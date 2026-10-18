# Links and fallbacks

misra watches the network link and tells you, before it fails if it can,
which fallback is ready. It doesn't switch for you yet; see "Later".

## Telling misra about your networks

`/var/lib/misra/local.toml` (root-owned, not in Nix or git):

```toml
[[uplink]]
label = "home"                # what alerts and state.json call it
connection = "My Network"     # the NetworkManager connection name
role = "mlo"                  # mlo | wifi | starlink | phone_bt | phone_hotspot

[[uplink]]
label = "phone"
connection = "Phone Hotspot"
role = "phone_hotspot"

[[uplink]]
label = "truck"
connection = "STARLINK"
role = "starlink"
```

Only labels and roles reach the rules, snapshots and state. Connection
names and SSIDs stay in this file.

## Roles and order

| rank | role | why this order |
| --- | --- | --- |
| 0 | `mlo`, `wifi` | the primary link |
| 1 | `starlink` | no mobile data used; needs the dish powered and parked with sky view |
| 2 | `phone_bt` | Bluetooth tethering: its own network interface, so it can stay up next to Wi-Fi (slow, but switching to it is seamless) |
| 3 | `phone_hotspot` | the phone's Wi-Fi hotspot: the laptop has one Wi-Fi radio, so using it means leaving the current network |

Change the order in `rules/links.lp` (`role_rank`).

## What counts as trouble

| problem | rule |
| --- | --- |
| `roam_burst` | 3+ associations in 5 minutes (mesh nodes fighting over you) |
| `dropping` | 2+ drops by the access point, or failed handshakes, in 15 minutes |
| `beacons_lost` | 3+ missed beacons since the last check |
| `weak` | signal below -75 dBm |
| `fading` | signal down 10 dB or more in 5 minutes, and now below -67 dBm |
| `mlo_degraded` | on a multi-link network, but fewer than 2 links up |
| `no_internet` | associated, but NetworkManager sees no or limited connectivity |

## The phone

Linux can't use the "instant hotspot" that Pixel phones offer Chromebooks:
that's a Google protocol between Android and ChromeOS. What works instead:

- **Bluetooth tethering** (Settings, Network, Hotspot & tethering, Bluetooth
  tethering). Pair the phone once. NetworkManager can then bring up a
  Bluetooth network connection on demand, or keep it up as a standby with a
  higher route metric. Slow, but it sits next to Wi-Fi rather than replacing it.
- **Wi-Fi hotspot**: misra tells you when to turn it on (`enable_hotspot`)
  if nothing else is in range.

## Starlink (planned)

A Starlink dish parked nearby on auxiliary power is a fallback with its own
health data. Plan:

1. Add its Wi-Fi as an uplink with `role = "starlink"`. misra then sees it
   whenever its SSID is in NetworkManager's scan list.
2. A collector for the dish's local status API (gRPC on `192.168.100.1:9200`,
   as used by the community `starlink-grpc-tools`). Reachable only once
   connected. It reports obstruction, outage history and latency, which
   become facts like `starlink(obstructed)` and `starlink(outage_recent)`.
3. Rules that rank Starlink below the phone while it's obstructed or still
   booting.

## Later: acting, not only advising

- Bring up Bluetooth tethering automatically as a standby when the link is
  `at_risk`, and drop it again once it's `ok`.
- Switch Wi-Fi from the MLO profile to a single-band profile of the same
  network when `mlo_degraded` keeps recurring, as a recorded experiment.
- Any automatic action will be a derived `act(...)` atom, logged with the
  facts that led to it.
