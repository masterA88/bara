"""Peran tiap node: normal, kontrol (acuan suhu latar), atau pasca-kebakaran.

Node di blok bekas terbakar memakai mode pasca-kebakaran dan dibandingkan dengan node kontrol di sampah yang tidak
terbakar pada kedalaman yang sama (brief DRA 2026-10-30-bara-field-followup, perubahan 1; EA SC010066 6.1.1:
penyelesaian dinilai dengan membandingkan data titik panas dengan kondisi latar lokasi).

Konfigurasi lapangan dibaca dari data/nodes.json jika ada. Tanpa file itu dipakai konfigurasi simulasi di bawah.
Format: {"N1": {"mode": "kontrol"}, "N3": {"mode": "pasca_kebakaran", "reference": "N1", "since": "2026-09-24"}}
"""
from __future__ import annotations

import json
from pathlib import Path

CONFIG = Path(__file__).resolve().parent.parent / "data" / "nodes.json"
MODES = ("normal", "kontrol", "pasca_kebakaran")

SIM_NODES = {
    "N1": {"mode": "kontrol"},
    "N2": {"mode": "normal"},
    "N3": {"mode": "pasca_kebakaran", "reference": "N1", "since": "2026-09-24"},
    "N4": {"mode": "pasca_kebakaran", "reference": "N1", "since": "2026-09-24"},
}


def load(simulated: bool = True) -> dict[str, dict]:
    if CONFIG.exists():
        cfg = json.loads(CONFIG.read_text())
    else:
        cfg = SIM_NODES if simulated else {}
    for node, c in cfg.items():
        if c.get("mode", "normal") not in MODES:
            raise ValueError(f"mode node {node} tidak dikenal: {c.get('mode')}")
    return cfg


def role(cfg: dict[str, dict], node: str) -> dict:
    return {"mode": "normal", **cfg.get(node, {})}
