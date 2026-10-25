"""The rules, case by case. Each case is a set of facts and what must (and
must not) be certain afterwards."""

from pathlib import Path

import pytest

from misra.reason import solve

CASES = Path(__file__).parent / "cases"

SENSORS = """
trust(acpi_bat,2). trust(acpi_ac,2). trust(ucsi,1). trust(ec,5). trust(trend,3).
"""


def certain(*facts):
    res = solve([SENSORS, *facts])
    assert not res.unsat
    return {str(a) for a in res.certain}, {str(a) for a in res.possible}


def test_incident_2026_10_17():
    c, _ = certain((CASES / "incident-2026-10-17.lp").read_text())
    assert {"faulty(acpi_bat)", "faulty(acpi_ac)", "faulty(ucsi)"} <= c
    assert "faulty(ec)" not in c
    assert {"truth(ac,off)", "truth(flow,discharging)", "shown_pct(88,ec)"} <= c
    assert {"alert(after_resume,hibernate)", "capture(deep,power_fault)"} <= c


def test_healthy_on_battery():
    c, _ = certain("""
        sensor(acpi_bat;acpi_ac;ucsi;ec;trend).
        claim(acpi_bat,battery,present). claim(acpi_bat,flow,discharging). reading(acpi_bat,pct,70).
        claim(acpi_ac,ac,off). claim(ucsi,ac,off).
        claim(ec,ac,off). claim(ec,battery,present). claim(ec,flow,discharging). reading(ec,pct,71).
        claim(trend,flow,discharging). derived_from(trend,ec).
    """)
    assert "power_ok" in c
    assert "shown_pct(71,ec)" in c
    assert "support(flow,discharging,3)" in c


def test_healthy_without_ec_uses_acpi():
    c, _ = certain("""
        sensor(acpi_bat;acpi_ac;ucsi).
        claim(acpi_bat,battery,present). claim(acpi_bat,flow,charging). reading(acpi_bat,pct,50).
        claim(acpi_ac,ac,on). claim(ucsi,ac,on).
    """)
    assert {"power_ok", "shown_pct(50,acpi_bat)", "truth(ac,on)"} <= c


def test_frozen_firmware_readings():
    """ACPI stuck at 'full, on AC' while the EC sees the battery draining."""
    c, _ = certain("""
        sensor(acpi_bat;acpi_ac;ucsi;ec).
        claim(acpi_bat,battery,present). claim(acpi_bat,flow,idle). reading(acpi_bat,pct,100).
        claim(acpi_ac,ac,on). claim(ucsi,ac,on).
        claim(ec,ac,off). claim(ec,battery,present). claim(ec,flow,discharging). reading(ec,pct,92).
    """)
    assert {"faulty(acpi_bat)", "faulty(acpi_ac)", "faulty(ucsi)", "shown_pct(92,ec)"} <= c
    assert "blamed(firmware)" in c


def test_no_ec_and_no_battery_report_means_unknown_not_zero():
    """This morning without root: nothing reliable knows the charge level."""
    c, _ = certain("""
        sensor(acpi_bat;acpi_ac;ucsi).
        claim(acpi_bat,battery,absent). acpi_unreadable(battery).
        acpi_unreadable(adapter). claim(ucsi,ac,on).
    """)
    assert not any(a.startswith("shown_pct") for a in c)
    assert {"faulty(acpi_bat)", "faulty(acpi_ac)"} <= c


def test_a_tie_is_possible_not_certain():
    c, p = certain("""
        sensor(a;b). trust(a,1). trust(b,1).
        claim(a,ac,on). claim(b,ac,off).
        claim(a,battery,present).
    """)
    assert "faulty(a)" not in c and "faulty(b)" not in c
    assert {"faulty(a)", "faulty(b)"} <= p


def test_recovered_alert_is_edge_triggered():
    c, _ = certain("""
        sensor(ec). claim(ec,ac,on). claim(ec,battery,present). claim(ec,flow,charging).
        was(faulty(ucsi)). was(faulty(ec)).
    """)
    assert "alert(power_recovered,ucsi)" in c
    assert not any(a.startswith("alert(power_fault") for a in c)


# ---- Links ----

