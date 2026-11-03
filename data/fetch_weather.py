"""Unduh cuaca historis TPA Putri Cempo dari Open-Meteo Archive (reanalisis ERA5, tanpa key, non-komersial).

Indeks FWI (Drought Code, FFMC) didefinisikan pada cuaca jam 12 siang dan hujan 24 jam sampai siang, jadi skrip
ini mengambil data per jam lalu menyusunnya per hari (brief DRA 2026-10-30, perubahan 8).

Run: .venv/bin/python data/fetch_weather.py [start] [end]
Keluaran: data/raw/openmeteo_noon.csv (date, t_noon, rh_noon, wind_noon, rain_24h, tmax)
"""
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bara.site import LAT, LON  # noqa: E402

OUT = Path(__file__).resolve().parent / "raw" / "openmeteo_noon.csv"
URL = "https://archive-api.open-meteo.com/v1/archive"


def fetch_hourly(start: str, end: str) -> pd.DataFrame:
    params = {"latitude": LAT, "longitude": LON, "start_date": start, "end_date": end, "timezone": "Asia/Jakarta",
              "hourly": "temperature_2m,relative_humidity_2m,wind_speed_10m,precipitation"}
    r = requests.get(URL, params=params, timeout=300)
    r.raise_for_status()
    h = r.json()["hourly"]
    return pd.DataFrame({"time": pd.to_datetime(h["time"]), "t": h["temperature_2m"], "rh": h["relative_humidity_2m"],
                         "wind": h["wind_speed_10m"], "rain": h["precipitation"]}).dropna()


def to_noon(h: pd.DataFrame) -> pd.DataFrame:
    h = h.set_index("time").sort_index()
    rain_24h = h["rain"].rolling("24h").sum()          # jam 13:00 kemarin sampai 12:00 hari ini
    noon = h[h.index.hour == 12].copy()
    noon["rain_24h"] = rain_24h[noon.index]
    tmax = h["t"].resample("1D").max()
    out = pd.DataFrame({"date": noon.index.normalize(), "t_noon": noon["t"].values, "rh_noon": noon["rh"].values,
                        "wind_noon": noon["wind"].values, "rain_24h": noon["rain_24h"].values})
    out["tmax"] = tmax.reindex(out["date"]).values
    return out


if __name__ == "__main__":
    start = sys.argv[1] if len(sys.argv) > 1 else "2015-01-01"
    end = sys.argv[2] if len(sys.argv) > 2 else str(date.today() - timedelta(days=5))  # ERA5 tertunda sekitar 5 hari
    df = to_noon(fetch_hourly(start, end))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False)
    print(f"{len(df)} hari, {df.date.min().date()} sampai {df.date.max().date()} -> {OUT}")
