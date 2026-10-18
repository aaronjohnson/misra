"""Events from the kernel and wpa_supplicant logs: sleep and resume, failing
ACPI methods, and Wi-Fi associations, drops and beacon loss.

Reads the journal incrementally from a cursor, so each tick only parses
what's new.
"""

import json
import re
import subprocess
from dataclasses import dataclass, field

# ---- Recognising lines ----

SLEEP_ENTRY = re.compile(r"PM: (suspend entry|hibernation: hibernation entry)")
RESUME = re.compile(r"PM: (suspend exit|hibernation: hibernation exit)")
ACPI_ABORT = re.compile(r"Aborting method \\(\S+) due to")

ASSOC = re.compile(r"^\S+: (\[link \d+\] .*\(assoc\)|associated)$")
DROP_REMOTE = re.compile(r"^\S+: (deauthenticated|disassociated) from \S+ \(Reason: (\d+)")
DROP_LOCAL = re.compile(r"^\S+: (deauthenticating|disassociating) from \S+ by local choice")
BEACON_LOSS = re.compile(r"CTRL-EVENT-BEACON-LOSS")
HANDSHAKE = re.compile(r"4WAY_HANDSHAKE_TIMEOUT|reason=15\b")


def acpi_kind(device):
    if re.fullmatch(r"BAT\d*", device):
        return "battery"
    if re.fullmatch(r"ACAD|AC\d*|ADP\d*", device):
        return "adapter"
    return "other"


def classify(msg, source):
    """One log message -> list of (kind, detail). Kinds: sleep, resume,
    acpi_error, assoc, drop_remote, drop_local, beacon_loss, handshake_timeout."""
    out = []
    if source == "kernel":
        if SLEEP_ENTRY.search(msg):
            out.append(("sleep", None))
        if m := RESUME.search(msg):
            out.append(("resume", "hibernate" if "hibernation" in m.group(1) else "suspend"))
        if m := ACPI_ABORT.search(msg):
            parts = m.group(1).split(".")
            if len(parts) >= 2:
                out.append(("acpi_error", (acpi_kind(parts[-2]), parts[-2], parts[-1])))
        if ASSOC.match(msg):
            out.append(("assoc", None))
        if m := DROP_REMOTE.match(msg):
            out.append(("drop_remote", int(m.group(2))))
            if m.group(2) == "15":
                out.append(("handshake_timeout", None))
        if DROP_LOCAL.match(msg):
            out.append(("drop_local", None))
    else:
        if BEACON_LOSS.search(msg):
            out.append(("beacon_loss", None))
        elif "4WAY_HANDSHAKE_TIMEOUT" in msg and "CTRL-EVENT-DISCONNECTED" not in msg:
            out.append(("handshake_timeout", None))
    return out


# ---- Reading the journal ----

@dataclass
class Journal:
    cursor: str | None = None
    acpi_errors: set = field(default_factory=set)   # since the last sleep entry
    events: list = field(default_factory=list)      # (realtime s, kind, detail), last hour
    last_resume: tuple | None = None                # (realtime s, kind)

    def read_new(self):
        """Parse entries since the cursor. Returns the resumes seen."""
        args = ["journalctl", "-o", "json", "--no-pager",
                "_TRANSPORT=kernel", "+", "_SYSTEMD_UNIT=wpa_supplicant.service"]
        args += ["--after-cursor", self.cursor] if self.cursor else ["-b"]
        try:
            p = subprocess.run(args, capture_output=True, text=True, timeout=20)
        except (OSError, subprocess.TimeoutExpired):
            return []
        resumes = []
        for line in p.stdout.splitlines():
            try:
                e = json.loads(line)
            except ValueError:
                continue
            self.cursor = e.get("__CURSOR", self.cursor)
            msg = e.get("MESSAGE")
            if not isinstance(msg, str):
                continue
            t = int(e.get("__REALTIME_TIMESTAMP", 0)) / 1e6
            source = "kernel" if e.get("_TRANSPORT") == "kernel" else "wpa"
            for kind, detail in classify(msg, source):
                self.note(t, kind, detail, resumes)
        return resumes

    def note(self, t, kind, detail, resumes):
        if kind == "sleep":
            # Errors from before a sleep say nothing about the next wake.
            self.acpi_errors.clear()
        elif kind == "resume":
            self.last_resume = (t, detail)
            resumes.append((t, detail))
        elif kind == "acpi_error":
            self.acpi_errors.add(detail)
        else:
            self.events.append((t, kind, detail))

    def prune(self, now, keep=3600):
        self.events = [e for e in self.events if now - e[0] <= keep]

    def event_facts(self, now):
        """(kind, age in seconds) for the rules."""
        return [(kind, max(0, int(now - t))) for t, kind, _ in self.events]
