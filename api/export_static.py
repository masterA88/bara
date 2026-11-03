"""Ekspor jawaban API untuk data simulasi ke file JSON, agar dashboard bisa di-deploy tanpa server Python.

Run: .venv/bin/python api/export_static.py
Keluaran: web/public/data/ (site.json, weather.json, comparison.json, steps.json, status/<n>.json, series/<node>.json)
Status dihitung tiap 3 jam. Deret suhu, skor AI, dan selisih pasca-kebakaran diekspor penuh sekali per node; frontend
memotongnya sampai waktu yang dipilih.
"""
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from api import main as api  # noqa: E402

OUT = ROOT / "web" / "public" / "data"
STEP_H = 3


def dump(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, separators=(",", ":"), ensure_ascii=False))


def main() -> None:
    df = api.readings("sim")
    start, end = df["ts"].min(), df["ts"].max()
    steps = list(pd.date_range(start + pd.Timedelta(hours=24), end, freq=f"{STEP_H}h"))
    if steps[-1] != end:
        steps.append(end)
    dump(OUT / "site.json", api.site())
    dump(OUT / "weather.json", api.weather(days=365))
    dump(OUT / "comparison.json", api.comparison())
    dump(OUT / "steps.json", {"step_h": STEP_H, "steps": [t.isoformat() for t in steps]})
    for i, t in enumerate(steps):
        dump(OUT / "status" / f"{i}.json", api.status("sim", t.isoformat()))
        if i % 40 == 0:
            print(f"status {i + 1}/{len(steps)}")
    for node in sorted(df["node"].unique()):
        dump(OUT / "series" / f"{node}.json", api.series(node, "sim", None))
    size = sum(f.stat().st_size for f in OUT.rglob("*.json"))
    print(f"{len(steps)} status, {df['node'].nunique()} node -> {OUT} ({size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
