"""Uji mundur Drought Code dan FFMC pada tanggal kebakaran Putri Cempo.

Hanya ada 4 kejadian, jadi hasilnya deskriptif: di persentil berapa cuaca hari kebakaran, bukan akurasi model.
Run: .venv/bin/python data/backtest_weather.py
Keluaran: data/processed/weather_index.csv dan data/processed/backtest_weather.md
"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from bara.site import FIRES  # noqa: E402
from bara.weather import DRY_SEASON_MONTHS, fwi_codes  # noqa: E402

RAW = ROOT / "data" / "raw" / "openmeteo_noon.csv"
OUT = ROOT / "data" / "processed"


def main() -> None:
    d = fwi_codes(pd.read_csv(RAW, parse_dates=["date"]))
    OUT.mkdir(parents=True, exist_ok=True)
    d.to_csv(OUT / "weather_index.csv", index=False)

    season = d[d.date.dt.month.isin(DRY_SEASON_MONTHS)]
    rows = []
    for ev in FIRES:
        day = d[d.date == pd.Timestamp(ev.start)]
        if day.empty:
            continue
        x = day.iloc[0]
        rows.append({
            "tanggal": ev.start.isoformat() + ("" if ev.start_exact else " (paling lambat)"),
            "DC": round(x.dc), "kelas DC (BMKG)": x.dc_class, "persentil DC Jul-Okt": round(x.dc_pct_dry_season * 100),
            "FFMC": round(x.ffmc, 1), "kelas FFMC (BMKG)": x.ffmc_class,
            "persentil FFMC Jul-Okt": round((season.ffmc < x.ffmc).mean() * 100),
        })
    res = pd.DataFrame(rows)
    lowest = res["DC"].min()
    md = [
        "# Uji mundur Drought Code dan FFMC",
        "",
        f"Data: Open-Meteo Archive (cuaca jam 12 siang), {d.date.min().date()} sampai {d.date.max().date()}, {len(d)} hari "
        f"setelah 120 hari spin-up, titik TPA Putri Cempo. Indeks dari xclim 0.62.0.",
        "",
        res.to_markdown(index=False),
        "",
        f"Kelas BMKG 'sangat kering' (DC > 350) berlaku pada {(season.dc > 350).mean():.0%} hari Juli sampai Oktober. "
        f"DC setinggi kebakaran dengan nilai terendah ({lowest}) atau lebih dicapai pada {(season.dc >= lowest).mean():.0%} hari Juli sampai Oktober.",
        "Empat kejadian terlalu sedikit untuk mengukur akurasi. Indeks ini menandai musim berisiko di tingkat TPA dan tidak bisa",
        "menunjuk blok mana yang panas.",
    ]
    (OUT / "backtest_weather.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
