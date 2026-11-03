"""Jalankan lapisan AI (detektor termal) dan lapisan aturan sepanjang waktu, lalu bandingkan waktu deteksinya.

Run: .venv/bin/python data/run_thermal.py [csv bacaan]   (default: data/processed/sim_readings.csv)
Keluaran: data/processed/thermal_scan.csv, rules_timeline.csv, layer_comparison.md
"""
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from bara.assess import AI_LEVEL_SCORE, assess_readings, thermal_scan  # noqa: E402

PROC = ROOT / "data" / "processed"
STEP_H = 3


def rules_timeline(df: pd.DataFrame) -> pd.DataFrame:
    ts = pd.to_datetime(df["ts"])
    rows = []
    for t in pd.date_range(ts.min() + pd.Timedelta(hours=24), ts.max(), freq=f"{STEP_H}h"):
        for v in assess_readings(df, until=t):
            rows.append({"ts": t, "block": v.block, "level": v.level.name, "level_n": int(v.level)})
    return pd.DataFrame(rows)


def first(frame: pd.DataFrame, mask) -> pd.Timestamp | None:
    hit = frame[mask]
    return hit["ts"].iloc[0] if not hit.empty else None


def main() -> None:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else PROC / "sim_readings.csv"
    df = pd.read_csv(src)
    scan = thermal_scan(df, STEP_H)
    scan.to_csv(PROC / "thermal_scan.csv", index=False)
    rules = rules_timeline(df)
    rules.to_csv(PROC / "rules_timeline.csv", index=False)

    truth_path = PROC / "sim_truth.json"
    truth = json.loads(truth_path.read_text()) if src.name == "sim_readings.csv" and truth_path.exists() else {}
    lines = ["# Perbandingan waktu deteksi: lapisan AI dan lapisan aturan", "",
             f"Data: `{src.name}`. Langkah {STEP_H} jam. Waktu dalam WIB.", "",
             "| Node | Mode | Kebenaran (simulasi) | AI skor > 1 | AI skor >= 20 (menaikkan level) | Perkiraan AI (kedalaman, mulai) | Aturan pertama WASPADA | Aturan pertama SIAGA |",
             "|---|---|---|---|---|---|---|---|"]
    for node, g in scan.groupby("node"):
        block, mode = g["block"].iloc[0], g["mode"].iloc[0]
        r = rules[rules["block"] == f"{block} ({node})"]
        t_ai = first(g, g["detected"])
        t_lift = first(g, g["detected"] & (g["score"] >= AI_LEVEL_SCORE))
        est = g[g["detected"]].head(1)
        est_txt = f"{est.z_m.iloc[0]:.2f} m, {pd.Timestamp(est.onset.iloc[0]):%d %b %H:%M}" if not est.empty else "-"
        tr = truth.get(node)
        tr_txt = f"sumber {tr['q_w_m3']:.0f} W/m3 di {tr['z_m']:.2f} m, mulai {pd.Timestamp(tr['onset']):%d %b %H:%M}" if tr else "tanpa sumber baru"
        w = first(r, r["level_n"] >= 1)
        s2 = first(r, r["level_n"] >= 2)
        f = lambda t: f"{pd.Timestamp(t):%d %b %H:%M}" if t is not None else "tidak dalam rentang data"
        lift = f(t_lift) if mode != "pasca_kebakaran" else "tidak dipakai (mode pasca-kebakaran)"
        lines.append(f"| {node} ({block}) | {mode} | {tr_txt} | {f(t_ai)} | {lift} | {est_txt} | {f(w)} | {f(s2)} |")
    lines += ["", "Ambang AI dikalibrasi pada data commissioning tiap node (3x statistik maksimum tanpa sumber), dengan ambang node "
              "kontrol sebagai batas bawah. Lapisan AI hanya menaikkan level jika skor >= 20; di blok pasca-kebakaran AI hanya "
              "informasi. Data simulasi memakai model fisika yang sama dengan detektor, ditambah pemanasan matahari, hujan, "
              "derau, dan drift yang tidak dimodelkan detektor. Hasil ini satu simulasi 30 hari dan batas atas, bukan klaim "
              "kinerja lapangan. Uji DRA 60 hari menemukan alarm palsu AI tanpa batas skor 20."]
    (PROC / "layer_comparison.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
