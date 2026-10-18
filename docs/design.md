# Design

## The loop

```
collectors ──facts──▶ clingo (rules/*.lp) ──conclusions──▶ state.json
  sysfs, EC,            optimal models,                    alerts.json
  journal, iw,          certain / possible                 snapshots/
  NetworkManager                                           history.jsonl
        ▲                                                       │
        └──────────── was(...) : last tick's conclusions ◀──────┘
```

Each tick (every 30 s, or on SIGUSR1, which the `misra-resume` unit sends after
every wake):

1. **Collect.** Every source becomes facts: `claim(ec,ac,off)`,
   `acpi_error(battery,"BAT1","_STA")`, `event(assoc,42,0)`, `visible(phone)`.
   Collectors only parse. They never decide.
2. **Solve.** clingo finds every *optimal* answer.
3. **Split.** Conclusions true in every optimal answer are **certain**. Ones
   true in only some are **possible**. Only certain conclusions reach the
   displays and alerts, so a tie shows as "unknown", never as a coin flip.
4. **Act.** Write the state, raise new alerts, take snapshots, append to the
   history. The certain conclusions go into the next tick as `was(...)`, which
   makes alerts fire on changes, not on every tick.

## Power: diagnosis by minimal blame

This is consistency-based diagnosis, as in Reiter's 1987 "A theory of
diagnosis from first principles":

- three properties of the world: `ac` (on/off), `battery` (present/absent)
  and `flow` (charging/discharging/idle). Exactly one value of each is true.
- each sensor is either **normal**, in which case every claim it makes is
  true, or **abnormal** (`ab`), in which case its claims say nothing.
- **physics** limits what can be true: the machine is running, so it has AC
  or a battery; without AC the battery must be discharging; without a
  battery nothing flows.
- **evidence** forces `ab` at no cost: a failing firmware method
  (`acpi_error`), or a sysfs read that runs firmware and errors
  (`acpi_unreadable`).
- **shared causes**: the ACPI battery, the ACPI adapter and UCSI all reach
  the hardware through the firmware, so `broken(firmware)` can explain all
  three at once for the price of one guess.
- **derived sensors** inherit faults: the charge trend computed from the EC
  is abnormal if the EC is.
- **trust is a cost**: guessing that a sensor is broken costs its trust
  (roughly how unlikely that failure is). clingo minimises the total cost.

| sensor | trust | why |
| --- | --- | --- |
| `ec` | 5 | the controller that actually runs the battery and charger |
| `trend` | 3 | charge measured over minutes; inherits from its source |
| `acpi_bat`, `acpi_ac` | 2 | firmware methods; break on bad resumes |
| `ucsi` | 1 | USB-C status; seen stale after unplugging |
| `firmware` (cause) | 3 | one fault in the firmware can corrupt all three |

### Worked example: 2026-10-18

| sensor | claimed |
| --- | --- |
| acpi_bat | battery absent (and `_STA` failing) |
| acpi_ac | (`_PSR` failing) |
| ucsi | AC on |
| ec | AC off, battery present, discharging, 88 % |
| trend | discharging (from EC) |

The firmware evidence makes `acpi_bat` and `acpi_ac` abnormal and the
firmware broken for free, which also covers `ucsi`. Total cost: just the
evidence. The truth comes out as AC off, discharging, 88 % per the EC. See
`tests/cases/incident-2026-10-17.lp`.

Without the EC (not running as root), nothing trustworthy reports a charge
level, so `shown_pct` isn't certain and the bar shows "?", not "0 %".

## Links: observe and advise

`rules/links.lp` derives problems (roam bursts, repeated drops, lost
beacons, weak or fading signal, an MLO association down to one link, no
internet). From those it derives a `link_state` (ok, at_risk or down), and
from that state and the configured uplinks it derives advice (prepare a
fallback, turn on the phone hotspot). Fallbacks are ranked in the rules.
See [links.md](links.md).

## Cost

A check runs a few small commands (`iw`, `nmcli`, `ectool`, `journalctl`
from a cursor) and a clingo solve over about 50 facts, which takes
milliseconds. The daemon runs at `Nice=10`. Nothing scans for Wi-Fi: it uses
NetworkManager's cached scan results.

## Ideas

- **Temporal rules** with telingo, instead of passing ages in as numbers.
- **Prediction**: learn which hours or places see roam bursts, from the
  history, and pre-warm the fallback.
- **Self-repair as an experiment**: when the firmware is blamed, reload the
  battery driver, record whether that fixed it, and feed the result back as
  evidence.
- **More domains**: thermals (PROCHOT clamps, see Framework issue #269), NPU
  firmware boot timeouts, suspend failures.
