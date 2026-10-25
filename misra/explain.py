"""Draw how the power rules reached their answer: the evidence and the explanation.

One panel per optimal answer set (several when they tie), side by side as small
multiples on the same grid:

                 ac    battery   flow          %
    truth        on    present   charging          <- what this answer believes
                 2     1         1                 <- how many working sensors back it
    ec       5   off   present   discharging   88  <- each sensor's claims, most trusted first
    ucsi     1   on                                   faint row: abnormal in this answer,
    ...                                               the reason in the right margin

A claim in red contradicts the answer's truth: the evidence the answer had to
explain away. Where tied answers differ, the cells are marked: that's what misra
shows as "unknown". Under each panel: what it blamed and what it cost.

    misra explain case.lp ...    from fact files (a snapshot's facts.lp, a test case)
    misra explain                from a live tick (as root to include the EC)
"""

from dataclasses import dataclass
from pathlib import Path

import clingo
from PIL import Image, ImageDraw, ImageFont

from .reason import RULES, solve

PROPS = ["ac", "battery", "flow"]
PALETTE = {
    "dark":  {"bg": "#002b36", "ink": "#93a1a1", "strong": "#eee8d5", "faint": "#405e66", "label": "#839496"},
    "light": {"bg": "#fdf6e3", "ink": "#586e75", "strong": "#073642", "faint": "#c9c2ad", "label": "#657b83"},
}
RED, VIOLET, CYAN, YELLOW = "#dc322f", "#6c71c4", "#2aa198", "#b58900"


@dataclass
class Evidence:
    sensors: list          # [(name, trust)], most trusted first
    claims: dict           # (sensor, prop) -> value
    pct: dict              # sensor -> percent
    acpi_bad: set          # sensors with a failing firmware method (observed)
    derived: dict          # sensor -> source
    causes: dict           # sensor -> shared cause (from the rules)
    cause_trust: dict      # cause -> cost


def evidence(facts, rules_dir=RULES):
    """Read the facts the way clingo does (pools and all), plus the rules' cause/2."""
    ctl = clingo.Control(["--warn=none"])
    for f in sorted(Path(rules_dir).glob("*.lp")):
        ctl.load(str(f))
    ctl.add("base", [], "\n".join(facts))
    ctl.ground([("base", [])])
    fact = {}
    for a in ctl.symbolic_atoms:
        if a.is_fact:
            fact.setdefault(a.symbol.name, []).append([str(x).strip('"') for x in a.symbol.arguments])
    trust = {s: int(w) for s, w in fact.get("trust", [])}
    sensors = sorted({s for (s,) in fact.get("sensor", [])}, key=lambda s: (-trust.get(s, 0), s))
    kind_of = {"battery": "acpi_bat", "adapter": "acpi_ac"}
    bad = {kind_of[k] for k, *_ in fact.get("acpi_error", []) if k in kind_of}
    bad |= {kind_of[k] for (k,) in fact.get("acpi_unreadable", []) if k in kind_of}
    return Evidence(
        sensors=[(s, trust.get(s, 0)) for s in sensors],
        claims={(s, p): v for s, p, v in fact.get("claim", [])},
        pct={s: v for s, k, v in fact.get("reading", []) if k == "pct"},
        acpi_bad=bad,
        derived={s: t for s, t in fact.get("derived_from", [])},
        causes={s: c for s, c in fact.get("cause", [])},
        cause_trust={c: int(w) for c, w in fact.get("cause_trust", [])},
    )


def answer(model):
    """An answer set -> (truth {prop: value}, support {prop: n}, faulty set, blamed set)."""
    truth, support, faulty, blamed = {}, {}, set(), set()
    for a in model:
        args = [str(x) for x in a.arguments]
        if a.name == "truth":
            truth[args[0]] = args[1]
        elif a.name == "support":
            support[args[0]] = int(args[2])
        elif a.name == "faulty":
            faulty.add(args[0])
        elif a.name == "blamed":
            blamed.add(args[0])
    return truth, support, faulty, blamed


def reason_for(s, ev, faulty, blamed):
    """Why sensor s is abnormal in this answer, in the margin's words."""
    if s in ev.acpi_bad:
        return "ACPI error (seen)", RED
    if s in ev.derived and ev.derived[s] in faulty:
        return f"from {ev.derived[s]}", None
    if ev.causes.get(s) in blamed:
        return f"{ev.causes[s]} broke", YELLOW
    return f"on its own: {dict(ev.sensors).get(s, '?')}", None


