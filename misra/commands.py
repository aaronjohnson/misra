"""A shell command as facts, for rules/commands: should Claude Code ask first?

Claude Code runs `misra check-command` before every Bash command (a PreToolUse
hook). This module only reads the command; rules/commands/commands.lp decides.
The hook can ask or deny, never allow: with no concern it says nothing and the
normal permission prompts apply.

What the parser does, and no more:
  - drops heredoc bodies (a commit message that says "npm install" is text)
  - splits on | || && ; & and newlines, noting which segment pipes into which
  - unwraps prefixes to the real command: sudo, pkexec, doas, env A=B, time,
    exec, command, nohup, xargs, and `nix shell|develop ... -c`
  - reads `bash -c "..."` (and sh, zsh) and $(...) as commands of their own
  - classifies paths it writes to, where git clone puts a checkout, and flake
    references, since clingo has no string prefixes
"""

import json
import os
import re
import shlex

from .facts import fact


def _s(v):
    """Always a quoted ASP string: command words are text, even `npm`."""
    return '"' + str(v).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'

PREFIXES = {"sudo", "pkexec", "doas", "time", "exec", "command", "nohup", "nice", "xargs"}
# options of those prefixes that take a value (sudo -u amj, nice -n 10, xargs -I {})
VALUED = {"-u", "-g", "-C", "-D", "-h", "-p", "-r", "-t", "-U", "-n", "-I", "-L", "-P", "--user", "--group"}
SHELLS = {"sh", "bash", "zsh", "dash", "fish"}
SPLIT = {"|", "||", "&&", ";", "&", "\n"}

_HEREDOC = re.compile(r"<<-?\s*(['\"]?)(\w+)\1[^\n]*\n.*?\n\s*\2\s*(?=\n|$)", re.S)
_SUBST = re.compile(r"\$\(([^()]*)\)")
_PROCSUB = re.compile(r"<\(([^()]*)\)")


def _strip_heredocs(cmd):
    return _HEREDOC.sub(lambda m: m.group(0).split("\n", 1)[0], cmd)


def _tokens(cmd):
    lex = shlex.shlex(cmd, posix=True, punctuation_chars=";&|<>\n")
    lex.whitespace = " \t\r"          # newlines are punctuation: they end a command
    lex.whitespace_split = True
    lex.commenters = ""                # `#` comments only at a word's start (nixpkgs#x is a word)
    try:
        toks = list(lex)
    except ValueError:                 # unbalanced quotes: read it word by word
        toks = cmd.split()
    out, comment = [], False
    for t in toks:
        if comment and "\n" not in t:
            continue
        comment = t.startswith("#")
        if not comment:
            out.append(t)
    return out


def _segments(cmd):
    """[(words, redirects, piped_from_previous)] for one command line."""
    segs, words, redirs, piped, toks = [], [], [], False, _tokens(cmd)
    i = 0
    while i < len(toks):
        t = toks[i]
        if t in SPLIT or (t and set(t) <= set(";&|\n") and t not in ("&>", "&>>")):
            if words:
                segs.append((words, redirs, piped))
            words, redirs, piped = [], [], t.strip("\n") == "|"
        elif t in (">", ">>", ">|", "&>", "&>>") and i + 1 < len(toks):
            redirs.append(toks[i + 1])
            i += 1
        elif t in ("<", "<<", "<<<", "<&", ">&") and i + 1 < len(toks):
            i += 1
        else:
            words.append(t)
        i += 1
    if words:
        segs.append((words, redirs, piped))
    return segs


def _unwrap(words):
    """The real command inside prefixes; ('nested', text) for `bash -c TEXT`."""
    while words:
        name = os.path.basename(words[0])
        if name in PREFIXES or name == "env":
            words = words[1:]
            while words and (words[0].startswith("-") or (name == "env" and "=" in words[0])):
                words = words[2:] if words[0] in VALUED else words[1:]
        elif re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", words[0]):     # FOO=bar cmd
            words = words[1:]
        elif name == "nix" and len(words) > 2 and words[1] in ("shell", "develop") and "-c" in words:
            words = words[words.index("-c") + 1:]
        elif name in SHELLS and "-c" in words[1:]:
            k = words.index("-c")
            return ("nested", words[k + 1] if k + 1 < len(words) else "")
        else:
            return ("cmd", words)
    return ("cmd", [])


def _place(path, home, cwd):
    """Where a path points: ssh | shell_rc | claude | autostart | home | outside."""
    path = path.replace("$HOME", home).replace("${HOME}", home)
    if path == "~" or path.startswith("~/"):
        path = home + path[1:]
    p = os.path.normpath(os.path.join(cwd, path))
    rel = os.path.relpath(p, home)
    if rel.startswith(".."):
        return "outside"
    if rel == ".ssh" or rel.startswith(".ssh/"):
        return "ssh"
    if rel in (".bashrc", ".bash_profile", ".profile", ".zshrc", ".zprofile") or rel.startswith(".config/fish/"):
        return "shell_rc"
    if rel.startswith(".claude/settings") or rel == ".claude.json" or rel.startswith(".claude/hooks"):
        return "claude"
    if rel.startswith(".config/autostart") or rel.startswith(".config/systemd/user"):
        return "autostart"
    return "home"


