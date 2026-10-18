# Roadmap

misra started as a laptop that couldn't tell whether it was charging. The
same method (collect each witness's claims, let the rules find the cheapest
consistent explanation, act only on what's certain) carries over to every
link and every power source a mobile setup depends on.

## Where things stand

| | status |
| --- | --- |
| Laptop power: ACPI, UCSI, EC, charge trend | running; first incident caught (2026-10-17) |
| Check after every resume, snapshots on new faults | running |
| Wi-Fi observation: roams, drops, beacons, fading, MLO | running; MLO link count not yet checked against a real multi-link session |
| Fallback advice: Starlink, phone Bluetooth, phone hotspot | rules written; needs `local.toml` and a paired phone |
| Bar, HUD read `state.json` | running |

## Phase 1: the vehicle as a base station

A vehicle with an auxiliary battery becomes the place the other links live.

1. **Factory hotspot, if the vehicle has one.** Many vehicles from about
   2018 on have a built-in 4G hotspot. Add it as a `wifi` uplink: free to try,
   but it usually runs only with the ignition on, and there's no status API, so
   misra sees only whether it's in range.
2. **A vehicle router on the aux battery.** MikroTik's vehicle line runs on
   12–30 V and has cellular modems and GPS. Starlink connects to its WAN port.
   RouterOS fails over between uplinks by itself; misra watches it through the
   REST API (`/rest/...`): which uplink is active, cellular signal and
   technology, interface errors, GPS position. New role: `router`, with the
   router reporting its own uplinks.
3. **Starlink's status** through the router: obstruction, outages, latency
   (see [links.md](links.md)).

Collector shape: `router.py` polls the REST API with a read-only user over
HTTPS, only while the router is reachable, and writes facts like
`router_uplink(starlink,active)` and `cell(signal,-95)`.

## Phase 2: vehicle power

The aux battery decides how long phase 1 keeps running. See
[power-vehicle.md](power-vehicle.md): Victron shunt, DC-DC charger and solar
controller as cross-checked witnesses, and a "runway" estimate that warns
before the router or dish goes dark.

## Phase 3: links by what they can carry

Today the rules pick the best fallback. Later links differ in what they can
do, not just how fast they are. Each link declares what it can carry, and
advice answers "what can carry this need right now":

```
carries(L,internet) :- uplink(L,R), internet_role(R).
carries(L,email)    :- uplink(L,winlink).
carries(L,position) :- uplink(L,aprs).
carries(L,text)     :- uplink(L,(aprs;meshtastic;winlink)).

advise(use,L,N) :- need(N), best_for(N,L).
advise(no_path,N) :- need(N), not carries(_,N).
```

| link | carries | collector |
| --- | --- | --- |
| Starlink, cellular, Wi-Fi | internet | router API, ModemManager, NetworkManager |
| AREDN mesh (amateur) | IP inside the mesh, sometimes internet | the node's status JSON |
| Winlink over HF/VHF (amateur) | email | Pat (Winlink client): its CLI or HTTP API |
| APRS (amateur) | position, short messages | Direwolf (software TNC) logs or KISS |
| LoRa / Meshtastic | short text | the node's serial API |

**Amateur radio links are advisory only.** Part 97 requires a licensed
control operator, so misra never transmits: it says which path exists and
what it can carry. A person decides and keys up.

## Phase 4: misra in more than one place

The laptop isn't always in the vehicle, so the vehicle needs its own
observer: misra on a small computer there (or in a RouterOS container),
publishing its `state.json` over MQTT. The laptop's misra treats the
vehicle's conclusions as one more sensor, trusted like any other and
cross-checked like any other.

## Throughout

- **Firmware as an experiment.** Each new BIOS (or router, modem, Victron
  firmware) gets the same reproduction (hibernate on battery and on AC,
  roam between nodes), with results kept per version.
- **Temporal rules** with telingo once trends need more than "now vs five
  minutes ago".
- **Acting, carefully.** Automatic actions only as derived `act(...)` atoms,
  logged with the facts behind them, starting with the reversible ones
  (bring up Bluetooth tethering as a standby).