HOME = """
sensor(ec). claim(ec,ac,on). claim(ec,battery,present). claim(ec,flow,idle).
uplink(home,mlo). uplink("4runner",starlink). uplink(phone,phone_hotspot).
active(home). link_up(wifi). internet(full). mlo_links(2). signal(-55).
"""


def test_healthy_link():
    c, _ = certain(HOME)
    assert "link_state(ok)" in c
    assert not any(a.startswith("advise") for a in c)


def test_roam_burst_prepares_starlink_fallback():
    c, _ = certain(HOME, 'visible("4runner"). event(assoc,30,0). event(assoc,90,1). event(assoc,200,2).')
    assert {"link_state(at_risk)", "problem(roam_burst)", 'advise(prepare_fallback,"4runner")',
            'alert(fallback,"4runner")', "alert(link_at_risk,roam_burst)"} <= c


def test_two_events_at_the_same_age_both_count():
    c, _ = certain(HOME, "event(assoc,30,0). event(assoc,30,1). event(assoc,30,2).")
    assert "problem(roam_burst)" in c


def test_mlo_down_to_one_link():
    c, _ = certain(HOME.replace("mlo_links(2)", "mlo_links(1)"))
    assert "problem(mlo_degraded)" in c


def test_nothing_in_range_asks_for_the_hotspot():
    c, _ = certain(HOME.replace("signal(-55)", "signal(-80)"))
    assert {"problem(weak)", "advise(enable_hotspot,phone)"} <= c


def test_starlink_preferred_over_phone():
    c, _ = certain(HOME.replace("signal(-55)", "signal(-80)"), 'visible("4runner"). visible(phone).')
    assert 'advise(prepare_fallback,"4runner")' in c
    assert "advise(prepare_fallback,phone)" not in c


def test_known_problem_does_not_alert_again():
    c, _ = certain(HOME.replace("signal(-55)", "signal(-80)"), "was(problem(weak)).")
    assert "problem(weak)" in c
    assert "alert(link_at_risk,weak)" not in c


def test_no_alerts_on_first_tick():
    c, _ = certain(HOME.replace("signal(-55)", "signal(-80)"), "first_tick.")
    assert "alert(link_at_risk,weak)" not in c


def test_simultaneous_faults_make_one_notification():
    from misra import messages
    state = {"power": {"blamed": ["firmware"], "ac": "off", "flow": "discharging",
                       "pct": 88, "source": "ec"}, "links": {"advice": []}}
    out = messages.alerts([("power_fault", "acpi_bat"), ("power_fault", "ucsi"),
                           ("after_resume", "hibernate")], state)
    assert [o[0] for o in out] == ["power_fault", "after_resume"]
    assert "firmware" in out[0][1] or "firmware" in out[0][2]
    assert "88%" in out[0][2]


# ---- sky.lp: grey days ----

def sky(*facts):
    c, _ = certain(*facts)
    return "gloomy" in c, sorted(a[5:-1] for a in c if a.startswith("grey("))


def test_rain_is_gloomy():
    # 2026-10-25, Vancouver WA at noon: light rain, full cloud
    assert sky("weather_age(60). cloud(100). rain(6). wmo(61). radiation(116). daylight.") == (True, ["overcast", "rain"])


def test_clear_day_is_not():
    assert sky("weather_age(60). cloud(10). rain(0). wmo(1). radiation(420). daylight.") == (False, [])


def test_thin_overcast_is_not():
    # cloudy but bright enough to light the room
    assert sky("weather_age(60). cloud(95). rain(0). wmo(3). radiation(240). daylight.") == (False, [])


def test_stale_weather_says_nothing():
    assert sky("weather_age(7200). cloud(100). rain(20). wmo(63). radiation(50). daylight.") == (False, [])


def test_gap_in_the_clouds_keeps_it_grey():
    gap = "weather_age(60). cloud(80). rain(0). wmo(2). radiation(200). daylight."
    assert sky(gap, "was(gloomy).") == (True, ["lingering"])
    assert sky(gap) == (False, [])


def test_sun_breaks_through():
    assert sky("weather_age(60). cloud(80). rain(0). wmo(2). radiation(350). daylight.", "was(gloomy).") == (False, [])