def _flake(ref):
    """nixpkgs | local | remote, for a flake reference like github:o/r#x."""
    if ref.startswith(("nixpkgs#", "nixpkgs/", "github:NixOS/nixpkgs", "github:nixos/nixpkgs")) or ref == "nixpkgs":
        return "nixpkgs"
    if ref.startswith((".", "/", "~", "path:", "git+file:")) or ref.startswith("#"):
        return "local"
    return "remote"


def facts_for(cmd, cwd=None, home=None):
    home = home or os.path.expanduser("~")
    cwd = cwd or home
    out, n = [], [0]
    out.append("cwd_in_home." if _place(cwd, home, "/") != "outside" else "cwd_outside_home.")

    def walk(text):
        text = _strip_heredocs(text)
        # $(...) and <(...) are commands too; <(curl URL) feeds a download as a file
        for m in _PROCSUB.finditer(text):
            first = walk(m.group(1))
            out.append(fact("procsub", first))
        for m in _SUBST.finditer(text):
            walk(m.group(1))
        text = _PROCSUB.sub(" PROCSUB ", _SUBST.sub(" SUBST ", text))
        first, prev = None, None
        for words, redirs, piped in _segments(text):
            kind, rest = _unwrap(words)
            if kind == "nested":
                i = walk(rest)
            else:
                if not rest:
                    continue
                i = n[0]
                n[0] += 1
                name = os.path.basename(rest[0])
                out.append(fact("seg", i))
                out.append(f"name({i},{_s(name)}).")
                for k, a in enumerate(rest[1:]):
                    out.append(f"arg({i},{k},{_s(a)}).")
                    if re.match(r"https?://", a):
                        out.append(fact("url", i))
                if any(re.search(r"\.(py|sh|bash|rb|pl|js|mjs|ts)$", a) for a in rest[1:]):
                    out.append(fact("script_file", i))
                if name == "tee":
                    redirs = redirs + [a for a in rest[1:] if not a.startswith("-")]
                if name == "nix":
                    for a in rest[2:]:
                        if a in ("--", "-c", "--command"):     # the rest belongs to the program run
                            break
                        if not a.startswith("-") and (":" in a or "#" in a):
                            out.append(fact("flake", i, _flake(a)))
                if name == "git" and "clone" in rest:
                    pos = [a for a in rest[rest.index("clone") + 1:] if not a.startswith("-")]
                    if pos:
                        dest = pos[1] if len(pos) > 1 else re.sub(r"\.git$", "", pos[0].rstrip("/").split("/")[-1].split(":")[-1])
                        out.append(fact("clone_to", i, "home" if _place(dest, home, cwd) != "outside" else "outside"))
                for r in redirs:
                    if r not in ("/dev/null", "&1", "&2"):
                        out.append(fact("writes", i, _place(r, home, cwd)))
            if piped and prev is not None and i is not None:
                out.append(fact("pipe", prev, i))
            if first is None:
                first = i
            prev = i
        return first

    walk(cmd)
    return out


REASONS = {
    "pipe_to_shell": "pipes a download straight into a shell or interpreter",
    "download_run": "runs a download as a script (<(curl …))",
    "js_install": "installs packages from npm (install scripts are off, the code still comes from npm); a flake devShell pins it",
    "js_run_fresh": "runs a package fetched fresh from npm (npx / dlx / bunx)",
    "pip_install": "installs from PyPI; a flake devShell pins Python packages",
    "cargo_install": "builds and installs a crate from crates.io",
    "go_install": "builds and installs a Go module from the network",
    "gem_install": "installs a Ruby gem",
    "mix_install": "installs a Mix archive or escript from the network",
    "nix_remote": "runs or builds a flake from outside nixpkgs",
    "nix_profile": "installs into a nix profile, outside any flake",
    "clone_in_home": "clones outside code under ~, which Claude Code trusts; /usr/src keeps the trust prompt",
    "writes_ssh": "writes into ~/.ssh",
    "writes_shell_rc": "writes a shell startup file",
    "writes_claude": "writes Claude Code's own settings or hooks",
    "writes_autostart": "writes an autostart entry or a user systemd unit",
}


def check(hook_input, home=None):
    """Claude Code's PreToolUse JSON in; the hook's answer out (None: no opinion)."""
    from .facts import atoms
    from .reason import RULES, solve
    if hook_input.get("tool_name") != "Bash":
        return None
    cmd = (hook_input.get("tool_input") or {}).get("command") or ""
    res = solve(facts_for(cmd, hook_input.get("cwd"), home), RULES / "commands")
    c = res.certain
    decision = next((d for (d,) in atoms(c, "decision")), None)
    if decision is None:
        return None
    why = [w for (w,) in atoms(c, "deny")] if decision == "deny" else [w for (w,) in atoms(c, "ask")]
    return {"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": decision,
        "permissionDecisionReason": "misra: this command " + "; and ".join(REASONS.get(w, w) for w in why) + ".",
    }}


def main(stdin):
    out = check(json.load(stdin))
    if out:
        print(json.dumps(out))
    return 0
