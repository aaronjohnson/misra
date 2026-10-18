# Battery disappears after resume from hibernation

**Machine:** Framework Laptop 13 Pro (Intel Core Ultra Series 3), board A7.
**Firmware:** INSYDE BIOS 03.02 (2026-05-26). Kernel 7.2.9, NixOS 26.11.
**Status:** open. First seen 2026-10-17, noticed 2026-10-18.

## What was seen

Charged overnight, then unplugged. An hour later the bar and the HUD both showed
**0 %** and **100 W charging**, with no drain over time.

## What was actually wrong

- **03:41 Oct 17:** resume from hibernation (S4, after `suspend-then-hibernate`,
  `HibernateDelaySec = 2h`). From then on, the firmware's ACPI methods for the
  battery and AC adapter fail when run:
  - `\_SB.PC00.LPCB.BAT1._STA`: `Could not resolve symbol [...BAT1._STA.RMS], AE_NOT_FOUND`
  - `\_SB.PC00.LPCB.ACAD._PSR`: `AE_AML_PACKAGE_LIMIT` ("Error reading AC Adapter state")
- With `_STA` failing, the kernel dropped `BAT1`: `/sys/class/power_supply/`
  had no battery, but `/sys/bus/acpi/devices/PNP0C0A:00` was still present.
- upower restarted at 03:52 and its summary (`DisplayDevice`) never updated again.
- UCSI port 3 still said `online=1, 20 V x 5 A` after the charger was unplugged.
  That stale value is the "100 W".
- Three more hibernate/resume cycles (Oct 17 08:00 and 17:41, Oct 18 09:24) did
  not bring the battery back.
- **Not related:** the constant `I2C5._PS3` and `HDAS._PS3` AE_NOT_FOUND messages,
  which show up on every boot.

## Why the displays showed confident wrong numbers

- The bar and HUD read `BAT1` and the UCSI files directly. If a file is
  missing they read it as 0, and they don't check how old a value is.
- Nothing compared the separate sources of truth: ACPI battery, UCSI, the EC,
  and whether the energy level actually changes over time. That is why misra
  exists; this incident is its first test case
  (`tests/cases/incident-2026-10-17.lp`).

## Guesses (not yet tested)

- `RMS` not found *inside* the `_STA` method could mean an ACPI table loaded
  while the system runs (`/sys/firmware/acpi/tables/dynamic`) or a firmware memory
  region doesn't match what was saved in the hibernation image. To test: diff
  the ACPI tables in a misra deep snapshot from a broken resume against one
  from a healthy boot.
- If so, the bug is in the firmware or in how the kernel restores ACPI after
  hibernation. It is not a userspace bug.

## Evidence

- misra takes a deep snapshot automatically when a new power fault appears
  (`/var/lib/misra/snapshots/*-deep-*`). For a healthy baseline after a
  cold boot, run `sudo misra capture healthy`. Snapshots stay local
  (see ../privacy.md).

## Similar reports

- Framework tracker #269 (same model, BIOS 03.02): CPU stuck at 400 MHz on battery.
  It also survives resume and is cleared by a reboot.
  https://github.com/FrameworkComputer/SoftwareFirmwareIssueTracker/issues/269

## Next steps

- [ ] Capture the broken state, reboot, capture the healthy state, diff the ACPI tables
- [ ] Reproduce on purpose: `systemctl hibernate` on battery, then on AC
- [ ] Report to the Framework tracker, attaching the dumps
- [ ] Re-test with each new BIOS (check resources.frame.work/downloads/laptop-13-pro/)