def render(facts, path, mode="dark", scale=2, title=""):
    res = solve(facts)
    ev = evidence(facts)
    pal = PALETTE.get(mode, PALETTE["dark"])
    S = scale
    font = ImageFont.load_default(size=11 * S)
    bold = ImageFont.load_default(size=12 * S)
    small = ImageFont.load_default(size=9 * S)

    answers = [answer(m) for m in res.optimal] if not res.unsat else []
    # where tied answers differ: those cells and rows get a mark
    differ_truth = {p for p in PROPS if len({a[0].get(p) for a in answers}) > 1}
    differ_rows = {s for s, _ in ev.sensors if len({s in a[2] for a in answers}) > 1}

    cols = [("", 92), ("ac", 44), ("battery", 66), ("flow", 92), ("%", 34), ("", 118)]
    panel_w = sum(w for _, w in cols)
    row_h, gap = 20, 28
    rows = 3 + len(ev.sensors)
    panel_h = 22 + rows * row_h + 34
    n = max(1, len(answers))
    per_row = min(n, 2)                    # small multiples wrap two to a row
    grid_rows = (n + per_row - 1) // per_row
    W = 24 + per_row * panel_w + (per_row - 1) * gap + 24
    H = 54 + grid_rows * (panel_h + 12) + 20
    img = Image.new("RGB", (W * S, H * S), pal["bg"])
    d = ImageDraw.Draw(img)

    head = title or "power rules: the evidence and the answer"
    d.text((24 * S, 14 * S), head, font=bold, fill=pal["strong"])
    if res.unsat:
        sub = "no consistent answer at all (the facts contradict the physics)"
    elif n == 1:
        sub = f"one best answer · cost {res.cost[0] if res.cost else 0}"
    else:
        sub = f"{n} answers tie at cost {res.cost[0] if res.cost else 0}: misra shows what they disagree on as unknown"
    d.text((24 * S, 32 * S), sub, font=small, fill=VIOLET if n > 1 else pal["label"])

    def x_of(i, ox):
        return ox + sum(w for _, w in cols[:i])

    for k, (truth, support, faulty, blamed) in enumerate(answers):
        ox = 24 + (k % per_row) * (panel_w + gap)
        y = 54 + (k // per_row) * (panel_h + 12)
        if n > 1:
            d.text((ox * S, y * S), f"answer {k + 1}", font=small, fill=VIOLET)
        y += 18
        # column heads
        for i, (name, _) in enumerate(cols[1:5], start=1):
            d.text((x_of(i, ox) * S, y * S), name, font=small, fill=pal["label"])
        y += row_h - 4
        # the answer's truth, and its support underneath
        d.text((ox * S, y * S), "truth", font=bold, fill=pal["strong"])
        for i, p in enumerate(PROPS, start=1):
            v = truth.get(p, "?")
            x = x_of(i, ox)
            d.text((x * S, y * S), v, font=bold, fill=pal["strong"])
            if p in differ_truth:   # tied answers disagree here: unknown
                tw = d.textlength(v, font=bold)
                d.line([(x * S, (y + 15) * S), (x * S + tw, (y + 15) * S)], fill=VIOLET, width=2 * S)
        y += row_h - 2
        for i, p in enumerate(PROPS, start=1):
            if p in support:   # no sensor backing a value: missing evidence, not a conflict
                n_s = support[p]
                d.text((x_of(i, ox) * S, y * S),
                       "no sensor" if n_s == 0 else f"{n_s} sensor{'s' if n_s != 1 else ''}",
                       font=small, fill=pal["faint"] if n_s == 0 else pal["label"])
        y += row_h - 4
        d.line([(ox * S, y * S), ((ox + panel_w - 8) * S, y * S)], fill=pal["faint"], width=1 * S)
        y += 6
        # one row per sensor
        for s, trust in ev.sensors:
            bad = s in faulty
            ink = pal["faint"] if bad else pal["ink"]
            if s in differ_rows:
                d.line([((ox - 8) * S, y * S), ((ox - 8) * S, (y + 14) * S)], fill=VIOLET, width=2 * S)
            d.text((ox * S, y * S), s, font=font, fill=ink)
            d.text(((ox + 70) * S, y * S), str(trust), font=small, fill=pal["faint"] if bad else pal["label"])
            for i, p in enumerate(PROPS, start=1):
                v = ev.claims.get((s, p))
                if v is None:
                    continue
                wrong = truth.get(p) is not None and v != truth.get(p)
                x = x_of(i, ox)
                d.text((x * S, y * S), v, font=font, fill=RED if wrong else ink)
                if wrong and bad:   # explained away: struck through
                    tw = d.textlength(v, font=font)
                    d.line([(x * S, (y + 8) * S), (x * S + tw, (y + 8) * S)], fill=RED, width=1 * S)
            if s in ev.pct:
                d.text((x_of(4, ox) * S, y * S), ev.pct[s], font=font, fill=ink)
            if bad:
                why, colour = reason_for(s, ev, faulty, blamed)
                d.text((x_of(5, ox) * S, y * S), why, font=small, fill=colour or pal["label"])
            y += row_h
        # what this answer paid for
        cost_parts = [f"{c} {ev.cause_trust.get(c, '?')}" for c in sorted(blamed)]
        cost_parts += [f"{s} {t}" for s, t in ev.sensors
                       if s in faulty and s not in ev.acpi_bad
                       and not (s in ev.derived and ev.derived[s] in faulty)
                       and ev.causes.get(s) not in blamed]
        d.text((ox * S, (y + 6) * S), "paid for: " + (", ".join(cost_parts) or "nothing"),
               font=small, fill=pal["label"])

    img.save(path)
    return path, res
