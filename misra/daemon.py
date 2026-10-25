"""The tick: collect facts, run the rules, act on what's certain.

Runs every `interval` seconds, and straight away after a resume (the
misra-resume unit sends SIGUSR1; a jump between the boot-time and monotonic
clocks catches it too).

Writes (all paths configurable):
  /run/misra/state.json      what's true right now, for the bar, HUD and jantar
  /run/misra/alerts.json     recent alerts, numbered, for the desktop notifier
  /run/misra/state.json  .sky  is it a grey day (rules/sky.lp), for the bar's theme
  /run/misra/series.json     the last four hours, tick by tick: what each power sensor
                             claimed and what was believed, for the charts in alerts
  <state>/history.jsonl      one line per tick
  <state>/snapshots/...      facts + conclusions on every resume and every change
                             of fault; firmware tables and EC dumps on a new fault
"""

import json
import os
import shutil
import signal
import subprocess
import threading
import time
import tomllib
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

from . import messages
from .collect import ec, journal, links, power, weather
from .facts import atoms, fact
from .reason import solve

TRUST = {"ec": 5, "trend": 3, "acpi_bat": 2, "acpi_ac": 2, "ucsi": 1}


def boot_gap():
    """Time the machine has spent asleep since boot."""
    return time.clock_gettime(time.CLOCK_BOOTTIME) - time.clock_gettime(time.CLOCK_MONOTONIC)


def write_json(path, data):
    path = Path(path)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1, default=str) + "\n")
    os.chmod(tmp, 0o644)
    tmp.replace(path)


@dataclass
class Trend:
    """Charge level over time from one source, as a sensor of its own."""
    samples: deque = field(default_factory=lambda: deque(maxlen=200))

    def add(self, t, source, frac):
        if self.samples and self.samples[-1][1] != source:
            self.samples.clear()
        self.samples.append((t, source, frac))

    def reset(self):
        self.samples.clear()

    def claim(self, now):
        """(flow, source) once there's enough history, else None."""
        if len(self.samples) < 2:
            return None
        t0, source, f0 = self.samples[0]
        for t, _, f in self.samples:
            if now - t <= 900:
                t0, f0 = t, f
                break
        _, _, f1 = self.samples[-1]
        span, delta = now - t0, (f1 - f0) * 100
        if span >= 180 and delta <= -0.2:
            return "discharging", source
        if span >= 180 and delta >= 0.2:
            return "charging", source
        if span >= 600 and abs(delta) < 0.2:
            return "idle", source
        return None


