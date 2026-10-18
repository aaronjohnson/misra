"""Power sensors as seen through the kernel (sysfs): the ACPI battery and
adapter, and the USB-C ports (UCSI). Reads only; needs no privileges.

Each reader returns a Reading: the sensor's claims about the world, plus any
numbers worth keeping for trends and displays.
"""

import glob
import os
from dataclasses import dataclass, field

PS = "/sys/class/power_supply"
ACPI = "/sys/bus/acpi/devices"


@dataclass
class Reading:
    sensor: str
    claims: list = field(default_factory=list)   # (prop, value)
    pct: float | None = None
    frac: float | None = None                    # charge as a fraction of full, for trends
    watts: float | None = None                   # + into the battery, - out of it
    extra: dict = field(default_factory=dict)
    unreadable: list = field(default_factory=list)  # ACPI kinds whose reads failed


def read(path):
    """A sysfs value, or None. Raises OSError if the read itself fails
    (that is how a failing firmware method shows up)."""
    try:
        with open(path) as f:
            return f.read().strip()
    except FileNotFoundError:
        return None


def num(path):
    try:
        v = read(path)
    except OSError:
        return None
    try:
        return int(v) if v is not None else None
    except ValueError:
        return None


FLOW = {"Charging": "charging", "Discharging": "discharging",
        "Full": "idle", "Not charging": "idle"}


def acpi_devices(hid):
    return sorted(glob.glob(f"{ACPI}/{hid}:*"))


def acpi_battery():
    """The ACPI battery (PNP0C0A). None if the machine has no battery slot."""
    slots = acpi_devices("PNP0C0A")
    if not slots:
        return None
    r = Reading("acpi_bat")
    for slot in slots:
        try:
            read(f"{slot}/status")          # runs _STA in the firmware
        except OSError:
            r.unreadable.append("battery")
    bats = sorted(glob.glob(f"{PS}/BAT*"))
    if not bats:
        r.claims.append(("battery", "absent"))
        return r
    d = bats[0]
    try:
        status = read(f"{d}/status")
    except OSError:
        r.unreadable.append("battery")
        return r
    if read(f"{d}/present") == "0":
        r.claims.append(("battery", "absent"))
        return r
    r.claims.append(("battery", "present"))
    if status in FLOW:
        r.claims.append(("flow", FLOW[status]))
    r.pct = num(f"{d}/capacity")
    now = num(f"{d}/energy_now") or num(f"{d}/charge_now")
    full = num(f"{d}/energy_full") or num(f"{d}/charge_full")
    if now is not None and full:
        r.frac = now / full
    p = num(f"{d}/power_now")
    if p is None:
        i, v = num(f"{d}/current_now"), num(f"{d}/voltage_now")
        p = i * v / 1e6 if i is not None and v is not None else None
    if p is not None:
        w = p / 1e6
        r.watts = -w if status == "Discharging" else w
    return r


def acpi_adapter():
    """The ACPI AC adapter (ACPI0003), as the kernel names it (ACAD, AC, ADP1...)."""
    if not acpi_devices("ACPI0003"):
        return None
    r = Reading("acpi_ac")
    for d in glob.glob(f"{PS}/*"):
        if read(f"{d}/type") != "Mains":
            continue
        try:
            online = read(f"{d}/online")    # runs _PSR in the firmware
        except OSError:
            r.unreadable.append("adapter")
            continue
        if online is None:
            # The kernel hides `online` when it can't evaluate _PSR.
            r.unreadable.append("adapter")
        else:
            r.claims.append(("ac", "on" if online == "1" else "off"))
    return r


def ucsi():
    """USB-C power delivery as the UCSI driver reports it, port by port."""
    ports = sorted(glob.glob(f"{PS}/ucsi-source-psy-*"))
    if not ports:
        return None
    r = Reading("ucsi")
    watts, online = 0.0, []
    for d in ports:
        if num(f"{d}/online") == 1:
            online.append(os.path.basename(d).rsplit(":", 1)[-1])
            v, i = num(f"{d}/voltage_now"), num(f"{d}/current_max") or num(f"{d}/current_now")
            if v and i:
                watts = max(watts, v * i / 1e12)
    r.claims.append(("ac", "on" if online else "off"))
    r.extra = {"ports_online": online, "charger_w": round(watts, 1) if online else 0}
    return r


def collect():
    return [x for x in (acpi_battery(), acpi_adapter(), ucsi()) if x is not None]
