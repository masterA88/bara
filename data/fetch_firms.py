"""Unduh titik panas NASA FIRMS di sekitar TPA Putri Cempo.

Perlu MAP_KEY gratis: https://firms.modaps.eosdis.nasa.gov/api/map_key/  -> simpan di env FIRMS_MAP_KEY.
API area membatasi 1 sampai 5 hari per request (lihat dokumentasi FIRMS), jadi skrip ini mengulang per 5 hari
di sekitar tiap tanggal kebakaran.

Batas yang harus disebut: satu piksel VIIRS 375 m kira-kira 14 ha, TPA 17 ha kira-kira 1,2 piksel.
NASA sendiri tidak menyarankan FIRMS untuk keputusan taktis skala lokal. Data ini hanya riwayat.

Run: FIRMS_MAP_KEY=... .venv/bin/python data/fetch_firms.py
Keluaran: data/raw/firms_<source>.csv
"""
import io
import os
import sys
from datetime import timedelta
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bara.site import FIRES, LAT, LON  # noqa: E402

RAW = Path(__file__).resolve().parent / "raw"
PAD_DEG = 0.02  # sekitar 2 km di sekeliling titik TPA
SOURCES = ["VIIRS_SNPP_SP", "VIIRS_NOAA20_SP", "MODIS_SP"]
WINDOW_DAYS = 5


def area_url(key: str, source: str, day: str) -> str:
    bbox = f"{LON - PAD_DEG},{LAT - PAD_DEG},{LON + PAD_DEG},{LAT + PAD_DEG}"
    return f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{key}/{source}/{bbox}/{WINDOW_DAYS}/{day}"


def main() -> None:
    key = os.environ.get("FIRMS_MAP_KEY")
    if not key:
        sys.exit("FIRMS_MAP_KEY belum di-set. Daftar gratis di https://firms.modaps.eosdis.nasa.gov/api/map_key/")
    RAW.mkdir(parents=True, exist_ok=True)
    for source in SOURCES:
        frames = []
        for ev in FIRES:
            for k in range(-2, 4):  # dari 10 hari sebelum sampai 20 hari sesudah tanggal mulai
                day = ev.start + timedelta(days=k * WINDOW_DAYS)
                r = requests.get(area_url(key, source, day.isoformat()), timeout=60)
                if r.ok and r.text.strip() and "latitude" in r.text:
                    frames.append(pd.read_csv(io.StringIO(r.text)))
        out = RAW / f"firms_{source}.csv"
        df = pd.concat(frames).drop_duplicates() if frames else pd.DataFrame()
        df.to_csv(out, index=False)
        print(f"{source}: {len(df)} deteksi -> {out}")


if __name__ == "__main__":
    main()