class Misra:
    def __init__(self, state_dir="/var/lib/misra", run_dir="/run/misra",
                 config=None, interval=30, use_ec=True, weather_file=weather.FILE):
        self.state_dir, self.run_dir = Path(state_dir), Path(run_dir)
        self.weather_file, self.weather = weather_file, None
        self.interval, self.use_ec = interval, use_ec
        self.journal = journal.Journal()
        self.links = links.Links(uplinks=load_uplinks(config))
        self.trend = Trend()
        self.signals = deque(maxlen=40)          # (t, dBm)
        self.was = []                            # certain atoms from last tick
        self.first = True
        self.gap = boot_gap()
        self.alert_seq, self.alert_log = 0, deque(maxlen=30)
        self.series = deque(maxlen=max(60, 4 * 3600 // max(1, interval)))   # ~4 h of ticks
        self.last_deep = 0
        self.wake = threading.Event()

    # ---- One tick ----

    def tick(self, reason="timer"):
        now = time.time()
        facts, raw = [], {}

        resumes = self.journal.read_new()
        self.journal.prune(now)
        gap = boot_gap()
        slept = gap - self.gap > 5
        self.gap = gap
        # The first read covers the whole boot; only a recent resume counts.
        resumes = [r for r in resumes if now - r[0] <= max(120, 2 * self.interval)]
        if resumes or slept:
            kind = resumes[-1][1] if resumes else "sleep"
            facts.append(fact("resumed", kind))
            self.trend.reset()                  # a sleep breaks the time series
            self.signals.clear()
            reason = f"resume:{kind}"

        # Power sensors
        readings = power.collect()
        if self.use_ec:
            r, raw["ec"] = ec.collect()
            if r:
                readings.append(r)
        for r in readings:
            facts.append(fact("sensor", r.sensor))
            facts.append(fact("trust", r.sensor, TRUST[r.sensor]))
            facts += [fact("claim", r.sensor, p, v) for p, v in r.claims]
            if r.pct is not None:
                facts.append(fact("reading", r.sensor, "pct", int(r.pct)))
            facts += [fact("acpi_unreadable", k) for k in r.unreadable]
        for kind, dev, method in sorted(self.journal.acpi_errors):
            if kind != "other":                 # only battery and adapter methods matter here
                facts.append(fact("acpi_error", kind, dev, method))

        by = {r.sensor: r for r in readings}
        src = next((s for s in ("ec", "acpi_bat") if s in by and by[s].frac is not None), None)
        if src:
            self.trend.add(now, src, by[src].frac)
        tc = self.trend.claim(now)
        if tc:
            facts += [fact("sensor", "trend"), fact("trust", "trend", TRUST["trend"]),
                      fact("claim", "trend", "flow", tc[0]), fact("derived_from", "trend", tc[1])]

        # Links
        obs = self.links.collect(now)
        if obs["link_up"]:
            facts.append(fact("link_up", "wifi"))
            if "signal" in obs:
                facts.append(fact("signal", obs["signal"]))
                self.signals.append((now, obs["signal"]))
                then = [s for t, s in self.signals if 240 <= now - t <= 420]
                if then:
                    facts.append(fact("signal_then", then[0]))
            facts.append(fact("mlo_links", obs.get("mlo_links", 0)))
            for k, d in obs.get("counters", {}).items():
                facts.append(fact("counter", k, d))
        facts.append(fact("internet", obs["internet"]))
        for u in self.links.uplinks:
            facts.append(fact("uplink", u.label, u.role))
        facts += [fact("active", l) for l in obs["active"]]
        facts += [fact("visible", l) for l in obs["visible"]]
        facts += [fact("event", k, a, n) for n, (k, a) in enumerate(self.journal.event_facts(now))]

        # Weather (saved by the misra-weather unit; the daemon has no network)
        wfacts, self.weather = weather.collect(now, self.weather_file)
        facts += wfacts

        # Memory of last tick, for edge-triggered alerts
        facts += [f"was({a})." for a in self.was]
        if self.first:
            facts.append("first_tick.")

        res = solve(facts)
        state = self.state(now, res, by, obs, raw)
        self.record(now, reason, state, readings, tc)
        self.act(now, reason, facts, res, state, raw)
        self.was = sorted(str(a) for a in res.certain if a.name != "alert")
        self.first = False
        return facts, res, state

    # ---- Conclusions -> state ----

    def state(self, now, res, by, obs, raw):
        c = res.certain
        truth = dict(atoms(c, "truth"))
        faulty = [s for (s,) in atoms(c, "faulty")]
        shown = atoms(c, "shown_pct")
        pct, source = (shown[0] if len(shown) == 1 else (None, None))
        watts = by[source].watts if source in by else None
        charger = by["ucsi"].extra.get("charger_w") if "ucsi" in by and "ucsi" not in faulty else None
        return {
            "time": int(now),
            "power": {
                "pct": pct, "source": source,
                "ac": truth.get("ac"), "flow": truth.get("flow"),
                "battery": truth.get("battery"),
                "battery_w": round(watts, 1) if watts is not None else None,
                "charger_w": charger,
                "faulty": faulty,
                "blamed": [x for (x,) in atoms(c, "blamed")],
                "possible_faulty": sorted({s for (s,) in atoms(res.possible, "faulty")}),
                "support": {f"{p}={v}": n for p, v, n in atoms(c, "support")},
                "ok": bool(atoms(c, "power_ok")),
                "ec": "ok" if "ec" in by else raw.get("ec", "off"),
            },
            "links": {
                "state": next((s for (s,) in atoms(c, "link_state")), None),
                "problems": [p for (p,) in atoms(c, "problem")],
                "advice": [list(a) for a in atoms(c, "advise")],
                "signal": obs.get("signal"), "band": obs.get("band"),
                "mlo_links": obs.get("mlo_links"), "internet": obs.get("internet"),
                "active": obs.get("active"), "visible": obs.get("visible"),
            },
            "sky": {
                "gloomy": bool(atoms(c, "gloomy")),
                "why": [w for (w,) in atoms(c, "grey")],
                "fetched": self.weather.get("fetched") if self.weather else None,
                "cloud": self.weather.get("cloud_cover") if self.weather else None,
                "code": self.weather.get("weather_code") if self.weather else None,
            },
            "resume": {"time": self.journal.last_resume[0], "kind": self.journal.last_resume[1]}
                      if self.journal.last_resume else None,
            "models": res.models, "unsat": res.unsat,
        }

    # ---- The series behind the charts: claims next to beliefs, tick by tick ----

    def record(self, now, reason, state, readings, trend_claim):
        p = state["power"]
        claims = {r.sensor: dict(r.claims) for r in readings}
        if trend_claim:
            claims["trend"] = {"flow": trend_claim[0]}
        self.series.append({
            "t": int(now), "resume": reason.startswith("resume"),
            "believed": {"ac": p["ac"], "flow": p["flow"], "pct": p["pct"], "w": p["battery_w"]},
            "claims": claims,
            "pct": {r.sensor: round(r.pct, 1) for r in readings if r.pct is not None},
            "faulty": p["faulty"],
        })

    # ---- Acting: state file, alerts, snapshots, history ----

    def act(self, now, reason, facts, res, state, raw):
        self.run_dir.mkdir(parents=True, exist_ok=True)
        write_json(self.run_dir / "state.json", state)
        write_json(self.run_dir / "series.json", {"interval": self.interval, "ticks": list(self.series)})

        new = []
        for kind, title, body, urgency in messages.alerts(atoms(res.certain, "alert"), state):
            self.alert_seq += 1
            new.append({"seq": self.alert_seq, "time": int(now), "kind": kind,
                        "title": title, "body": body, "urgency": urgency})
        if new:
            self.alert_log.extend(new)
            write_json(self.run_dir / "alerts.json", {"seq": self.alert_seq, "alerts": list(self.alert_log)})

        for kind, why in atoms(res.certain, "capture"):
            if kind == "deep" and now - self.last_deep < 1800:
                kind = "light"
            if kind == "deep":
                self.last_deep = now
            self.snapshot(now, kind, why, facts, res, state, raw)

        self.history(state, reason)

    def snapshot(self, now, kind, why, facts, res, state, raw):
        d = self.state_dir / "snapshots" / f"{time.strftime('%Y%m%d-%H%M%S', time.localtime(now))}-{kind}-{why}"
        d.mkdir(parents=True, exist_ok=True)
        (d / "facts.lp").write_text("\n".join(facts) + "\n")
        (d / "conclusions.txt").write_text(
            "% certain\n" + "\n".join(sorted(map(str, res.certain))) +
            "\n% possible\n" + "\n".join(sorted(map(str, res.possible))) + "\n")
        write_json(d / "state.json", state)
        if kind == "deep":
            deep_capture(d, raw)
        prune(self.state_dir / "snapshots", {"light": 200, "deep": 20})

    def history(self, state, reason):
        p, l = state["power"], state["links"]
        line = {"t": state["time"], "why": reason, "pct": p["pct"], "src": p["source"],
                "ac": p["ac"], "flow": p["flow"], "w": p["battery_w"], "faulty": p["faulty"],
                "link": l["state"], "sig": l["signal"], "band": l["band"], "mlo": l["mlo_links"],
                "problems": l["problems"],
                # what each power sensor claimed this tick, next to what was believed above
                "claims": self.series[-1]["claims"] if self.series else {}}
        f = self.state_dir / "history.jsonl"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        if f.exists() and f.stat().st_size > 32 << 20:
            f.replace(f.with_suffix(".jsonl.1"))
        with open(f, "a") as out:
            out.write(json.dumps(line) + "\n")

    # ---- Loop ----

    def run(self):
        signal.signal(signal.SIGUSR1, lambda *_: self.wake.set())
        signal.signal(signal.SIGTERM, lambda *_: os._exit(0))
        reason = "start"
        while True:
            try:
                self.tick(reason)
            except Exception as e:                # keep watching even if one tick fails
                print(f"tick failed: {e!r}", flush=True)
            woke = self.wake.wait(self.interval)
            self.wake.clear()
            reason = "signal" if woke else "timer"


def load_uplinks(path):
    if not path or not Path(path).exists():
        return []
    with open(path, "rb") as f:
        cfg = tomllib.load(f)
    return [links.Uplink(u["label"], u["role"], u["connection"]) for u in cfg.get("uplink", [])]


def deep_capture(d, raw):
    """Everything about power and firmware state, for comparing broken with healthy."""
    r = d / "raw"
    r.mkdir(exist_ok=True)

    def save(name, *cmd):
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            (r / f"{name}.txt").write_text(f"$ {' '.join(cmd)}\n{p.stdout}{p.stderr}")
        except (OSError, subprocess.TimeoutExpired) as e:
            (r / f"{name}.txt").write_text(f"$ {' '.join(cmd)}\nfailed: {e}\n")

    save("power_supply", "sh", "-c", 'for d in /sys/class/power_supply/*; do echo "== $d"; '
         'for f in "$d"/*; do [ -f "$f" ] && printf "%s: %s\\n" "${f##*/}" "$(cat "$f" 2>&1)"; done; done')
    save("typec", "sh", "-c", 'for p in /sys/class/typec/*; do echo "== $p"; grep -H . "$p"/* 2>&1; done')
    save("acpi_devices", "sh", "-c", 'for d in /sys/bus/acpi/devices/PNP0C0A* /sys/bus/acpi/devices/ACPI0003*; '
         'do echo "== $d status=$(cat $d/status 2>&1) path=$(cat $d/path 2>&1)"; done')
    save("dmi", "sh", "-c", 'cd /sys/class/dmi/id && for f in sys_vendor product_name product_version '
         'bios_vendor bios_version bios_date ec_firmware_release; do echo "$f: $(cat $f 2>&1)"; done')
    save("upower", "upower", "-d")
    save("ec_battery", "ectool", "battery")
    save("ec_chargestate", "ectool", "chargestate", "show")
    save("ec_version", "ectool", "version")
    save("framework_power", "framework_tool", "--power")
    save("kernel", "journalctl", "-k", "-b", "--no-pager")
    save("cmdline", "cat", "/proc/cmdline")
    # Firmware tables, static and loaded-at-runtime: diff these broken vs healthy
    # (decompile later with `iasl -d`).
    try:
        shutil.copytree("/sys/firmware/acpi/tables", d / "acpi", dirs_exist_ok=True)
    except OSError as e:
        (r / "acpi-copy-failed.txt").write_text(str(e))


def prune(root, keep):
    for kind, n in keep.items():
        dirs = sorted(p for p in root.glob(f"*-{kind}-*") if p.is_dir())
        for p in dirs[:-n]:
            shutil.rmtree(p, ignore_errors=True)
