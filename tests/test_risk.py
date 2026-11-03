import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "sim"))

from bara.assess import assess_readings  # noqa: E402
from bara.risk import (BASELINE_MIN_H, SETTLE_H, Level, assess_block, learn_baseline,  # noqa: E402
                       probe_level, theil_sen_per_day)
from bara.thermal import ThermalDetector, estimate_alpha  # noqa: E402

READY = SETTLE_H + BASELINE_MIN_H + 24


def flat(n, v=45.0, noise=0.05, seed=0):
    return list(v + np.random.default_rng(seed).normal(0, noise, n))


def test_normal_flat():
    assert probe_level(100, flat(READY)).level == Level.NORMAL


def test_ea_thresholds_deep():
    h = flat(READY)
    assert probe_level(100, h[:-1] + [61.0]).level == Level.SIAGA
    assert probe_level(100, h[:-2] + [81.0, 81.5]).level == Level.AWAS


def test_awas_needs_two_readings():
    h = flat(READY)
    assert probe_level(100, h[:-1] + [81.0]).level == Level.SIAGA


def test_ds18b20_reset_value_ignored():
    h = flat(READY)
    assert probe_level(100, h + [85.0]).level == Level.NORMAL
    assert probe_level(100, h + [85.0, 85.0]).level == Level.NORMAL


def test_shallow_60_is_waspada():
    h = flat(READY, v=52.0)
    assert probe_level(30, h[:-1] + [61.0]).level == Level.WASPADA
    assert probe_level(100, h[:-1] + [61.0]).level == Level.SIAGA


def test_baseline_frozen_catches_slow_ramp():
    """Bug lama: median 7 hari bergulir ikut naik. Kenaikan 0,5 C/hari harus tertangkap oleh aturan tren."""
    base = flat(READY)
    ramp = [base[-1] + 0.5 * i / 24 for i in range(1, 8 * 24)]
    v = probe_level(100, base + ramp)
    assert v.level == Level.WASPADA
    assert any("tren" in r for r in v.reasons)


def test_baseline_states():
    assert learn_baseline(flat(10))[0].status == "settling"
    assert learn_baseline(flat(SETTLE_H + 24))[0].status == "learning"
    assert learn_baseline(flat(READY))[0].status == "ready"


def test_theil_sen_slope():
    y = [0.5 * i / 24 for i in range(168)]
    assert abs(theil_sen_per_day(y) - 0.5) < 1e-6


def test_gas_alone_caps_at_waspada():
    v = assess_block("X", {100: flat(READY)}, {"MQ": [400.0] * 30 + [2000.0]})
    assert v.level == Level.WASPADA and v.gas_flags


def test_estimate_alpha_recovers_value():
    alpha, dz = 6e-7, 0.20
    d = np.sqrt(2 * alpha / (2 * np.pi / 86400))
    t = np.arange(24 * 10)
    up = 5 * np.sin(2 * np.pi * t / 24)
    low = 5 * np.exp(-dz / d) * np.sin(2 * np.pi * t / 24 - dz / d)
    assert abs(estimate_alpha(up, low, dz) - alpha) / alpha < 0.02


def test_thermal_detector_finds_source_and_depth():
    from simulate_nodes import simulate_all
    df, truth, _ = simulate_all()
    g = df[df.node == "N3"]
    cols = ["t_10", "t_30", "t_60", "t_100", "t_150"]
    learn = slice(SETTLE_H, SETTLE_H + 14 * 24)
    det = ThermalDetector(g.t_air.to_numpy(), g[cols].to_numpy(), [0.1, 0.3, 0.6, 1.0, 1.5], learn)
    end = det.fit(len(g), t_min=learn.stop - 24)
    assert end.detected and abs(end.z_m - truth["N3"]["z_m"]) <= 0.1
    control = df[df.node == "N1"]
    det0 = ThermalDetector(control.t_air.to_numpy(), control[cols].to_numpy(), [0.1, 0.3, 0.6, 1.0, 1.5], learn)
    assert not det0.fit(len(control), t_min=learn.stop - 24).detected


