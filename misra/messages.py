"""Words for alerts. Kept apart from the rules so the rules stay about logic."""

SENSOR = {
    "acpi_bat": "the firmware's battery report (ACPI)",
    "acpi_ac": "the firmware's charger report (ACPI)",
    "ucsi": "the USB-C power report (UCSI)",
    "ec": "the embedded controller",
    "trend": "the charge trend",
}

PROBLEM = {
    "roam_burst": "roaming between access points again and again",
    "dropping": "the connection keeps dropping",
    "beacons_lost": "missing the access point's beacons",
    "weak": "weak signal",
    "fading": "signal fading fast",
    "mlo_degraded": "multi-link (MLO) down to one link",
    "no_internet": "connected, but no internet",
}


def belief(state):
    p = state["power"]
    parts = []
    if p["ac"]:
        parts.append("charger " + ("plugged in" if p["ac"] == "on" else "unplugged"))
    if p["flow"]:
        parts.append(f"battery {p['flow']}")
    if p["pct"] is not None:
        parts.append(f"{p['pct']}% per {SENSOR.get(p['source'], p['source'])}")
    else:
        parts.append("charge level unknown")
    return ", ".join(parts)


def advice(state):
    for a in state["links"]["advice"]:
        if a[0] == "prepare_fallback":
            return f"Fallback in range: {a[1]}."
        if a[0] == "enable_hotspot":
            return f"No fallback in range: turn on the {a[1]} hotspot."
        if a[0] == "no_fallback":
            return "No fallback configured."
    return ""


CAUSE = {"firmware": "The firmware's ACPI methods are failing"}


def names(args):
    return ", ".join(SENSOR.get(a, a) for a in args)


def alerts(found, state):
    """Alert atoms -> [(kind, title, body, urgency)]. Power faults that appear
    together are one event, so they become one notification."""
    out, faults, fixed = [], [], []
    for a in found:
        if a[0] == "power_fault":
            faults.append(a[1])
        elif a[0] == "power_recovered":
            fixed.append(a[1])
        else:
            out.append((a[0], *alert(a, state)))
    if faults:
        why = "; ".join(CAUSE.get(c, c) for c in state["power"].get("blamed", [])) \
            or "It disagrees with the other sensors"
        out.insert(0, ("power_fault", f"Not trusting {names(faults)}",
                       f"{why}. Believing: {belief(state)}. Snapshot saved.", "critical"))
    if fixed:
        out.append(("power_recovered", f"Trusting {names(fixed)} again", belief(state), "low"))
    return out


def alert(a, state):
    """(title, body, urgency) for one alert atom's arguments."""
    kind, arg = a[0], (a[1] if len(a) > 1 else None)
    if kind == "after_resume":
        return (f"Power readings broke after {arg} resume",
                f"Believing: {belief(state)}.", "critical")
    if kind == "link_at_risk":
        return (f"Wi-Fi: {PROBLEM.get(arg, arg)}", advice(state), "normal")
    if kind == "link_down":
        return ("Wi-Fi down", advice(state), "normal")
    if kind == "link_back":
        return ("Wi-Fi back", "", "low")
    if kind == "fallback":
        return (f"Fallback ready: {arg}", "In range if this link gets worse.", "low")
    if kind == "hotspot":
        return (f"Turn on the {arg} hotspot?", "Wi-Fi is struggling and no fallback is in range.", "normal")
    return (kind, str(arg or ""), "normal")
