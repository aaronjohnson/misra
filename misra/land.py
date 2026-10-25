"""`misra land-log`: what the F12 deck's log adds up to (rules/land/).

The deck writes its log as entry/4 facts, plus missing(N, Cmd) for a row whose
output said "Cmd: command not found". This module adds what the disk can tell
about each repo involved, so the rules can say how to fix it:

  has_flake(Repo).          the repo has a flake.nix
  shell_has(Repo, Cmd).     its devShell names the package that provides Cmd
  ship_in_shell(Repo).      its .ship runs commands inside `nix develop`
  provides(Cmd, Package).   the nixpkgs package that provides Cmd

Repos are found by name under ~/src, then ~ (nixos, dotfiles).
"""

import json
import os
import re
from pathlib import Path

from .facts import atoms
from .reason import RULES, solve

# commands whose nixpkgs package has another name; anything else: the same name
PACKAGE = {
    "firebase": "firebase-tools", "gcloud": "google-cloud-sdk", "gsutil": "google-cloud-sdk",
    "node": "nodejs", "npm": "nodejs", "npx": "nodejs", "python": "python3",
    "stripe": "stripe-cli", "convert": "imagemagick", "magick": "imagemagick",
    "pdftoppm": "poppler-utils", "pdfinfo": "poppler-utils", "lualatex": "texliveFull",
    "pdfjam": "texliveFull", "gs": "ghostscript", "wl-copy": "wl-clipboard",
    "wl-paste": "wl-clipboard", "v4l2-ctl": "v4l-utils", "rsvg-convert": "librsvg",
}


def _q(s):
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def repo_dir(name, home):
    for d in (Path(home) / "src" / name, Path(home) / name):
        if (d / ".git").exists():
            return d
    return None


def enrich(text, home=None):
    """Facts about the repos and commands that the log's missing/2 rows name."""
    home = home or os.path.expanduser("~")
    out = []
    for n, cmd in re.findall(r'missing\((\d+),"((?:[^"\\]|\\.)*)"\)', text):
        pkg = PACKAGE.get(cmd, cmd)
        out.append(f"provides({_q(cmd)},{_q(pkg)}).")
        m = re.search(rf'entry\({n},\w+,\w+,"((?:[^"\\]|\\.)*)"\)', text)
        if not m:
            continue
        repo = m.group(1)
        d = repo_dir(repo, home)
        if d is None:
            continue
        flake = d / "flake.nix"
        if flake.exists():
            out.append(f"has_flake({_q(repo)}).")
            if re.search(rf"\b(pkgs\.)?{re.escape(pkg)}\b", flake.read_text()):
                out.append(f"shell_has({_q(repo)},{_q(cmd)}).")
        ship = d / ".ship"
        if ship.exists() and "nix develop" in ship.read_text():
            out.append(f"ship_in_shell({_q(repo)}).")
    return sorted(set(out))


def conclude(text, home=None):
    res = solve([text, "\n".join(enrich(text, home))], RULES / "land")
    c = res.certain
    return {
        "verdict": next((v for (v,) in atoms(c, "verdict")), None),
        "failures": next((n for (n,) in atoms(c, "failures")), 0),
        "open": sorted(n for (n,) in atoms(c, "open")),
        "fixed": {str(n): m for n, m in atoms(c, "first_fix")},
        "blame": {str(n): r for n, r in atoms(c, "blame")},
        "advice": {str(n): say(kind, repo, pkg) for n, kind, repo, pkg in atoms(c, "advise")},
        "status": next((s for (s,) in atoms(c, "status")), None),
        "headline": headline(c),
    }, res.unsat


def headline(c):
    """The deck's line when no question is up: rules/land/queue.lp's status and notes."""
    status = next((s for (s,) in atoms(c, "status")), None)
    done = next((d for (d,) in atoms(c, "done")), 0)
    tail = []
    if done:
        tail.append(f"{done} step{'s' if done != 1 else ''} done")
    if any(True for _ in atoms(c, "note", 1)):
        tail.append("running = ~/nixos")
    unstaged = [f"{r} ({n})" for k, r, n in atoms(c, "note", 3) if k == "unstaged"]
    behind = [f"{r} ↓{n}" for k, r, n in atoms(c, "note", 3) if k == "behind"]
    stale = [r for k, r in atoms(c, "note", 2) if k == "stale_draft"]
    if unstaged:
        tail.append("unstaged, not part of land: " + ", ".join(unstaged))
    if behind:
        tail.append("behind the remote: " + ", ".join(behind))
    if stale:
        tail.append("stale draft: " + ", ".join(stale))
    skipped = [f"{label} {repo}" for _, label, repo in atoms(c, "skipped", 3)]
    head = {
        "clear": "Nothing left to land or ship",
        "skipped_only": "Nothing queued; skipped this time: " + ", ".join(skipped),
        "broken": "Nothing queued, but ~/nixos doesn't build",
        "checking": "Checking whether a switch is needed…",
        "reading": "Reading repos…",
    }.get(status)
    if head is None:
        return None                      # running or a question is up: the deck says that
    return " · ".join([head] + tail)


def say(kind, repo, pkg):
    return {
        "add_to_shell": f"add {pkg} to {repo}'s flake devShell",
        "run_in_shell": f"{repo}'s devShell has {pkg}; run the step inside it (nix develop -c …)",
        "add_flake": f"{repo} has no flake: give it one with {pkg} in the devShell",
        "nix_shell": f"run it as nix shell nixpkgs#{pkg} -c …",
    }.get(kind, kind)


def main(path, home=None):
    out, unsat = conclude(Path(path).read_text(), home)
    print(json.dumps(out))
    return 1 if unsat else 0
