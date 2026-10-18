"""Parsers for tool and log output. Addresses use the documentation range
(00:00:5e:00:53:xx, RFC 9542)."""

from misra.collect import ec, journal, links


def kinds(msg, source="kernel"):
    return journal.classify(msg, source)


def test_resume_and_sleep():
    assert kinds("PM: hibernation: hibernation exit") == [("resume", "hibernate")]
    assert kinds("PM: suspend exit") == [("resume", "suspend")]
    assert kinds("PM: suspend entry (s2idle)") == [("sleep", None)]


def test_acpi_errors():
    m = r"ACPI Error: Aborting method \_SB.PC00.LPCB.BAT1._STA due to previous error (AE_NOT_FOUND)"
    assert kinds(m) == [("acpi_error", ("battery", "BAT1", "_STA"))]
    m = r"ACPI Error: Aborting method \_SB.PC00.LPCB.ACAD._PSR due to previous error (AE_AML_PACKAGE_LIMIT)"
    assert kinds(m) == [("acpi_error", ("adapter", "ACAD", "_PSR"))]
    m = r"ACPI Error: Aborting method \_SB.PC00.I2C5._PS3 due to previous error (AE_NOT_FOUND)"
    assert kinds(m)[0][1][0] == "other"


def test_wifi_events():
    assert kinds("wlp0s20f3: [link 2] local address 00:00:5e:00:53:01, AP link address "
                 "00:00:5e:00:53:02 (assoc)") == [("assoc", None)]
    assert kinds("wlp0s20f3: [link 1] local address 00:00:5e:00:53:01, AP link address "
                 "00:00:5e:00:53:03") == []
    assert kinds("wlp0s20f3: associated") == [("assoc", None)]
    assert kinds("wlp0s20f3: deauthenticated from 00:00:5e:00:53:02 (Reason: 15=4WAY_HANDSHAKE_TIMEOUT)") \
        == [("drop_remote", 15), ("handshake_timeout", None)]
    assert kinds("wlp0s20f3: deauthenticating from 00:00:5e:00:53:02 by local choice "
                 "(Reason: 3=DEAUTH_LEAVING)") == [("drop_local", None)]
    assert kinds("wlp0s20f3: CTRL-EVENT-BEACON-LOSS bssid=00:00:5e:00:53:02", "wpa") \
        == [("beacon_loss", None)]


def test_acpi_errors_reset_on_sleep():
    j = journal.Journal()
    r = []
    j.note(1, "acpi_error", ("battery", "BAT1", "_STA"), r)
    j.note(2, "sleep", None, r)
    assert not j.acpi_errors
    j.note(3, "resume", "hibernate", r)
    j.note(3, "acpi_error", ("battery", "BAT1", "_STA"), r)
    assert j.acpi_errors and r == [(3, "hibernate")]


EC_DISCHARGING = """Battery info:
  OEM name:               EXAMPLE
  Design capacity:        5491 mAh
  Last full charge:       5200 mAh
  Design output voltage   15400 mV
  Cycle count             21
  Present voltage         16000 mV
  Present current         500 mA
  Remaining capacity      4576 mAh
  Desired voltage         0 mV
  Desired current         0 mA
  Flags                   0x06 BATT_PRESENT DISCHARGING
"""


def test_ectool_battery():
    r = ec.parse(EC_DISCHARGING)
    assert ("ac", "off") in r.claims and ("flow", "discharging") in r.claims
    assert r.pct == 88
    assert r.watts == -8.0


def test_ectool_on_ac_full():
    r = ec.parse(EC_DISCHARGING.replace("0x06 BATT_PRESENT DISCHARGING", "0x03 AC_PRESENT BATT_PRESENT"))
    assert ("ac", "on") in r.claims and ("flow", "idle") in r.claims


def test_ectool_garbage():
    assert ec.parse("Couldn't find EC") is None


def test_mlo_links():
    info = """Interface wlp0s20f3
	ifindex 3
	type managed
	MLD with links:
	 - link ID  1 link addr 00:00:5e:00:53:01
	   channel 37 (6135 MHz), width: 320 MHz, center1: 6105 MHz
	 - link ID  2 link addr 00:00:5e:00:53:04
	   channel 44 (5220 MHz), width: 160 MHz, center1: 5250 MHz
"""
    assert links.parse_mlo_links(info) == 2
    assert links.parse_mlo_links("Interface wlp0s20f3\n\tchannel 44 (5220 MHz)") == 0


def test_iw_link():
    assert links.parse_link("Not connected.") is None
    assert links.parse_link("Connected to 00:00:5e:00:53:02 (on wlp0s20f3)\n\tfreq: 5220.0\n\tsignal: -59 dBm") \
        == {"signal": -59, "freq": 5220}


def test_nmcli_terse():
    assert links.split_terse(r"Cafe\: 5G:802-11-wireless") == ["Cafe: 5G", "802-11-wireless"]
