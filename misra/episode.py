"""Turn a snapshot into a published episode: the evidence, the reasoning, the story.

    misra episode SNAPSHOT_DIR SLUG [--repo DIR]

writes docs/incidents/<date>-<slug>/ in the repo:
    facts.lp       the snapshot's facts, scrubbed to the power evidence
    explain.png    how the rules answered (misra explain), light palette
    README.md      a skeleton to write the story into (what was seen, what was wrong,
                   how misra saw it, status, fixes)
and adds a row to docs/incidents/README.md, the catalogue.

Scrubbing keeps only the facts below and drops everything else, on purpose: link
facts carry network and uplink names, and deep captures (ACPI tables, DMI, the
journal) carry serial numbers, UUIDs and MAC addresses. Read the result before
committing; the public-repo guard checks it again.
"""

import re
import time
from pathlib import Path

from .explain import render

# what an episode may publish: the power evidence and what happened around it
KEEP = {"sensor", "trust", "claim", "reading", "acpi_error", "acpi_unreadable",
        "derived_from", "resumed", "first_tick"}
INDEX_HEAD = """# Incidents

Episodes misra was built from or caught, each with its evidence (`facts.lp`, scrubbed
to the power readings), how the rules answered (`explain.png`, drawn by
`misra explain`), and the story. Re-run any of them: `misra explain <folder>/facts.lp`.

| Date | Episode | Status | In short |
| --- | --- | --- | --- |
"""


def scrub(text):
    """Keep only whitelisted facts, one per line; comments and everything else go."""
    out = []
    for stmt in re.findall(r"[a-z_]+(?:\([^()]*(?:\([^()]*\))*[^()]*\))?\.", text):
        name = stmt.split("(", 1)[0].rstrip(".")
        if name in KEEP:
            out.append(stmt)
    return "\n".join(out) + "\n"


def make(snapshot, slug, repo):
    snapshot, repo = Path(snapshot), Path(repo)
    facts = scrub((snapshot / "facts.lp").read_text())
    m = re.match(r"(\d{4})(\d{2})(\d{2})", snapshot.name)
    date = f"{m[1]}-{m[2]}-{m[3]}" if m else time.strftime("%Y-%m-%d")
    folder = repo / "docs/incidents" / f"{date}-{slug}"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "facts.lp").write_text(f"% {date} {slug}: power facts from a misra snapshot (scrubbed)\n" + facts)
    _, res = render([facts], folder / "explain.png", mode="light", title=f"{date} {slug}")
    readme = folder / "README.md"
    if not readme.exists():
        readme.write_text(f"""# {slug.replace('-', ' ').capitalize()}

**Date:** {date}. **Status:** open.

## What was seen

## What was actually wrong

## How misra saw it

![The evidence and the rules' answer](explain.png)

{res.models} best answer{'s' if res.models != 1 else ''} at cost {res.cost[0] if res.cost else 0}.
Evidence: [facts.lp](facts.lp) (re-run: `misra explain facts.lp`).

## Fixes and commits

## Next steps
""")
    index = repo / "docs/incidents/README.md"
    rows = index.read_text() if index.exists() else INDEX_HEAD
    link = f"[{slug}]({folder.name}/)"
    if link not in rows:
        rows = rows.rstrip("\n") + f"\n| {date} | {link} | open | |\n"
    index.write_text(rows)
    return folder
