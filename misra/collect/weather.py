"""Local weather, for the sky rules (rules/sky.lp): is it a grey day?

Two halves, so the daemon never touches the network:
  fetch()    `misra weather [OUT]`, run by the misra-weather unit (an
             unprivileged throwaway user with network) every 15 minutes; it
             saves Open-Meteo's current conditions to OUT
  collect()  the daemon reads that file each tick and turns it into facts

Open-Meteo needs no key. Only the coordinates are sent, rounded to two
decimals (about a kilometre). They come from a local file, never the repo:
the unit passes /var/lib/misra/weather.toml in as the credential `location`.
"""

import json
import os
import time
import tomllib
import urllib.request

URL = ("https://api.open-meteo.com/v1/forecast?latitude={lat:.2f}&longitude={lon:.2f}"
       "&current=cloud_cover,precipitation,weather_code,shortwave_radiation,is_day")
FILE = "/run/misra-weather/now.json"


def location(path=None):
    """(latitude, longitude) from the location file: the systemd credential
    when run by the unit, else the path given."""
    if path is None:
        path = os.path.join(os.environ.get("CREDENTIALS_DIRECTORY", "/var/lib/misra"),
                            "location" if "CREDENTIALS_DIRECTORY" in os.environ else "weather.toml")
    with open(path, "rb") as f:
        loc = tomllib.load(f)
    return float(loc["latitude"]), float(loc["longitude"])


def fetch(lat, lon, out):
    with urllib.request.urlopen(URL.format(lat=lat, lon=lon), timeout=20) as r:
        cur = json.load(r)["current"]
    cur["fetched"] = int(time.time())
    tmp = f"{out}.tmp"
    with open(tmp, "w") as f:
        json.dump(cur, f)
    os.replace(tmp, out)
    return cur


def collect(now, path=FILE):
    """Facts from the saved conditions, or none when there's no file. Rain in
    tenths of a millimetre, so it stays an integer."""
    try:
        with open(path) as f:
            w = json.load(f)
    except (OSError, ValueError):
        return [], None
    facts = [f"weather_age({max(0, int(now - w['fetched']))}).",
             f"cloud({int(w['cloud_cover'])}).",
             f"rain({round(10 * float(w['precipitation']))}).",
             f"wmo({int(w['weather_code'])}).",
             f"radiation({round(float(w['shortwave_radiation']))}).",
             "daylight." if w.get("is_day") else "night."]
    return facts, w
