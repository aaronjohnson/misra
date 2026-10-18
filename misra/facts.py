"""Turning Python values into ASP facts, and clingo symbols back into Python."""

import re

_IDENT = re.compile(r"[a-z][A-Za-z0-9_]*\Z")


def term(v):
    """A Python value as an ASP term: ints stay numbers, identifiers stay
    constants, anything else becomes a quoted string."""
    if isinstance(v, bool):
        raise TypeError("no booleans in facts; use a constant")
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return str(round(v))
    if isinstance(v, str) and _IDENT.match(v):
        return v
    s = str(v).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{s}"'


def fact(name, *args):
    if not args:
        return f"{name}."
    return f"{name}({','.join(term(a) for a in args)})."


def py(sym):
    """A clingo symbol as a plain Python value (constants and strings -> str)."""
    import clingo
    t = sym.type
    if t == clingo.SymbolType.Number:
        return sym.number
    if t == clingo.SymbolType.String:
        return sym.string
    if t == clingo.SymbolType.Function and not sym.arguments:
        return sym.name
    return str(sym)


def atoms(symbols, name, arity=None):
    """Arguments of every atom called `name` (optionally of one arity)."""
    out = []
    for s in symbols:
        if s.name == name and (arity is None or len(s.arguments) == arity):
            out.append(tuple(py(a) for a in s.arguments))
    return sorted(out, key=str)
