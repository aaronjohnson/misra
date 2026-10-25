"""land.lp: what the deck's log adds up to. The case is the afternoon of
2026-10-25, when the weather unit failed a switch and a colon broke a build."""

from misra.reason import RULES, solve

LAND = RULES / "land"

AFTERNOON = """
entry(0,ok,bump,"misra").          % 0.2.0 in
entry(1,bad,switch,"system").      % misra-weather: no location, CREDENTIALS
entry(2,ok,bump,"misra").          % 0.2.1: skip without a location
entry(3,ok,switch,"system").
entry(4,ok,bump,"misra").          % 0.2.2: a fixed system user, with a colon
entry(5,bad,check,"system").       % ~/nixos doesn't build
entry(6,bad,check,"system").       % ... nine of these, really
entry(7,ok,bump,"misra").          % 0.2.3: no colon
entry(8,ok,switch,"system").
"""


def conclude(facts):
    res = solve([facts], LAND)
    assert not res.unsat
    return {str(a) for a in res.certain}


def test_the_afternoon_ends_clear():
    c = conclude(AFTERNOON)
    assert {"verdict(clear)", "failures(3)", "open_count(0)"} <= c
    assert {"first_fix(1,3)", "first_fix(5,8)", "first_fix(6,8)"} <= c


def test_before_the_fix_the_bump_is_blamed():
    c = conclude("\n".join(AFTERNOON.strip().splitlines()[:7]))   # stop after entry 6
    assert {"verdict(open)", "open(5)", "open(6)"} <= c
    assert {'blame(5,"misra")', 'blame(6,"misra")'} <= c


def test_a_push_is_fixed_only_by_a_push_of_the_same_repo():
    c = conclude("""
        entry(0,bad,push,"dotfiles").
        entry(1,ok,push,"nixos").
        entry(2,ok,commit,"dotfiles").
    """)
    assert "open(0)" in c and "verdict(open)" in c
    c = conclude("""
        entry(0,bad,push,"dotfiles").
        entry(1,ok,push,"dotfiles").
    """)
    assert "first_fix(0,1)" in c and "verdict(clear)" in c


def test_info_rows_count_for_nothing():
    c = conclude('entry(0,info,system,"system"). entry(1,info,check,"system").')
    assert {"verdict(clear)", "failures(0)"} <= c
