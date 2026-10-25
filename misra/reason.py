"""Run the rules over a tick's facts.

The power rules minimise the blame put on sensors, and more than one answer
can be equally good. We collect every optimal answer and split the
conclusions into `certain` (in all of them) and `possible` (in some). Only
certain conclusions drive the displays and alerts, so a tie never turns into
a confident wrong number.
"""

from dataclasses import dataclass, field
from pathlib import Path

import clingo

RULES = Path(__file__).resolve().parent / "rules"


@dataclass
class Result:
    certain: frozenset = frozenset()
    possible: frozenset = frozenset()
    models: int = 0
    cost: list = field(default_factory=list)
    unsat: bool = False
    optimal: list = field(default_factory=list)   # each optimal model, for `misra explain`


def solve(facts, rules_dir=RULES):
    ctl = clingo.Control(["--opt-mode=optN", "0", "--warn=none"])
    for f in sorted(Path(rules_dir).glob("*.lp")):
        ctl.load(str(f))
    ctl.add("base", [], "\n".join(facts))
    ctl.ground([("base", [])])

    optimal, last, cost = [], None, []
    with ctl.solve(yield_=True) as handle:
        for m in handle:
            last = frozenset(m.symbols(shown=True))
            cost = list(m.cost)
            if m.optimality_proven:
                optimal.append(last)
        unsat = handle.get().unsatisfiable

    if unsat:
        return Result(unsat=True)
    models = optimal or ([last] if last is not None else [])
    if not models:
        return Result()
    certain = frozenset.intersection(*models)
    possible = frozenset.union(*models) - certain
    return Result(certain, possible, len(models), cost, optimal=models)
