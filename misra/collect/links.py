"""The Wi-Fi link (iw) and NetworkManager's view: which connection is up,
whether there's internet, and which configured fallbacks are in range.

Uses NetworkManager's cached scan results; never triggers a scan itself.
"""

import glob
import os
import re
import subprocess
from dataclasses import dataclass, field


def run(*args, timeout=5):
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return p.stdout if p.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def split_terse(line):
    """Split one line of `nmcli -t` output on unescaped colons."""
    parts, cur, esc = [], "", False
    for ch in line:
        if esc:
            cur += ch
            esc = False
        elif ch == "\\":
            esc = True
        elif ch == ":":
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    parts.append(cur)
    return parts


def wifi_iface():
    for d in sorted(glob.glob("/sys/class/net/*/wireless")):
        return os.path.basename(os.path.dirname(d))
    return None


def parse_link(text):
    if not text or text.startswith("Not connected"):
        return None
    out = {}
    if m := re.search(r"signal:\s*(-?\d+) dBm", text):
        out["signal"] = int(m.group(1))
    if m := re.search(r"freq:\s*([\d.]+)", text):
        out["freq"] = int(float(m.group(1)))
    return out


def parse_mlo_links(info):
    """Number of links in a multi-link (MLO) association, 0 if not MLO."""
    return len(re.findall(r"^\s*- link ID\s+\d+", info, re.M))


def parse_station(text):
    out = {}
    for key in ("beacon loss", "tx failed", "tx retries", "tx packets", "connected time"):
        if m := re.search(rf"^\s*{key}:\s*(\d+)", text, re.M):
            out[key.replace(" ", "_")] = int(m.group(1))
    return out


def band(freq):
    if not freq:
        return None
    return "2.4" if freq < 3000 else "5" if freq < 5925 else "6"


@dataclass
class Uplink:
    label: str
    role: str
    connection: str
    ssid: str | None = None


@dataclass
class Links:
    uplinks: list = field(default_factory=list)
    prev_station: dict = field(default_factory=dict)
    ssid_refreshed: float = 0

    def refresh_ssids(self, now, every=600):
        if now - self.ssid_refreshed < every:
            return
        self.ssid_refreshed = now
        for u in self.uplinks:
            ssid = run("nmcli", "-g", "802-11-wireless.ssid", "connection", "show", u.connection).strip()
            u.ssid = ssid or None

    def collect(self, now):
        """A dict of observations, free of SSIDs and addresses."""
        self.refresh_ssids(now)
        obs = {"link_up": False}
        iface = wifi_iface()
        if iface:
            link = parse_link(run("iw", "dev", iface, "link"))
            if link:
                obs["link_up"] = True
                obs.update(link)
                obs["band"] = band(link.get("freq"))
                obs["mlo_links"] = parse_mlo_links(run("iw", "dev", iface, "info"))
                st = parse_station(run("iw", "dev", iface, "station", "dump"))
                prev = self.prev_station
                fresh = not prev or st.get("connected_time", 0) < prev.get("connected_time", 0)
                for k in ("beacon_loss", "tx_failed"):
                    if k in st:
                        obs.setdefault("counters", {})[k] = st[k] if fresh else max(0, st[k] - prev.get(k, 0))
                self.prev_station = st
            else:
                self.prev_station = {}

        conn = run("nmcli", "-t", "-f", "CONNECTIVITY", "general").strip()
        obs["internet"] = conn or "unknown"

        active = set()
        for line in run("nmcli", "-t", "-f", "NAME,TYPE", "connection", "show", "--active").splitlines():
            parts = split_terse(line)
            if parts:
                active.add(parts[0])
        seen = {split_terse(l)[0] for l in run("nmcli", "-t", "-f", "SSID", "device", "wifi",
                                                "list", "--rescan", "no").splitlines()}
        obs["active"] = [u.label for u in self.uplinks if u.connection in active]
        obs["visible"] = [u.label for u in self.uplinks if u.ssid and u.ssid in seen]
        return obs
