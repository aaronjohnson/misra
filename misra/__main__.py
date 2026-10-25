"""misra: cross-checks a laptop's sensors with logic rules.

  misra daemon                 watch: tick every 30 s and after every resume
  misra once [--facts]         one tick, printed (no root: the EC is skipped)
  misra solve FILE.lp...       run the rules over fact files
  misra notify                 (as the desktop user) show new alerts
  misra capture [REASON]       save a full snapshot now
  misra explain [FILE.lp...]   draw how the power rules reached their answer
                               (from fact files, or a live tick); --show in kitty
  misra episode SNAPSHOT SLUG  publish a snapshot as an episode in docs/incidents/:
                               scrubbed facts, the explain picture, a story skeleton
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path



def main(argv=None):
    ap = argparse.ArgumentParser(prog="misra", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--state-dir", default=os.environ.get("MISRA_STATE", "/var/lib/misra"))
    ap.add_argument("--run-dir", default=os.environ.get("MISRA_RUN", "/run/misra"))
    ap.add_argument("--config", default=os.environ.get("MISRA_CONFIG", "/var/lib/misra/local.toml"))
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("daemon")
    d.add_argument("--interval", type=int, default=30)
    o = sub.add_parser("once")
    o.add_argument("--facts", action="store_true", help="print the facts too")
    s = sub.add_parser("solve")
    s.add_argument("files", nargs="+")
    sub.add_parser("notify")
    c = sub.add_parser("capture")
    c.add_argument("reason", nargs="?", default="manual")
    e = sub.add_parser("explain")
    e.add_argument("files", nargs="*", help="fact files; none = a live tick")
    e.add_argument("--out", default=None, help="PNG to write (default: misra-explain.png here)")
    e.add_argument("--light", action="store_true", help="light palette")
    e.add_argument("--show", action="store_true", help="show it in the terminal (kitty)")
    p = sub.add_parser("episode")
    p.add_argument("snapshot", help="a snapshot folder (with facts.lp)")
    p.add_argument("slug", help="short name, e.g. ucsi-stuck-on-after-unplug")
    p.add_argument("--repo", default=".", help="the misra checkout to write into")
    a = ap.parse_args(argv)

    if a.cmd == "explain":
        return explain(a)
    if a.cmd == "episode":
        from .episode import make
        print(make(a.snapshot, a.slug, a.repo))
        return 0

    if a.cmd == "solve":
        from .reason import solve
        facts = [Path(f).read_text() for f in a.files]
        res = solve(facts)
        print(f"% {res.models} optimal model(s), cost {res.cost}" + (" UNSAT" if res.unsat else ""))
        for sym in sorted(res.certain, key=str):
            print(sym)
        if res.possible:
            print("% possible:", " ".join(sorted(map(str, res.possible))))
        return 0

    if a.cmd == "notify":
        return notify(a.run_dir)

    from .daemon import Misra, deep_capture
    root = os.geteuid() == 0
    if a.cmd == "once":
        tmp = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "misra-once"
        m = Misra(state_dir=tmp, run_dir=tmp, config=a.config, use_ec=root)
        facts, res, state = m.tick("once")
        if a.facts:
            print("\n".join(facts))
            print()
        print(json.dumps(state, indent=1))
        return 0
    if a.cmd == "capture":
        d = Path(a.state_dir) / "snapshots" / f"{time.strftime('%Y%m%d-%H%M%S')}-deep-{a.reason}"
        d.mkdir(parents=True, exist_ok=True)
        deep_capture(d, {})
        print(d)
        return 0
    if a.cmd == "daemon":
        Misra(a.state_dir, a.run_dir, a.config, a.interval, use_ec=root).run()


def explain(a):
    from .explain import render
    if a.files:
        facts = [Path(f).read_text() for f in a.files]
        title = " + ".join(Path(f).name for f in a.files)
    else:
        from .daemon import Misra
        tmp = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "misra-once"
        facts, _, _ = Misra(state_dir=tmp, run_dir=tmp, config=a.config,
                            use_ec=os.geteuid() == 0).tick("explain")
        title = "this machine, now"
    out = Path(a.out or "misra-explain.png")
    _, res = render(facts, out, mode="light" if a.light else "dark", title=title)
    print(out)
    if a.show:
        subprocess.run(["kitten", "icat", str(out)], check=False)
    return 1 if res.unsat else 0


POWER_ALERTS = {"power_fault", "power_recovered", "after_resume"}


def power_chart(run_dir, alert):
    """The last two hours as small multiples (chart.py), for the alert's image.
    Drawn in the notification theme's colours: mako's "light" mode by day."""
    try:
        mode = subprocess.run(["makoctl", "mode"], capture_output=True, text=True).stdout
    except OSError:          # not mako, or not on this service's PATH: the dark palette
        mode = ""
    try:
        from .chart import render
        series = json.loads((Path(run_dir) / "series.json").read_text())
        out = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "misra"
        out.mkdir(parents=True, exist_ok=True)
        for old in sorted(out.glob("alert-*.png"))[:-10]:   # keep the last few
            old.unlink(missing_ok=True)
        return render(series, out / f"alert-{alert['seq']}.png",
                      mode="light" if "light" in mode.split() else "dark")
    except (OSError, ValueError, ImportError):
        return None                                          # the alert still goes out, text only


def notify(run_dir):
    """Show alerts newer than the last one shown. Run by a path unit whenever
    alerts.json changes."""
    src = Path(run_dir) / "alerts.json"
    seen_file = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "misra-seen"
    try:
        data = json.loads(src.read_text())
    except (OSError, ValueError):
        return 0
    try:
        seen = int(seen_file.read_text())
    except (OSError, ValueError):
        seen = 0
    if data.get("seq", 0) < seen:          # the daemon restarted and counts from 1 again
        seen = 0
    for al in data.get("alerts", []):
        if al["seq"] <= seen:
            continue
        cmd = ["notify-send", "-a", "misra", "-u", al.get("urgency", "normal")]
        chart = power_chart(run_dir, al) if al.get("kind") in POWER_ALERTS else None
        if chart:
            cmd += ["-i", str(chart)]
        subprocess.run(cmd + [al["title"], al.get("body", "")], check=False)
        seen = al["seq"]
    seen_file.parent.mkdir(parents=True, exist_ok=True)
    seen_file.write_text(str(seen))
    return 0


if __name__ == "__main__":
    sys.exit(main())