def test_assess_readings_on_simulation():
    from simulate_nodes import simulate_all
    df, _, _ = simulate_all()
    early = {v.block: v.level for v in assess_readings(df, until="2026-10-15 00:00+07:00")}
    assert all(lv == Level.NORMAL for lv in early.values())
    late = {v.block: v.level for v in assess_readings(df)}
    assert late["D1 (N3)"] >= Level.WASPADA and late["A (N1)"] == Level.NORMAL


def test_fwi_classes():
    from bara.weather import DC_CLASSES, FFMC_CLASSES, classify
    assert classify(351, DC_CLASSES) == "sangat kering" and classify(100, DC_CLASSES) == "basah"
    assert classify(83, FFMC_CLASSES) == "sangat mudah terbakar"
    assert isinstance(pd.Timestamp("2026-10-30"), pd.Timestamp)


# ---------------------------------------------------------------- v0.5.0: Permen PU, pasca-kebakaran, AI
from bara.assess import AI_LEVEL_SCORE, ai_effect  # noqa: E402
from bara.risk import permen_label, postfire_level  # noqa: E402


def test_permen_labels():
    assert permen_label(54.9) == "suhu normal TPA"
    assert permen_label(57) == "peningkatan aktivitas biologi"
    assert permen_label(65) == "peningkatan aktivitas biologi abnormal"
    assert permen_label(71) == "telah terjadi kebakaran TPA"


def test_deep_awas_at_permen_70_shallow_at_80():
    h = flat(READY)
    assert probe_level(100, h[:-2] + [71.0, 71.5]).level == Level.AWAS
    assert probe_level(30, flat(READY, v=50)[:-2] + [71.0, 71.5]).level < Level.AWAS  # dangkal: AWAS baru di atas 80 C


def _hourly_daily(values_per_day):
    return [v for v in values_per_day for _ in range(24)]


def test_postfire_needs_reference():
    v = postfire_level(100, flat(READY), None)
    assert v.status == "acuan belum ada" and v.level == Level.NORMAL


def test_postfire_cooling_is_quiet_and_stall_is_flagged():
    days = 30
    ref = _hourly_daily([40.0] * days)
    cooling = _hourly_daily([40 + 15 * np.exp(-d / 40) for d in range(days)])
    stalled = _hourly_daily([40 + 15 - 0.01 * d for d in range(days)])
    assert postfire_level(100, cooling, ref).level == Level.NORMAL
    v = postfire_level(100, stalled, ref)
    assert v.status == "berhenti mendingin" and v.level >= Level.WASPADA


def test_postfire_rekindle_rises_against_curve():
    ref = _hourly_daily([40.0] * 30)
    hot = [40 + 15 * np.exp(-d / 40) + (0.8 * (d - 20) if d > 20 else 0) for d in range(30)]
    v = postfire_level(100, _hourly_daily(hot), ref)
    assert v.status == "naik" and v.level >= Level.WASPADA


def test_postfire_mode_on_simulation():
    from simulate_nodes import simulate_all
    df, _, _ = simulate_all()
    late = {v.block: v for v in assess_readings(df)}
    assert late["D1 (N3)"].mode == "pasca_kebakaran" and late["D1 (N3)"].level >= Level.WASPADA
    assert any(p.status == "naik" for p in late["D1 (N3)"].postfire)
    stall = {v.block: v for v in assess_readings(df, until="2026-10-18 23:00+07:00")}
    assert any(p.status == "berhenti mendingin" for p in stall["B (N4)"].postfire)


def test_ai_effect_rules():
    row = {"detected": True, "score": 5.0}
    assert ai_effect(row, "normal") == "perhatian"
    assert ai_effect({"detected": True, "score": AI_LEVEL_SCORE}, "normal") == "naikkan"
    assert ai_effect({"detected": True, "score": 100.0}, "pasca_kebakaran") == "perhatian"
    assert ai_effect({"detected": False, "score": 0.1}, "normal") == "tidak"


def test_threshold_floor():
    from simulate_nodes import simulate_all
    df, _, _ = simulate_all()
    g = df[df.node == "N3"]
    cols = ["t_10", "t_30", "t_60", "t_100", "t_150"]
    learn = slice(SETTLE_H, SETTLE_H + 14 * 24)
    det = ThermalDetector(g.t_air.to_numpy(), g[cols].to_numpy(), [0.1, 0.3, 0.6, 1.0, 1.5], learn, min_threshold=500.0)
    assert det.threshold >= 500.0 and not det.calibrated
