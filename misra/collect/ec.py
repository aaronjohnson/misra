"""The embedded controller (EC), read directly with ectool.

The EC manages the battery and charger itself, so its view doesn't depend on
the firmware's ACPI methods or on the USB-C (UCSI) driver. That makes it the
independent witness when those disagree. Needs root (/dev/cros_ec).

`ectool battery` prints lines like:
    Last full charge:       5200 mAh
    Present voltage         17004 mV
    Present current         1234 mA
    Remaining capacity      4570 mAh
    Flags                   0x0b AC_PRESENT BATT_PRESENT DISCHARGING
"""

import re
import subprocess

from .power import Reading

_NUM = re.compile(r"^\s*([A-Za-z][A-Za-z ]*?)\s*:?\s+(-?\d+)\s*(mAh|mV|mA)\b", re.M)
_FLAGS = re.compile(r"^\s*Flags\s*:?\s+0x[0-9a-fA-F]+\s*(.*)$", re.M)


def parse(text):
    """`ectool battery` output -> Reading, or None if it isn't recognisable."""
    nums = {k.strip().lower(): int(v) for k, v, _ in _NUM.findall(text)}
    m = _FLAGS.search(text)
    if not m:
        return None
    flags = set(m.group(1).split())
    r = Reading("ec")
    r.claims.append(("ac", "on" if "AC_PRESENT" in flags else "off"))
    if "BATT_PRESENT" not in flags:
        r.claims.append(("battery", "absent"))
        return r
    r.claims.append(("battery", "present"))
    if "DISCHARGING" in flags:
        flow = "discharging"
    elif "CHARGING" in flags:
        flow = "charging"
    else:
        flow = "idle"
    r.claims.append(("flow", flow))
    rem, full = nums.get("remaining capacity"), nums.get("last full charge")
    if rem is not None and full:
        r.frac = rem / full
        r.pct = round(100 * rem / full)
    i, v = nums.get("present current"), nums.get("present voltage")
    if i is not None and v is not None:
        w = abs(i) * v / 1e6
        r.watts = -w if flow == "discharging" else w
    r.extra = {"flags": sorted(flags)}
    return r


def collect():
    """(Reading or None, raw text or the reason it failed)."""
    try:
        p = subprocess.run(["ectool", "battery"], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired) as e:
        return None, f"ectool: {e}"
    text = p.stdout + p.stderr
    if p.returncode != 0:
        return None, text.strip().splitlines()[-1] if text.strip() else f"exit {p.returncode}"
    r = parse(text)
    return r, text if r else "unrecognised ectool output"
