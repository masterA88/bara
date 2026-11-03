"""Hubungkan tabel bacaan node (CSV dari ingest atau simulasi) ke lapisan aturan dan lapisan AI."""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import nodes as node_cfg
from .risk import BASELINE_MIN_H, SETTLE_H, BASELINE_TARGET_H, DS18B20_RESET_C, BlockVerdict, assess_block
from .thermal import ThermalDetector

TEMP_PREFIX = "t_"
# Lapisan AI hanya menaikkan level blok jika skornya >= 20 (stopgap dari brief DRA field-followup 6.4: menghapus
# 8 dari 8 alarm palsu di 10 simulasi 60 hari; penyalaan ulang 150 W/m3 tetap terdeteksi dalam 3 hari di 10 dari 10,
# pemanasan lambat 40 W/m3 di 8 dari 10). Skor 1 sampai 20 ditampilkan sebagai "perhatian AI" tanpa menaikkan level.
AI_LEVEL_SCORE = 20.0


def depth_columns(df: pd.DataFrame) -> dict[int, str]:
    return {int(c[len(TEMP_PREFIX):]): c for c in df.columns if c.startswith(TEMP_PREFIX) and c[len(TEMP_PREFIX):].isdigit()}


def hourly(g: pd.DataFrame) -> pd.DataFrame:
    """Rata-rata per jam per node. Nilai reset 85,00 C dibuang sebelum dirata-rata."""
    g = g.copy()
    for c in depth_columns(g).values():
        g.loc[g[c].round(2) == DS18B20_RESET_C, c] = np.nan
    num = g.select_dtypes("number").columns
    return g.set_index("ts")[num].resample("1h").mean().interpolate(limit=3)


def node_frames(df: pd.DataFrame, until=None) -> dict[tuple[str, str], pd.DataFrame]:
    df = df.copy()
    df["ts"] = pd.to_datetime(df["ts"])
    if until is not None:
        df = df[df["ts"] <= pd.Timestamp(until)]
    return {k: hourly(g) for k, g in df.sort_values("ts").groupby(["node", "block"])}


def is_simulated(df: pd.DataFrame) -> bool:
    return "simulated" in df and bool(df["simulated"].astype(str).eq("True").any())


def _probes(g: pd.DataFrame) -> dict[int, list[float]]:
    cols = depth_columns(g)
    return {d: g[c].tolist() for d, c in cols.items() if g[c].notna().any()}


def _aligned_ref(g: pd.DataFrame, ref: pd.DataFrame | None) -> dict[int, list[float]] | None:
    """Probe node kontrol pada jam yang sama dengan node blok terbakar."""
    if ref is None:
        return None
    r = ref.reindex(g.index)
    return {d: r[c].tolist() for d, c in depth_columns(r).items() if r[c].notna().any()}


def assess_readings(df: pd.DataFrame, until=None) -> list[BlockVerdict]:
    frames = node_frames(df, until)
    cfg = node_cfg.load(is_simulated(df))
    by_node = {n: g for (n, _), g in frames.items()}
    out = []
    for (node, block), g in frames.items():
        role = node_cfg.role(cfg, node)
        gases = {"MQ": g["mq_raw"].dropna().tolist()[-7 * 24:]} if "mq_raw" in g else {}
        ref = _aligned_ref(g, by_node.get(role.get("reference"))) if role["mode"] == "pasca_kebakaran" else None
        out.append(assess_block(f"{block} ({node})", _probes(g), gases, role["mode"], ref))
    return out


def thermal_scan(df: pd.DataFrame, step_h: int = 3) -> pd.DataFrame:
    """Jalankan detektor termal per node setelah commissioning. Node kontrol dihitung dulu, karena ambangnya menjadi
    batas bawah ambang node lain (brief DRA field-followup, perubahan 4)."""
    cfg = node_cfg.load(is_simulated(df))
    frames = node_frames(df)
    order = sorted(frames, key=lambda k: node_cfg.role(cfg, k[0])["mode"] != "kontrol")
    floors: dict[str, float] = {}
    rows = []
    for node, block in order:
        g = frames[(node, block)]
        role = node_cfg.role(cfg, node)
        cols = depth_columns(g)
        depths = sorted(d for d in cols if g[cols[d]].notna().mean() > 0.9)
        if len(g) < SETTLE_H + BASELINE_MIN_H + 24 or "t_air" not in g:
            continue
        learn = slice(SETTLE_H, min(SETTLE_H + BASELINE_TARGET_H, len(g) - 24))
        temps = g[[cols[d] for d in depths]].interpolate(limit_direction="both").to_numpy()
        floor = floors.get(role.get("reference"), max(floors.values(), default=0.0))
        det = ThermalDetector(g["t_air"].interpolate(limit_direction="both").to_numpy(), temps,
                              [d / 100 for d in depths], learn, min_threshold=floor)
        if role["mode"] == "kontrol":
            floors[node] = det.threshold
        for r in det.scan(step_h):
            rows.append({
                "node": node, "block": block, "mode": role["mode"], "ts": g.index[r.t_end - 1], "lr": r.lr,
                "threshold": r.threshold, "own_threshold": det.own_threshold, "calibrated": det.calibrated,
                "score": r.score, "detected": r.detected, "z_m": r.z_m,
                "onset": g.index[r.onset_h] if r.onset_h is not None else pd.NaT, "strength_w_m3": r.strength_w_m3,
                "alpha": det.alpha, "alpha_source": det.alpha_source, "learn_end": g.index[learn.stop - 1],
            })
    return pd.DataFrame(rows)


def ai_effect(row: dict | pd.Series | None, mode: str) -> str:
    """Bagaimana hasil AI dipakai: "naikkan" (level minimal WASPADA), "perhatian" (catatan saja), atau "tidak"."""
    if row is None or not bool(row["detected"]):
        return "tidak"
    if mode == "pasca_kebakaran":
        return "perhatian"       # sampai suku peluruhan bebas (v2) tersedia, AI hanya informasi di blok terbakar
    return "naikkan" if row["score"] >= AI_LEVEL_SCORE else "perhatian"
