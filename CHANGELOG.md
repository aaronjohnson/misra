# Ship's log of the misra

Kept by the watch. Newest entry on top. A version is a port of call: a minor
number when a new set of rules comes aboard, a patch for running repairs.

## 0.7.1 · 25 October 2026 · the harbour lights on the chart

A port of call now gets a notice in the harbour too: `misra release-notes`
turns this log into a GitHub release (the entry's heading for a title, every
entry since the last tag for the notes), and land offers to publish it as a
step of its own, since a public notice is the captain's call, not the watch's.

## 0.7.0 · 25 October 2026 · late, the fan quiet again

Ports of call get a name on the chart. When land carries a new version to the
system, `rules/release/` reads this log's newest heading and decides: a new
version is tagged where it lies (signed, pushed) and the system's flake points
at the tag, not the moving tip of the branch; a version already tagged here
is taken as it is; and if commits came after the tag without a new heading,
the tag stays put (a checkpoint isn't moved) and the system takes the tip,
saying why. Repos whose logs keep folios or field reports instead of version
numbers stay on their tips. Several machines can then sail on the same
release, and going back is pointing at an earlier one.

## 0.6.0 · 25 October 2026 · still night, the watch writes the last line

"Nothing left to land or ship" used to be painted on the bulkhead. Now the
watch says it, and says more: how many steps held today, that the running
system matches the charts, which repos have work below decks that landing
won't touch, which are behind the remote, which drafts went stale, and which
steps were waved off this time. `rules/land/queue.lp` reads the deck's queue
alongside its log; a question still up, or a step still running, means the
watch keeps quiet and lets the deck ask.

## 0.5.0 · 25 October 2026 · night watch, clear

When the log says a tool was missing ("firebase: command not found", which
is how three of the afternoon's deploys went), the watch now says how to
fit it rather than only that it was lost overboard: add the package to that
repo's devShell, run the step inside the devShell that already has it, or
give a repo with no flake one. It checks the repo's own flake and .ship on
disk to know which. Every answer is a rule in `rules/land/`, tested on the
afternoon it came from.

## 0.4.0 · 25 October 2026 · clearing, the evening watch

A boarding officer at the gangway. Before Claude Code runs a shell command,
`misra check-command` reads it and `rules/commands/` decides whether you
should be asked first: anything from a registry or a URL (npm, npx, pip,
cargo, go, gem, mix archives, flakes from outside nixpkgs, nix profiles),
outside code cloned under ~ (which Claude Code trusts), and writes to where a
stowaway hides: ~/.ssh, shell startup files, autostart, Claude's own hooks.
A download piped straight into a shell isn't asked about; it's refused.

The officer may only stop a passenger, never wave one through: with no
concern the officer says nothing and the usual prompts stand. Python reads the
command (heredocs are cargo, not crew; `bash -c`, `sudo`, `nix shell -c` are
looked inside); clingo decides, and every refusal says why. Its tests include
the very commands of the day it was built, which it must let pass.

## 0.3.0 · 25 October 2026 · rain easing, a long afternoon in the log

The watch now reads its own log. `rules/land/` takes the F12 deck's record of
the day (each commit, bump, push, switch and check, and whether it held) and
says what it adds up to: which failures a later success has fixed, which are
still open, the change most likely to blame, and one verdict for the page.
Its first case is this afternoon: a switch failed for want of a position, a
build failed for a colon on the crew list, and three bumps later the log reads
"all clear: 3 failed, all fixed". `misra land-log FILE` answers as JSON; the
daemon doesn't load these rules.

## 0.2.3 · 25 October 2026 · rain easing

The sailor's name went on the crew list with a colon in it ("misra: fetches
the weather"), and the crew list is a passwd file, where a colon splits the
fields. The ship wouldn't build until the clerk wrote "misra weather fetcher".

## 0.2.2 · 25 October 2026 · moderate rain, 0.9 mm, the lamps still lit

The barometer read 100 % cloud and rain, and nobody on the bridge heard it:
the sailor kept his readings in a locked locker (`/run/private`, where a
throwaway crewman's things go) that even the watch, sworn off all its
privileges, couldn't open. He now has a name on the crew list
(`misra-weather`, a plain system user) and pins his readings where the watch
can see them. Still no shore leave for the watch itself.

## 0.2.1 · 25 October 2026 · still raining

The barometer's sailor no longer reports for duty, and fails, before the
captain has written down where we are: without a location the weather unit
now stands down quietly.

## 0.2.0 · 25 October 2026 · Vancouver WA, overcast, light rain, 0.6 mm

Fitted a barometer. `rules/sky.lp` reads the weather and calls a grey day:
rain, fog, storm, or an overcast too leaden to light the cabin. The lamps on
the bridge (the bar, kitty, GTK) now go dark on such a day, noon or not, and
the log says why (`grey(rain)`, `grey(overcast)`). Once grey, the watch keeps
it grey through a passing gap in the clouds.

The barometer hangs outside the hull. A separate `misra-weather` unit, a
throwaway sailor with leave to go ashore and nothing else, fetches Open-Meteo
every quarter hour and after every resume. The daemon itself still never
touches the network. Our position is kept in the captain's cabin
(`/var/lib/misra/weather.toml`), never in the public charts, and handed to
the unit as a sealed credential, rounded to two decimals.

Opt in: `services.misra.weather.enable = true;`

## 0.1.0 · 18–25 October 2026 · fair, the lid switch dead after a hibernate

Launched. Five witnesses aboard (firmware battery and adapter, USB-C, the EC,
and the trend of the charge itself) and clingo to weigh them when they
disagree. Born of the night of 17 October, when the firmware swore the
battery had gone overboard and the bar showed 0 % and a 100 W charger for an
hour.

- Cross-checks power and network sensors every 30 s and after every resume.
- Watches the Wi-Fi link and advises the next uplink; never switches.
- `ops/hw-snapshot` records the hardware's state before a reboot clears it.
- Alerts carry a chart of what each power sensor claimed.
- `misra explain` draws how the rules reached their answer; episodes publish
  a snapshot with its trace.
