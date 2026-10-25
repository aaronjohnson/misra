"""An episode publishes only the power evidence, never names or serials."""

from misra.episode import make, scrub

SNAPSHOT_FACTS = """
sensor(acpi_bat;ucsi). trust(acpi_bat,2). trust(ucsi,1).
claim(acpi_bat,battery,present). claim(acpi_bat,flow,discharging).
claim(ucsi,ac,on).
reading(acpi_bat,pct,72).
acpi_error(battery,"BAT1","_STA").
resumed(hibernate).
uplink("Home-Wifi-5G",primary). active("Home-Wifi-5G"). visible("Neighbour").
signal(-48). counter(tx_failed,3). internet(full).
"""


def test_scrub_keeps_power_drops_links():
    out = scrub(SNAPSHOT_FACTS)
    assert "claim(ucsi,ac,on)." in out and 'acpi_error(battery,"BAT1","_STA").' in out
    assert "resumed(hibernate)." in out and "sensor(acpi_bat;ucsi)." in out
    for private in ("Home-Wifi", "Neighbour", "uplink", "signal", "counter"):
        assert private not in out


def test_make_writes_the_episode_and_indexes_it(tmp_path):
    snap = tmp_path / "snapshots" / "20261025-101500-deep-power_fault"
    snap.mkdir(parents=True)
    (snap / "facts.lp").write_text(SNAPSHOT_FACTS)
    folder = make(snap, "ucsi-stale-after-unplug", tmp_path)
    assert folder.name == "2026-10-25-ucsi-stale-after-unplug"
    assert {p.name for p in folder.iterdir()} == {"facts.lp", "explain.png", "README.md"}
    assert "Home-Wifi" not in (folder / "facts.lp").read_text()
    index = (tmp_path / "docs/incidents/README.md").read_text()
    assert "ucsi-stale-after-unplug" in index
    make(snap, "ucsi-stale-after-unplug", tmp_path)          # again: no duplicate row
    assert (tmp_path / "docs/incidents/README.md").read_text().count("ucsi-stale-after-unplug](") == 1
