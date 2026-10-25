"""Small multiples of the power sensors, for the image in a power alert.

One row per thing, all on the same time axis (the last two hours), no box, no
legend, labels where the data is:

  AC        believed: a heavy line while the charger is believed plugged in
  acpi_ac   each sensor's own claim, thin; faint while misra distrusts it;
  ucsi      a thin red line wherever it disagreed with the belief
  ec
  flow      believed charging / discharging / idle, as a thin coloured line
  battery   charge %, a sparkline, the current value at its end
  watts     into (+) or out of (-) the battery, around a faint zero line

Gaps (sleep, hibernate) break the lines instead of being drawn across.
"""

from PIL import Image, ImageDraw, ImageFont

PALETTE = {
    # Solarized, the desktop's palette; mako cards are dark or light with the time of day
    "dark":  {"ink": "#93a1a1", "faint": "#3d5a63", "label": "#839496"},
    "light": {"ink": "#586e75", "faint": "#d3cbb7", "label": "#657b83"},
}
GREEN, ORANGE, RED, VIOLET, CYAN = "#859900", "#cb4b16", "#dc322f", "#6c71c4", "#2aa198"
FLOW = {"charging": GREEN, "discharging": ORANGE, "idle": None}   # idle: the ink colour


def render(series, path, mode="dark", width=320, scale=2, window=7200):
    ticks = series.get("ticks", [])
    interval = series.get("interval", 30)
    if not ticks:
        return None
    pal = PALETTE.get(mode, PALETTE["dark"])
    t1 = ticks[-1]["t"]
    t0 = max(ticks[0]["t"], t1 - window)
    ticks = [k for k in ticks if k["t"] >= t0]
    span = max(1, t1 - t0)

    sensors = [s for s in ("acpi_ac", "ucsi", "ec") if any("ac" in k["claims"].get(s, {}) for k in ticks)]
    rows = [("AC", "ac_belief", 12)] + [(s, "ac", 9) for s in sensors] + \
           [("flow", "flow", 9), ("battery", "pct", 24), ("watts", "w", 24)]
    left, right, top = 52, 70, 4
    height = top + sum(h + 5 for _, _, h in rows) + 14

    S = scale
    img = Image.new("RGBA", (width * S, height * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    small = ImageFont.load_default(size=9 * S)
    x0, x1 = left * S, (width - right) * S

    def X(t):
        return x0 + (t - t0) / span * (x1 - x0)

    def runs(pred):
        """[(ta, tb)] stretches where pred(tick) holds, broken at gaps."""
        out, start, prev = [], None, None
        for k in ticks:
            gap = prev is not None and k["t"] - prev["t"] > 3 * interval
            if start is not None and (gap or not pred(k)):
                out.append((start, prev["t"] + (0 if gap else interval)))
                start = None
            if pred(k) and start is None:
                start = k["t"]
            prev = k
        if start is not None:
            out.append((start, ticks[-1]["t"]))
        return out

    def label(y, text, colour=None):
        d.text((x0 - 6 * S, y), text, font=small, fill=colour or pal["label"], anchor="rm")

    def value(y, text, colour=None):
        d.text((x1 + 6 * S, y), text, font=small, fill=colour or pal["ink"], anchor="lm")

    y = top * S
    for name, kind, h in rows:
        mid = y + h * S / 2
        if kind == "ac_belief":
            label(mid, name, pal["ink"])
            d.line([(x0, mid), (x1, mid)], fill=pal["faint"], width=1 * S)
            for a, b in runs(lambda k: k["believed"]["ac"] == "on"):
                d.line([(X(a), mid), (X(b), mid)], fill=pal["ink"], width=4 * S)
            now = ticks[-1]["believed"]["ac"]
            value(mid, "on" if now == "on" else "off" if now == "off" else "?")
        elif kind == "ac":
            s = name
            faulty_now = s in ticks[-1]["faulty"]
            label(mid, s, RED if faulty_now else None)
            # its claim: solid while trusted, faint where misra distrusted it
            on = lambda k: k["claims"].get(s, {}).get("ac") == "on"  # noqa: E731
            for a, b in runs(lambda k: on(k) and s not in k["faulty"]):
                d.line([(X(a), mid), (X(b), mid)], fill=pal["ink"], width=2 * S)
            for a, b in runs(lambda k: on(k) and s in k["faulty"]):
                d.line([(X(a), mid), (X(b), mid)], fill=pal["faint"], width=2 * S)
            # where it said something else than the belief: a thin red line under the row
            def disagrees(k):
                claim, belief = k["claims"].get(s, {}).get("ac"), k["believed"]["ac"]
                return bool(claim and belief and claim != belief)
            for a, b in runs(disagrees):
                yy = mid + h * S / 2
                d.line([(X(a), yy), (X(b), yy)], fill=RED, width=int(1.5 * S))
            claim = ticks[-1]["claims"].get(s, {}).get("ac")
            value(mid, claim or "–", RED if faulty_now else None)
        elif kind == "flow":
            label(mid, name)
            for flow, colour in FLOW.items():
                for a, b in runs(lambda k, f=flow: k["believed"]["flow"] == f):
                    d.line([(X(a), mid), (X(b), mid)], fill=colour or pal["ink"], width=2 * S)
            now = ticks[-1]["believed"]["flow"]
            value(mid, now or "?", FLOW.get(now) or pal["ink"])
        else:
            key, unit = ("pct", "%") if kind == "pct" else ("w", " W")
            pts = [(k["t"], k["believed"][key]) for k in ticks if k["believed"][key] is not None]
            label(mid, name)
            if pts:
                lo, hi = min(v for _, v in pts), max(v for _, v in pts)
                if kind == "w":
                    lo, hi = min(lo, 0), max(hi, 0)
                pad = max(0.5, (hi - lo) * 0.1)
                lo, hi = lo - pad, hi + pad

                def Y(v):
                    return y + h * S - (v - lo) / (hi - lo) * h * S
                if kind == "w":
                    d.line([(x0, Y(0)), (x1, Y(0))], fill=pal["faint"], width=1 * S)
                seg, prev = [], None
                for t, v in pts:
                    if prev is not None and t - prev > 3 * interval and len(seg) > 1:
                        d.line(seg, fill=pal["ink"], width=int(1.5 * S), joint="curve")
                        seg = []
                    seg.append((X(t), Y(v)))
                    prev = t
                if len(seg) > 1:
                    d.line(seg, fill=pal["ink"], width=int(1.5 * S), joint="curve")
                # Tufte's sparkline marks: the end point, and the extremes if they differ
                tmin = min(pts, key=lambda p: p[1])
                tmax = max(pts, key=lambda p: p[1])
                for (t, v), col in ((tmin, CYAN), (tmax, CYAN), (pts[-1], RED if kind == "w" and pts[-1][1] < 0 else VIOLET)):
                    r = 2 * S
                    d.ellipse([X(t) - r, Y(v) - r, X(t) + r, Y(v) + r], fill=col)
                last = pts[-1][1]
                value(mid, f"{last:g}{unit}")
            else:
                value(mid, "–")
        y += (h + 5) * S

    # the time axis: just where it starts and that it ends now
    hours = span / 3600
    d.text((x0, y + 1 * S), f"-{hours:.1f} h" if hours >= 1 else f"-{span // 60} min",
           font=small, fill=pal["label"], anchor="la")
    d.text((x1, y + 1 * S), "now", font=small, fill=pal["label"], anchor="ra")

    img.save(path)
    return path
