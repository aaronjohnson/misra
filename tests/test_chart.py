"""The alert chart renders from a series like the daemon writes, gaps and disagreements included."""

from PIL import Image

from misra.chart import render


def series():
    ticks = []
    for i in range(120):                       # an hour at 30 s, with a sleep in the middle
        t = 1_000_000 + i * 30 + (1800 if i >= 60 else 0)
        plugged = i < 80
        ucsi_wrong = 40 <= i < 70              # UCSI says unplugged while the charger is in
        ticks.append({
            "t": t, "resume": i == 60,
            "believed": {"ac": "on" if plugged else "off",
                         "flow": "charging" if plugged else "discharging",
                         "pct": 60 + i * 0.2 if plugged else 76 - (i - 80) * 0.3,
                         "w": 12.5 if plugged else -7.0},
            "claims": {"acpi_ac": {"ac": "on" if plugged else "off"},
                       "ucsi": {"ac": "off" if ucsi_wrong or not plugged else "on"}},
            "pct": {"acpi_bat": 60 + i * 0.2},
            "faulty": ["ucsi"] if ucsi_wrong else [],
        })
    return {"interval": 30, "ticks": ticks}


def test_renders_both_modes(tmp_path):
    for mode in ("dark", "light"):
        p = render(series(), tmp_path / f"{mode}.png", mode=mode)
        img = Image.open(p)
        assert img.width == 640 and img.height > 200      # 320 logical at 2x
        assert img.getbbox() is not None                  # something was drawn


def test_empty_series_draws_nothing(tmp_path):
    assert render({"ticks": []}, tmp_path / "x.png") is None
