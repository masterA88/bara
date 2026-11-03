"""API BARA: membungkus mesin Python (lapisan aturan, lapisan AI, cuaca) untuk frontend web.

Run: .venv/bin/uvicorn api.main:app --port 8000 --reload
Dokumentasi otomatis: http://localhost:8000/docs
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from bara import nodes as node_cfg  # noqa: E402
from bara.assess import AI_LEVEL_SCORE, ai_effect, assess_readings, depth_columns, is_simulated, node_frames, thermal_scan  # noqa: E402
from bara.risk import ACTIONS, Level, permen_label  # noqa: E402
from bara.site import AREA_HA, BBOX, BLOCKS, FIRES, LAT, LON  # noqa: E402

PROC = ROOT / "data" / "processed"
SOURCES = {"sim": PROC / "sim_readings.csv", "field": PROC / "readings.csv"}
WIB = timezone(timedelta(hours=7))

app = FastAPI(title="BARA API", version="0.5.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
                   allow_methods=["*"], allow_headers=["*"])


def _path(source: str) -> Path:
    p = SOURCES.get(source)
    if p is None or not p.exists():
        raise HTTPException(404, f"Sumber data '{source}' belum ada. Jalankan simulasi atau kirim data node.")
    return p


@lru_cache(maxsize=8)
def _readings(source: str, mtime: float) -> pd.DataFrame:
    df = pd.read_csv(SOURCES[source])
    df["ts"] = pd.to_datetime(df["ts"])
    return df


def readings(source: str) -> pd.DataFrame:
    p = _path(source)
    return _readings(source, p.stat().st_mtime)


@lru_cache(maxsize=8)
def _scan(source: str, mtime: float) -> pd.DataFrame:
    pre = PROC / "thermal_scan.csv"
    if source == "sim" and pre.exists() and pre.stat().st_mtime >= mtime:
        s = pd.read_csv(pre)
    else:
        s = thermal_scan(_readings(source, mtime))
    for c in ("ts", "onset", "learn_end"):
        if c in s:
            s[c] = pd.to_datetime(s[c])
    return s


def scan(source: str) -> pd.DataFrame:
    p = _path(source)
    return _scan(source, p.stat().st_mtime)


def _iso(t) -> str | None:
    return None if t is None or pd.isna(t) else pd.Timestamp(t).isoformat()


def _num(v, nd=2):
    return None if v is None or (isinstance(v, float) and np.isnan(v)) else round(float(v), nd)


def _until(df: pd.DataFrame, until: str | None) -> pd.Timestamp:
    return pd.Timestamp(until) if until else df["ts"].max()


@app.get("/api/site")
def site():
    outline = ROOT / "data" / "site_outline.geojson"
    return {
        "outline": json.loads(outline.read_text()) if outline.exists() else None,
        "name": "TPA Putri Cempo", "lat": LAT, "lon": LON, "bbox": BBOX, "area_ha": AREA_HA,
        "blocks": [{"id": k, **v} for k, v in BLOCKS.items()],
        "fires": [{"start": f.start.isoformat(), "end": f.end.isoformat() if f.end else None, "note": f.note,
                   "start_exact": f.start_exact} for f in FIRES],
    }


def _events(source: str) -> pd.DataFrame:
    p = PROC / ("sim_events.csv" if source == "sim" else "events.csv")
    if not p.exists() or p.stat().st_size == 0:
        return pd.DataFrame(columns=["ts", "node", "block", "type", "note"])
    e = pd.read_csv(p)
    e["ts"] = pd.to_datetime(e["ts"])
    return e


@app.get("/api/status")
def status(source: str = "sim", until: str | None = None):
    """Level per blok pada waktu `until`: lapisan aturan, mode pasca-kebakaran, lapisan AI, dan level gabungan."""
    df = readings(source)
    t = _until(df, until)
    sc = scan(source)
    cfg = node_cfg.load(is_simulated(df))
    frames = {n: g for (n, _), g in node_frames(df, t).items()}
    ev = _events(source)
    out = []
    for v in assess_readings(df, t):
        block, node = v.block.split(" (")[0], v.block.split("(")[-1].rstrip(")")
        g = frames[node]
        role = node_cfg.role(cfg, node)
        ai = None
        s = sc[(sc["node"] == node) & (sc["ts"] <= t)] if not sc.empty else sc
        if not s.empty:
            r = s.iloc[-1]
            ai = {"detected": bool(r["detected"]), "score": _num(r["score"], 3), "z_m": _num(r["z_m"]),
                  "onset": _iso(r["onset"]) if bool(r["detected"]) else None, "effect": ai_effect(r, role["mode"]),
                  "calibrated": bool(r.get("calibrated", True)), "alpha": float(r["alpha"]),
                  "alpha_source": r["alpha_source"], "learn_end": _iso(r["learn_end"])}
        level = v.level
        if ai and ai["effect"] == "naikkan":
            level = max(level, Level.WASPADA)
        action = ACTIONS[Level(level)] if level == v.level else \
            "Cek lapangan: model termal melihat panas tumbuh sebelum ambang EA tercapai."
        cols = depth_columns(g)
        last = g.iloc[-1]
        pf = [{"depth_cm": p.depth_cm, "status": p.status, "level": p.level.name, "sentence": p.sentence,
               "delta_c": _num(p.delta_c), "expect_c": _num(p.expect_c), "tau_days": _num(p.tau_days, 0),
               "start_class": p.start_class, "flags": p.flags, "days_below": p.days_below} for p in v.postfire]
        e = ev[(ev["node"] == node) & (ev["ts"] <= t)]
        out.append({
            "node": node, "block": block, "level": Level(level).name, "rule_level": v.level.name, "action": action,
            "mode": role["mode"], "reference": role.get("reference"), "since": role.get("since"),
            "commissioning": v.commissioning, "reasons": v.reasons, "gas_flags": v.gas_flags, "ai": ai, "postfire": pf,
            "events": [{"ts": _iso(x.ts), "type": x.type, "note": x.note} for x in e.itertuples()],
            "latest": {"ts": _iso(g.index[-1]), "t_air": _num(last.get("t_air")),
                       "probes": {str(d): _num(last[c]) for d, c in sorted(cols.items())},
                       "permen": {str(d): permen_label(last[c]) for d, c in sorted(cols.items())}},
            "probes": [{"depth_cm": p.depth_cm, "temp_c": _num(p.temp_c), "baseline_c": _num(p.baseline.value),
                        "baseline_status": p.baseline.status, "slope_c_day": _num(p.slope_c_day, 3),
                        "level": p.level.name, "permen": permen_label(p.temp_c)} for p in v.probes],
        })
    order = {lv.name: lv.value for lv in Level}
    out.sort(key=lambda r: (-order[r["level"]], -((r["ai"] or {}).get("score") or 0), r["block"]))
    return {"source": source, "simulated": is_simulated(df), "until": _iso(t), "ai_level_score": AI_LEVEL_SCORE,
            "range": {"start": _iso(df["ts"].min()), "end": _iso(df["ts"].max())}, "blocks": out}


@app.get("/api/nodes/{node}/series")
def series(node: str, source: str = "sim", until: str | None = None):
    """Suhu per jam per kedalaman, skor AI, dan (untuk node pasca-kebakaran) selisih harian dengan node kontrol."""
    df = readings(source)
    t = _until(df, until)
    frames = {n: g for (n, _), g in node_frames(df, t).items()}
    if node not in frames:
        raise HTTPException(404, f"Node {node} tidak ada")
    g = frames[node]
    cols = depth_columns(g)
    rows = [{"ts": _iso(ts), "t_air": _num(r.get("t_air")), **{f"t_{d}": _num(r[c]) for d, c in cols.items()}}
            for ts, r in g.iterrows()]
    sc = scan(source)
    s = sc[(sc["node"] == node) & (sc["ts"] <= t)] if not sc.empty else sc
    ai = [{"ts": _iso(r.ts), "score": _num(r.score, 3), "detected": bool(r.detected), "z_m": _num(r.z_m)}
          for r in s.itertuples()]
    postfire = None
    v = next((v for v in assess_readings(df, t) if v.block.endswith(f"({node})")), None)
    if v is not None and v.postfire:
        start = g.index[0].normalize()
        postfire = {
            "days": [_iso(start + pd.Timedelta(days=k)) for k in range(max(len(p.delta_series) for p in v.postfire))],
            "depths": {str(p.depth_cm): {"delta": [_num(x) for x in p.delta_series],
                                          "expect": [_num(x) for x in p.expect_series]} for p in v.postfire},
            "limit_c": 10.0,
        }
    ev = _events(source)
    e = ev[(ev["node"] == node) & (ev["ts"] <= t)]
    return {"node": node, "depths_cm": sorted(cols), "temps": rows, "ai": ai, "postfire": postfire,
            "events": [{"ts": _iso(x.ts), "type": x.type, "note": x.note} for x in e.itertuples()]}


@app.get("/api/weather")
def weather(days: int = Query(365, ge=30, le=4000)):
    p = PROC / "weather_index.csv"
    if not p.exists():
        raise HTTPException(404, "Jalankan data/fetch_weather.py lalu data/backtest_weather.py")
    w = pd.read_csv(p, parse_dates=["date"])
    last = w.iloc[-1]
    recent = w[w["date"] >= w["date"].max() - pd.Timedelta(days=days)]
    return {
        "latest": {"date": last["date"].date().isoformat(), "dc": round(float(last.dc)), "dc_class": last.dc_class,
                   "dc_pct_dry_season": round(float(last.dc_pct_dry_season), 3), "ffmc": round(float(last.ffmc), 1),
                   "ffmc_class": last.ffmc_class},
        "series": [{"date": d.date().isoformat(), "dc": round(float(dc)), "ffmc": round(float(f), 1)}
                   for d, dc, f in zip(recent["date"], recent["dc"], recent["ffmc"])],
    }


@app.get("/api/comparison")
def comparison():
    """Perbandingan waktu deteksi AI dan aturan pada simulasi."""
    sc_path, truth_path = PROC / "thermal_scan.csv", PROC / "sim_truth.json"
    rules_path = PROC / "rules_timeline.csv"
    if not (sc_path.exists() and rules_path.exists()):
        raise HTTPException(404, "Jalankan data/run_thermal.py")
    sc = pd.read_csv(sc_path, parse_dates=["ts", "onset"])
    rules = pd.read_csv(rules_path, parse_dates=["ts"])
    truth = json.loads(truth_path.read_text()) if truth_path.exists() else {}
    scen = {"N1": "Kontrol di sampah tidak terbakar", "N4": "Blok terbakar, pendinginan berhenti, injeksi hari ke-21"}
    out = []
    for node, g in sc.groupby("node"):
        block, mode = g["block"].iloc[0], g["mode"].iloc[0]
        r = rules[rules["block"] == f"{block} ({node})"]
        hit = g[g["detected"]].head(1)
        lift = g[g["detected"] & (g["score"] >= AI_LEVEL_SCORE)].head(1)
        w = r[r["level_n"] >= 1].head(1)
        tr = truth.get(node)
        onset = pd.Timestamp(tr["onset"]) if tr else None
        hours = lambda t: None if onset is None or t is None else round((t - onset).total_seconds() / 3600)
        out.append({
            "node": node, "block": block, "mode": mode, "truth": tr, "scenario": scen.get(node),
            "ai_first": _iso(hit.ts.iloc[0]) if not hit.empty else None,
            "ai_hours_after_onset": hours(hit.ts.iloc[0]) if not hit.empty else None,
            "ai_lift_hours_after_onset": hours(lift.ts.iloc[0]) if not lift.empty and mode != "pasca_kebakaran" else None,
            "ai_z_m": _num(hit.z_m.iloc[0]) if not hit.empty else None,
            "rule_first": _iso(w.ts.iloc[0]) if not w.empty else None,
            "rule_hours_after_onset": hours(w.ts.iloc[0]) if not w.empty else None,
        })
    return {"rows": out, "ai_level_score": AI_LEVEL_SCORE,
            "note": "Satu simulasi 30 hari dengan model fisika yang sama dengan detektor, jadi hasil ini batas atas. "
                    "AI hanya menaikkan level jika skor >= 20; di blok pasca-kebakaran AI hanya informasi."}


class Reading(BaseModel):
    node: str
    block: str
    ts: str | None = None
    seq: int | None = None
    t_10: float | None = None
    t_30: float | None = None
    t_60: float | None = None
    t_100: float | None = None
    t_150: float | None = None
    tc_100: float | None = None
    t_air: float | None = None
    rh: float | None = None
    mq_raw: float | None = None


@app.post("/api/ingest", status_code=204)
def ingest(r: Reading):
    """Penerima data node (pengganti ingest/server.py). Belum ada token: jangan dibuka ke internet."""
    rec = r.model_dump()
    rec["ts"] = rec["ts"] or datetime.now(WIB).isoformat(timespec="seconds")
    rec["simulated"] = False
    p = SOURCES["field"]
    p.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([rec]).to_csv(p, mode="a", header=not p.exists(), index=False)
