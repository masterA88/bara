"""Data node SIMULASI untuk demo, dibuat dengan model konduksi panas yang sama dengan bara/thermal.py.

Empat node, tiap node 5 probe DS18B20 (10, 30, 60, 100, 150 cm), DHT22, dan MQ (ADC mentah). 30 hari per jam
di musim hujan. Commissioning: 72 jam pertama dibuang, hari ke-3 sampai ke-17 untuk belajar baseline.
Skenario (parameter blok terbakar dari brief DRA field-followup bagian 4.2, disetel pada model ini):
  N1 (blok A)  node kontrol di sampah yang tidak terbakar, ditambah satu bacaan 85,00 C palsu (nilai reset DS18B20)
  N2 (blok C)  mode normal, pemanasan lambat: sumber 40 W/m3 di 1,0 m mulai hari ke-18
  N3 (blok D1) blok bekas terbakar: kelebihan awal 14,6 C di 0,3 sampai 2,0 m, sisa bara 40 W/m3 di 1,3 m yang meluruh
               (tau 120 hari), sehingga probe 150 cm sekitar 55 C di hari ke-3 dan mendingin sekitar 0,25 C/hari;
               penyalaan ulang 150 W/m3 di 0,8 m mulai hari ke-20 (naik bertahap 48 jam)
  N4 (blok B)  blok bekas terbakar dengan sisa bara tetap 80 W/m3 di 1,3 m sehingga pendinginan berhenti, lalu injeksi
               air hari ke-21 (-400 W/m3 di 1,0 m selama 48 jam, dicatat di sim_events.csv) dan suhu naik lagi.
               Brief DRA memakai 40 W/m3 dan injeksi hari ke-14 tanpa menguji tanda "berhenti mendingin"; dengan 40 W/m3
               selisihnya tidak pernah di atas 10 C, jadi dinaikkan ke 80 W/m3, dan injeksi digeser agar tanda itu
               muncul lebih dulu (hari ke-16).
Angka 55 C mengikuti notulensi tim ("dapat mencapai sekitar 55 C"); laju pendinginan dan respons injeksi adalah asumsi
demo karena tidak ada kurva terukur dari TPA terbuka tropis.

Asumsi demo, bukan pengukuran: difusivitas "sebenarnya" 6,5e-7 m2/s (model mulai dari 5e-7 dan harus
memperkirakannya sendiri), panas biologis 6 W/m3, suhu dasar 3 m 45 C. Profil yang dihasilkan sekitar 33 sampai
45 C naik menurut kedalaman, sesuai bentuk musim hujan di TPA terbuka Maceio (brief DRA bagian 2).

Run: .venv/bin/python sim/simulate_nodes.py
Keluaran: data/processed/sim_readings.csv (kolom simulated=True) dan data/processed/sim_truth.json
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from bara.thermal import Z, gauss, simulate, steady_profile  # noqa: E402

PROC = ROOT / "data" / "processed"
DEPTHS_CM = [10, 30, 60, 100, 150]
DAYS = 30
START = "2026-10-01"
ALPHA_TRUE = 6.5e-7
G_BIO = 6.0
BOTTOM_C = 45.0
POSTFIRE_A0 = 14.6
SCENARIOS = {
    "N1": {"block": "A", "source": None, "glitch_h": 22 * 24 + 5},
    "N2": {"block": "C", "source": {"z": 1.00, "q": 40.0, "onset_day": 18}},
    "N3": {"block": "D1", "postfire": {"q": 40.0, "z": 1.3, "tau_d": 120},
           "source": {"z": 0.80, "q": 150.0, "onset_day": 20, "ramp_h": 48}},
    "N4": {"block": "B", "postfire": {"q": 80.0, "z": 1.3, "tau_d": None},
           "injection": {"z": 1.0, "q": -400.0, "day": 21, "hours": 48}},
}


def postfire_excess(a0: float, top: float = 0.3, bottom: float = 2.0) -> np.ndarray:
    """Kelebihan suhu awal blok bekas terbakar, tepi logistik (0,10 m di atas, 0,15 m di bawah)."""
    up = 1 / (1 + np.exp(-(Z - top) / 0.10))
    lo = 1 / (1 + np.exp((Z - bottom) / 0.15))
    return a0 * up * lo


def weather(rng, hours: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    h = np.arange(hours)
    hod = h % 24
    air = 28 + 4 * np.sin(2 * np.pi * (hod - 9) / 24) + rng.normal(0, 0.4, hours)
    rain_days = rng.random(hours // 24) < 0.6           # musim hujan: sekitar 60% hari hujan sore
    for d in np.flatnonzero(rain_days):
        s = d * 24 + 14
        air[s:s + 5] -= rng.uniform(2, 4)
    sun = np.clip(np.sin(np.pi * (hod - 6) / 12), 0, None) * 3.0   # sampah terbuka lebih panas dari udara siang
    surface = air + sun * np.repeat(~rain_days, 24)[:hours]
    rh = np.clip(88 - 3 * (air - 28) + rng.normal(0, 3, hours), 30, 100)
    return air, surface, rh


def simulate_all(seed: int = 7) -> tuple[pd.DataFrame, dict]:
    rng = np.random.default_rng(seed)
    H = DAYS * 24
    probes = np.array(DEPTHS_CM) / 100
    air, surface, rh = weather(rng, H)
    ts = pd.date_range(START, periods=H, freq="h", tz="Asia/Jakarta")
    _, T_spin = simulate(ALPHA_TRUE, np.tile(surface[:24], 60), BOTTOM_C,
                         steady_profile(surface.mean(), BOTTOM_C), probes, g=G_BIO)
    rows, truth, events = [], {}, []
    for node, sc in SCENARIOS.items():
        src, pf, inj = sc.get("source"), sc.get("postfire"), sc.get("injection")
        parts = []
        if src:
            onset, ramp = src["onset_day"] * 24, src.get("ramp_h", 0)
            shape = src["q"] * gauss(src["z"])
            parts.append(lambda h, onset=onset, ramp=ramp, shape=shape:
                         shape * (min(1.0, (h - onset) / ramp) if ramp else 1.0) if h >= onset else 0.0 * Z)
            truth[node] = {"z_m": src["z"], "q_w_m3": src["q"], "onset": ts[onset].isoformat()}
        if pf:
            shape = pf["q"] * gauss(pf["z"])
            tau_h = pf["tau_d"] * 24 if pf["tau_d"] else None
            parts.append(lambda h, shape=shape, tau_h=tau_h: shape * (np.exp(-h / tau_h) if tau_h else 1.0))
        if inj:
            h0, h1 = inj["day"] * 24, inj["day"] * 24 + inj["hours"]
            shape = inj["q"] * gauss(inj["z"])
            parts.append(lambda h, h0=h0, h1=h1, shape=shape: shape if h0 <= h < h1 else 0.0 * Z)
            events.append({"ts": ts[h0].isoformat(), "node": node, "block": sc["block"], "type": "injeksi",
                           "note": f"injeksi air simulasi di {inj['z']:.1f} m selama {inj['hours']} jam"})
        source = (lambda h, parts=parts: sum(f(h) for f in parts)) if parts else None
        T0 = T_spin + postfire_excess(POSTFIRE_A0) if pf else T_spin
        T, _ = simulate(ALPHA_TRUE, surface, BOTTOM_C, T0, probes, g=G_BIO, source=source)
        T = T + rng.normal(0, 0.1, T.shape) + np.cumsum(rng.normal(0, 0.005, T.shape), axis=0)
        gas = 400 + rng.normal(0, 15, H)
        if src:
            ramp = np.clip((np.arange(H) - src["onset_day"] * 24) / 24, 0, None)
            gas *= 1 + 0.02 * ramp * src["q"] / 40
        for i in range(H):
            r = {"ts": ts[i].isoformat(), "node": node, "block": sc["block"], "t_air": round(air[i], 2),
                 "rh": round(rh[i], 1)}
            for j, d in enumerate(DEPTHS_CM):
                r[f"t_{d}"] = round(float(T[i, j]), 2)
            if sc.get("glitch_h") == i:
                r["t_100"] = 85.0
            r["mq_raw"] = int(gas[i])
            r["simulated"] = True
            rows.append(r)
    return pd.DataFrame(rows), truth, pd.DataFrame(events)


if __name__ == "__main__":
    df, truth, events = simulate_all()
    PROC.mkdir(parents=True, exist_ok=True)
    df.to_csv(PROC / "sim_readings.csv", index=False)
    events.to_csv(PROC / "sim_events.csv", index=False)
    (PROC / "sim_truth.json").write_text(json.dumps(truth, indent=2))
    first = df[df.node == "N1"].iloc[24 * 5]
    print(f"{len(df)} baris simulasi -> {PROC / 'sim_readings.csv'}")
    print("contoh profil N1 hari ke-5:", {d: first[f"t_{d}"] for d in DEPTHS_CM})
