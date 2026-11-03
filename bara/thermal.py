"""Model termal berbasis fisika: komponen AI utama BARA.

Ide (brief DRA 2026-10-30, perubahan 3): tiap tali probe dimodelkan sebagai kolom sampah 1D yang menghantarkan
panas, dipaksa di permukaan oleh suhu udara dari DHT22 node itu sendiri.
  rho_c dT/dt = k d2T/dz2 + g_bg + s(z, t)
Model ini linear terhadap kekuatan sumber, jadi respons sumber panas di kedalaman z yang menyala pada jam t0
adalah respons satuan yang digeser waktunya (pendekatan kamus, arXiv 2610.21301). Untuk tiap kandidat (z, t0)
kekuatan sumber dicari dengan kuadrat terkecil, bersama satu suku latar (panas biologis normal) sebagai
parameter pengganggu. Statistik deteksi adalah rasio kemungkinan (penurunan RSS dalam satuan varians derau),
dan ambangnya dikalibrasi pada data commissioning node itu sendiri. Tidak butuh data kebakaran.

Difusivitas diperkirakan di tempat dari rasio amplitudo gelombang harian antara dua probe dangkal
(metode fisika tanah standar). Tanpa probe 10 cm, dipakai nilai awal 5e-7 m2/s dari literatur
(3,0e-7 sampai 7,0e-7 di empat lokasi lapangan; brief DRA [24]).

Batas: model ini hanya konduksi. Konveksi gas, air hujan, dan sampah baru yang ditimbun di atas probe
tidak dimodelkan. Satu tali probe hanya melihat panas dalam jarak sekitar 1 sampai 2 m.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np
from scipy.sparse import diags
from scipy.sparse.linalg import splu

DT_S = 3600.0
DZ_M = 0.05
DEPTH_M = 3.0
Z = np.arange(0.0, DEPTH_M + DZ_M / 2, DZ_M)
K_W_MK = 1.0                 # konduktivitas, rentang in situ 0,86 sampai 1,32 W/m C (brief DRA [28])
ALPHA_PRIOR = 5e-7           # m2/s
ALPHA_RANGE = (2e-7, 1.2e-6)
SOURCE_WIDTH_M = 0.10
CAND_Z = np.round(np.arange(0.15, 2.05, 0.05), 2)
ONSET_STEP_H = 3
THRESHOLD_FACTOR = 3.0       # ambang = 3x statistik maksimum di jendela tanpa sumber (seperti uji DRA)
UNSTABLE_SLOPE_C_DAY = 0.05  # probe >= 60 cm yang naik/turun lebih dari ini saat commissioning: ambang tidak andal
# Batas yang diketahui (brief DRA field-followup 6.4): pada node kontrol biasa, detektor ini memberi alarm palsu di
# 8 dari 10 simulasi 60 hari karena ambangnya tidak stabil (47 sampai 1.662). Karena itu bara/assess.py hanya menaikkan
# level jika skor >= 20. Perbaikan sebenarnya (kalibrasi pada simulasi nol 90 hari) dijadwalkan setelah 8 November.
OMEGA = 2 * np.pi / 86400.0


def gauss(zc: float) -> np.ndarray:
    return np.exp(-0.5 * ((Z - zc) / SOURCE_WIDTH_M) ** 2)


@lru_cache(maxsize=16)
def _lu(alpha: float):
    n, r = len(Z), alpha * DT_S / DZ_M**2
    main, lower, upper = np.full(n, 1 + 2 * r), np.full(n - 1, -r), np.full(n - 1, -r)
    main[0], upper[0] = 1.0, 0.0      # permukaan: suhu ditetapkan (suhu udara)
    main[-1], lower[-1] = 1.0, 0.0    # dasar 3 m: suhu ditetapkan
    return splu(diags([lower, main, upper], [-1, 0, 1], format="csc"))


def simulate(alpha: float, surface: np.ndarray, bottom: float, T0: np.ndarray, probes_m: np.ndarray,
             g: np.ndarray | float = 0.0, source=None) -> tuple[np.ndarray, np.ndarray]:
    """Euler implisit per jam. surface: suhu permukaan per jam. source(h) -> W/m3 per titik grid."""
    lu, rho_c = _lu(alpha), K_W_MK / alpha
    idx = np.rint(np.asarray(probes_m) / DZ_M).astype(int)
    T = T0.copy()
    out = np.empty((len(surface), len(idx)))
    for h, s in enumerate(surface):
        rhs = T + DT_S * g / rho_c
        if source is not None:
            rhs = rhs + DT_S * source(h) / rho_c
        rhs[0], rhs[-1] = s, bottom
        T = lu.solve(rhs)
        out[h] = T[idx]
    return out, T


def steady_profile(surface_mean: float, bottom: float) -> np.ndarray:
    return surface_mean + (bottom - surface_mean) * Z / DEPTH_M


@lru_cache(maxsize=64)
def unit_response(alpha: float, zc: float, hours: int, probes: tuple) -> np.ndarray:
    """Respons probe terhadap sumber 1 W/m3 (Gaussian di zc) yang menyala di jam 0, kondisi batas nol."""
    zero = np.zeros(hours)
    out, _ = simulate(alpha, zero, 0.0, np.zeros(len(Z)), np.array(probes), source=lambda h: gauss(zc))
    return out


@lru_cache(maxsize=16)
def background_response(alpha: float, hours: int, probes: tuple) -> np.ndarray:
    out, _ = simulate(alpha, np.zeros(hours), 0.0, np.zeros(len(Z)), np.array(probes), g=1.0)
    return out


def estimate_alpha(t_upper: np.ndarray, t_lower: np.ndarray, dz_m: float) -> float | None:
    """Difusivitas dari rasio amplitudo harmonik harian dua probe (jarak dz_m). None jika tidak terbaca."""
    n = (min(len(t_upper), len(t_lower)) // 24) * 24
    if n < 72:
        return None

    def amp(x):
        x = np.asarray(x[:n], float) - np.mean(x[:n])
        c = np.fft.rfft(x)
        return 2 * abs(c[n // 24]) / n

    a1, a2 = amp(t_upper), amp(t_lower)
    if a2 <= 0 or a1 <= a2:
        return None
    alpha = OMEGA * dz_m**2 / (2 * np.log(a1 / a2) ** 2)
    return float(np.clip(alpha, *ALPHA_RANGE))


@dataclass
class Detection:
    t_end: int
    lr: float
    threshold: float
    z_m: float | None
    onset_h: int | None
    strength_w_m3: float | None

    @property
    def detected(self) -> bool:
        return self.lr > self.threshold

    @property
    def score(self) -> float:
        return self.lr / self.threshold if self.threshold > 0 else 0.0


class ThermalDetector:
    """Satu detektor per tali probe. Data per jam: air (H,), temps (H, P) dengan kedalaman probes_m."""

    def __init__(self, air: np.ndarray, temps: np.ndarray, probes_m: list[float], learn: slice,
                 alpha: float | None = None, min_threshold: float = 0.0):
        self.air = np.asarray(air, float)
        self.obs = np.asarray(temps, float)
        self.probes = tuple(float(p) for p in probes_m)
        self.learn = learn
        self.H = len(self.air)
        self.alpha = alpha or self._alpha_from_data() or ALPHA_PRIOR
        self.alpha_source = "data" if alpha is None and self._alpha_from_data() else "prior"
        self._baseline()
        self.R = {zc: unit_response(self.alpha, float(zc), self.H, self.probes) for zc in CAND_Z}
        self.B = background_response(self.alpha, self.H, self.probes)
        own = self._calibrate()
        self.calibrated = self._stable_commissioning()
        # Ambang sendiri bisa runtuh ke 0 jika commissioning sedang mendingin (blok bekas terbakar). Pakai ambang node
        # kontrol sebagai batas bawah (brief DRA field-followup, perubahan 4).
        self.own_threshold = own
        self.threshold = max(own, min_threshold)

    def _stable_commissioning(self) -> bool:
        o = self.obs[self.learn]
        for j, z in enumerate(self.probes):
            if z < 0.6:
                continue
            y = o[:, j]
            y = y[~np.isnan(y)]
            if len(y) < 48:
                continue
            slope = np.polyfit(np.arange(len(y)) / 24.0, y, 1)[0]
            if abs(slope) > UNSTABLE_SLOPE_C_DAY:
                return False
        return True

    def _alpha_from_data(self) -> float | None:
        p = list(self.probes)
        if len(p) < 2 or p[0] > 0.15:
            return None
        o = self.obs[self.learn]
        return estimate_alpha(o[:, 0], o[:, 1], p[1] - p[0])

    def _baseline(self) -> None:
        o = self.obs[self.learn]
        bottom = float(np.nanmean(o[:, -1]))
        T0 = steady_profile(float(np.nanmean(self.air[self.learn])), bottom)
        base, _ = simulate(self.alpha, self.air, bottom, T0, np.array(self.probes))
        self.offset = np.nanmean(o - base[self.learn], axis=0)
        self.resid = self.obs - base - self.offset
        sig = np.nanstd(self.resid[self.learn], axis=0)
        self.sigma = np.where(sig > 0.05, sig, 0.05)

    def fit(self, t_end: int, t_min: int = 0) -> Detection:
        y = np.nan_to_num(self.resid[:t_end] / self.sigma)
        b = self.B[:t_end] / self.sigma
        bb = float((b * b).sum())
        rss0 = float((y * y).sum()) - (float((b * y).sum()) ** 2 / bb if bb > 0 else 0.0)
        best = (rss0, None, None, None)
        for zc, Rz in self.R.items():
            for t0 in range(t_min, t_end - 6, ONSET_STEP_H):
                x = np.zeros_like(y)
                x[t0:] = Rz[: t_end - t0] / self.sigma
                xx, xb = float((x * x).sum()), float((x * b).sum())
                xy, by = float((x * y).sum()), float((b * y).sum())
                det = xx * bb - xb * xb
                if det <= 1e-12:
                    continue
                q = (xy * bb - by * xb) / det
                if q <= 0:
                    continue
                c = (by * xx - xy * xb) / det
                r = y - q * x - c * b
                rss = float((r * r).sum())
                if rss < best[0]:
                    best = (rss, float(zc), t0, q)
        return Detection(t_end, rss0 - best[0], getattr(self, "threshold", 0.0), best[1], best[2], best[3])

    def _calibrate(self) -> float:
        lo, hi = self.learn.start or 0, self.learn.stop
        stats = [self.fit(t, t_min=lo).lr for t in range(lo + 48, hi + 1, 12)]
        return THRESHOLD_FACTOR * max(stats) if stats else 50.0

    def scan(self, step_h: int = 3) -> list[Detection]:
        start = self.learn.stop
        return [self.fit(t, t_min=start - 24) for t in range(start + step_h, self.H + 1, step_h)]
