"""`misra explain` draws the evidence and every optimal answer."""

from pathlib import Path

from PIL import Image

from misra.explain import answer, evidence, render
from misra.reason import solve

CASES = Path(__file__).parent / "cases"
TIE = """
sensor(a;b). trust(a,1). trust(b,1).
claim(a,ac,on). claim(b,ac,off).
claim(a,battery,present).
"""


def test_incident_reads_the_evidence_and_one_answer(tmp_path):
    facts = [(CASES / "incident-2026-10-17.lp").read_text()]
    ev = evidence(facts)
    assert [s for s, _ in ev.sensors][:2] == ["ec", "trend"]        # most trusted first
    assert ev.acpi_bad == {"acpi_bat", "acpi_ac"}                    # observed, not guessed
    assert ev.causes["ucsi"] == "firmware"                           # from the rules
    path, res = render(facts, tmp_path / "incident.png")
    assert res.models == 1 and Image.open(path).getbbox()
    truth, _, faulty, blamed = answer(res.optimal[0])
    assert truth["ac"] == "off" and "ucsi" in faulty and blamed == {"firmware"}


def test_a_tie_draws_every_answer(tmp_path):
    path, res = render([TIE], tmp_path / "tie.png", mode="light")
    # a vs b disagree about ac, and nothing says anything about flow: 1 + 3 answers
    assert res.models == 4
    assert len(solve([TIE]).optimal) == 4
    assert Image.open(path).width > Image.open(path).height          # two panels a row
