# Privacy

misra is built to be published and used without revealing anything about
whoever runs it.

**Stays on the machine** (`/var/lib/misra`, `/run/misra`, not in git):

- `local.toml`: your connection names
- `snapshots/`: facts and conclusions, plus on a new power fault the raw
  EC output (which includes the battery's serial number), the kernel log,
  `upower -d` and the firmware's ACPI tables
- `history.jsonl`: one line per check (levels, labels, signal; no names
  or addresses)

**Never collected**: SSIDs, BSSIDs, MAC or IP addresses as facts. Wi-Fi
facts are counts, signal levels, bands and the labels from `local.toml`.

**Before sharing a snapshot** (in a bug report, for example), look through
`raw/`. Remove the serial number from `ec_battery.txt` and addresses from
`kernel.txt`. The ACPI tables and `facts.lp` are usually fine to share.

**In this repository**, example addresses come from the documentation range
`00:00:5e:00:53:xx` (RFC 9542).
