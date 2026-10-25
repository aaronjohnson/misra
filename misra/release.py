"""`misra release-plan REPO`: a release tag or the branch tip, for land's Bump step.

Reads the repo's CHANGELOG (newest "## <version> · …" heading) and its tags;
rules/release/release.lp decides. Prints JSON: mode (tag | tip), plan, tag,
heading, reason. land does the tagging and points ~/nixos at the result.
"""

import json
import re
import subprocess
from pathlib import Path

from .facts import atoms
from .reason import RULES, solve

VERSION = re.compile(r"^##\s+v?(\d+\.\d+(?:\.\d+)?)\b")


def _git(repo, *args):
    p = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    return p.stdout.split() if p.returncode == 0 else []


def _q(s):
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def newest(repo):
    """(version, heading) from the CHANGELOG's newest entry, or (None, heading)."""
    for name in ("CHANGELOG.md", "CHANGELOG.txt", "CHANGELOG"):
        f = Path(repo) / name
        if f.exists():
            for line in f.read_text(errors="replace").splitlines():
                if line.startswith("## "):
                    m = VERSION.match(line)
                    return (m.group(1) if m else None), line[3:].strip()
    return None, ""


def plan(repo):
    version, heading = newest(repo)
    want = f"v{version}" if version else None
    facts = [f"tag({_q(t)})." for t in _git(repo, "tag")]
    facts += [f"head_tag({_q(t)})." for t in _git(repo, "tag", "--points-at", "HEAD")]
    if want:
        facts.append(f"want_tag({_q(want)}).")
    c = solve(["\n".join(facts)], RULES / "release").certain
    p = next((x for (x,) in atoms(c, "plan")), "tip")
    reason = {
        "new_tag": f"CHANGELOG says {version}: tag {want} here and take the tag",
        "at_tag": f"{want} is already on this commit: take the tag",
        "stale": f"{want} is older than this commit and the CHANGELOG wasn't bumped: staying on the tip",
        "tip": "no version in the CHANGELOG: the branch tip",
    }[p]
    return {"mode": next((x for (x,) in atoms(c, "mode")), "tip"), "plan": p,
            "tag": want, "heading": heading, "reason": reason}


def main(repo):
    print(json.dumps(plan(repo)))
    return 0
