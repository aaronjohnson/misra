# Vehicle power (planned)

A vehicle's auxiliary battery runs the base station: router, Starlink,
radios. How long it lasts decides how long those links stay up, so it
deserves the same treatment as the laptop's battery: several witnesses,
cross-checked, with a fault shown as a fault and not as a number.

## Witnesses

| sensor | what it reports | how misra reads it |
| --- | --- | --- |
| battery shunt (e.g. Victron SmartShunt) | current in and out, state of charge by counting amp-hours | Victron GX: MQTT or Modbus TCP; or Bluetooth "Instant Readout" broadcasts; or VE.Direct over USB |
| the battery's own BMS (lithium) | its own state of charge, cell voltages, protection state | Bluetooth, if the battery offers it |
| DC-DC charger (e.g. Victron Orion) | charging from the alternator, or not | GX or Bluetooth |
| solar charge controller | solar input, charging state | GX or Bluetooth |
| resting voltage | rough state of charge after the battery has been idle | the shunt's voltage, when current has been near zero for an hour |

A GX device (Cerbo GX, or Venus OS on a Raspberry Pi) collects the Victron
devices and publishes them all on a local MQTT broker. That's the easiest
path: one connection, push updates.

## Cross-checks worth having

Same method as the laptop: each sensor works or doesn't, minimal blame.

- **Shunt drift.** A shunt counts amp-hours and drifts until it sees a full
  charge. If the shunt says 60 % and the BMS and resting voltage both say
  about 40 %, believe the pair and say the shunt needs a full charge to resync.
- **Charging that isn't.** The DC-DC charger says it's charging, but the shunt
  shows net discharge: either the charger is limited (hot, low alternator
  voltage) or the load is bigger than the charge. That's a problem, not a fault.
- **Silent sensors.** No update for a few minutes means no claim, not a
  stale one (the same lesson as the laptop's USB-C report).

## Runway

The useful number isn't the charge level, it's **how long until the links go
dark**:

```
runway_min = usable_Ah_left / net_discharge_A * 60
```

computed in the collector from the certain state of charge and a smoothed
current. The rules decide what to do with it:

```
problem(runway_short) :- runway(M), M < 120, powers(aux,L), active(L).
advise(start_engine)  :- problem(runway_short), charger(dcdc), not charging(dcdc).
advise(shed,starlink) :- problem(runway_short), not need(internet).
```

The alert says something like "Starlink and the router have about 1h50 on
the aux battery", in time to act.

## Where it runs

The laptop isn't always in the vehicle, so this runs on the vehicle's own
observer (see "Phase 4" in [roadmap.md](roadmap.md)). The laptop reads the
vehicle's conclusions when it's connected.

## Privacy

GPS position from the router and battery serial numbers stay in local
snapshots, like everything else in [privacy.md](privacy.md). Position never
goes into the rules as coordinates, only as labels you define ("home",
"camp").
