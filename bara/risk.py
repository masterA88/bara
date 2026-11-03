"""Mesin aturan BARA (lapisan aturan; lapisan AI ada di bara/thermal.py).

Semua deret diasumsikan per jam (bara/assess.py meratakan bacaan node ke per jam).

Aturan dan sumbernya:
- Ambang suhu in-waste EA SC010066 (2007) Tabel 23: >10 C di atas suhu operasi normal (selidiki), >60 C (di atas
  suhu anaerob biasa), >80 C (titik panas mungkin ada atau berkembang).
- >60 C dibuat bergantung kedalaman (brief DRA 2026-10-30, perubahan 5): lapisan aerob dangkal bisa normal di atas
  60 C (EA Tabel 3: fase aerob 80 sampai 90 C; TPA terbuka Maceio rata-rata 54 C di 25 cm saat kemarau). Pada probe
  <= 60 cm, >60 C saja memberi WASPADA; SIAGA butuh >60 C ditambah tren atau +10 C. Probe >= 100 cm tetap SIAGA.
- AWAS (>80 C) harus terbaca pada dua jam berturut-turut, karena nilai reset DS18B20 adalah +85 C (datasheet
  Rev 6). Bacaan tepat 85,00 C dibuang sebagai gangguan.
- Baseline per probe dipelajari saat commissioning lalu dibekukan (perubahan 1): 72 jam pertama dibuang, lalu median
  7 hari menjadi baseline dan aturan mulai aktif. Sesudahnya baseline hanya bergeser lewat EWMA 30 hari, dan hanya
  saat residu probe kecil. Baseline lama (median 7 hari bergulir) ikut naik bersama titik panas yang lambat.
  Model termal (bara/thermal.py) memakai jendela commissioning yang lebih panjang, 14 hari.
- Aturan tren (perubahan 4): kemiringan Theil-Sen residu 7 hari, 0,3 C/hari untuk probe >= 60 cm dan 0,6 C/hari
  untuk 30 cm. Analog: tren sumur gas Bridgeton 3 sampai 5 F dalam kurang dari seminggu (Thalhamer 2013), sekitar
  0,24 sampai 0,4 C/hari. Pemanasan biologis normal 0,06 sampai 0,16 C/hari. Kenaikan 5 C/24 jam tetap ada sebagai
  cadangan untuk kejadian cepat.
- Gas hanya penanda tren (EA: CO "can not be regarded as a reliable indicator"); gas saja maksimal WASPADA.
- Probe 10 cm hanya untuk memperkirakan difusivitas; tidak diberi aturan karena didominasi cuaca.
- Permen PU 03/PRT/M/2013 Lampiran III Tabel 10 (acuan nasional): < 55 C suhu normal TPA, 55 sampai 60 C peningkatan
  aktivitas biologi, 60 sampai 70 C peningkatan abnormal, > 70 C telah terjadi kebakaran TPA. Label ini ditampilkan di
  tiap probe. Untuk probe >= 100 cm, AWAS dipicu > 70 C dua jam berturut-turut; probe 30 dan 60 cm tetap 80 C karena
  panas aerob dangkal bisa normal (brief DRA field-followup, perubahan 3). Status hukum lampiran belum dicek.
- Mode pasca-kebakaran untuk node di blok bekas terbakar: lihat postfire_level() di bawah.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from statistics import median

import numpy as np


class Level(IntEnum):
    NORMAL = 0
    WASPADA = 1
    SIAGA = 2
    AWAS = 3


EA_ABOVE_BASELINE_C = 10.0
EA_INVESTIGATE_C = 60.0
EA_HOTSPOT_C = 80.0
PERMEN_FIRE_C = 70.0
PERMEN_TABEL10 = [(55.0, "suhu normal TPA"), (60.0, "peningkatan aktivitas biologi"),
                  (70.0, "peningkatan aktivitas biologi abnormal"), (float("inf"), "telah terjadi kebakaran TPA")]
DS18B20_RESET_C = 85.0
SHALLOW_MAX_DEPTH_CM = 60
MIN_RULE_DEPTH_CM = 30

SETTLE_H = 72
BASELINE_MIN_H = 7 * 24
BASELINE_TARGET_H = 14 * 24
EWMA_TAU_H = 30 * 24
EWMA_FREEZE_RESID_C = 3.0

RISE_WINDOW_H = 168
RISE_SLOPE_DEEP = 0.3        # C/hari, probe >= 60 cm
RISE_SLOPE_SHALLOW = 0.6     # C/hari, probe 30 cm
FAST_RISE_C_24H = 5.0        # cadangan untuk kejadian cepat

GAS_TREND_RATIO = 1.5
MIN_GAS_SAMPLES = 25

ACTIONS = {
    Level.NORMAL: "Pantau rutin.",
    Level.WASPADA: "Masukkan blok ini ke rute inspeksi shift berikutnya; cek dengan termometer IR atau kamera termal, catat di bot.",
    Level.SIAGA: "Periksa blok ini pada shift sekarang dan cari titik asap; siapkan injeksi sesuai prosedur DLH. Lapor ke koordinator.",
    Level.AWAS: "Kemungkinan titik panas. Lapor koordinator DLH segera, tangani dengan injeksi atau tanah penutup sesuai prosedur DLH, jauhkan alat berat.",
}
# Draf tim, menunggu SOP resmi DLH. Disesuaikan dengan praktik yang dilaporkan dalam notulensi tim
# (bible/lapangan/): inspeksi manual dalam enam shift, injeksi pada titik asap, rencana kamera termal genggam.


def clean(values: list[float]) -> list[float]:
    """Buang NaN dan nilai reset DS18B20 (tepat 85,00 C)."""
    return [v for v in values if v is not None and not np.isnan(v) and round(v, 2) != DS18B20_RESET_C]


@dataclass
class Baseline:
    value: float | None
    status: str             # "settling", "learning", "ready"
    hours_learned: int


def learn_baseline(series: list[float]) -> tuple[Baseline, list[float]]:
    """Kembalikan baseline dan deret baseline per jam (untuk residu). Deret penuh sejak node dipasang."""
    n = len(series)
    if n <= SETTLE_H:
        return Baseline(None, "settling", 0), [np.nan] * n
    learned = min(n - SETTLE_H, BASELINE_MIN_H)
    if learned < BASELINE_MIN_H:
        return Baseline(None, "learning", learned), [np.nan] * n
    base = median(series[SETTLE_H:SETTLE_H + learned])
    end_learn = SETTLE_H + learned
    path = [np.nan] * end_learn
    w = 1.0 / EWMA_TAU_H
    for v in series[end_learn:]:
        if abs(v - base) < EWMA_FREEZE_RESID_C:
            base = (1 - w) * base + w * v
        path.append(base)
    return Baseline(base, "ready", learned), path


def theil_sen_per_day(y: list[float]) -> float | None:
    if len(y) < 48:
        return None
    a = np.asarray(y, float)
    idx = np.linspace(0, len(a) - 1, min(len(a), 84)).astype(int)   # subsampel agar O(n^2) tetap ringan
    x, v = idx.astype(float), a[idx]
    i, j = np.triu_indices(len(x), 1)
    return float(np.median((v[j] - v[i]) / (x[j] - x[i]))) * 24


@dataclass
class ProbeVerdict:
    depth_cm: int
    temp_c: float
    baseline: Baseline
    slope_c_day: float | None
    level: Level
    reasons: list[str] = field(default_factory=list)


@dataclass
class BlockVerdict:
    block: str
    level: Level
    probes: list[ProbeVerdict]
    gas_flags: list[str]
    reasons: list[str]
    mode: str = "normal"
    postfire: list["PostfireVerdict"] = field(default_factory=list)

    @property
    def action(self) -> str:
        return ACTIONS[self.level]

    @property
    def commissioning(self) -> str:
        st = {p.baseline.status for p in self.probes}
        if st == {"ready"}:
            return "siap"
        h = min(p.baseline.hours_learned for p in self.probes) if self.probes else 0
        return f"commissioning ({h // 24} dari {BASELINE_MIN_H // 24} hari)"


def fmt(v: float, nd: int = 1, sign: bool = False) -> str:
    """Angka gaya Indonesia (koma desimal) untuk teks alasan."""
    t = f"{v:+.{nd}f}" if sign else f"{v:.{nd}f}"
    return t.replace(".", ",")


def permen_label(temp_c: float | None) -> str | None:
    if temp_c is None or np.isnan(temp_c):
        return None
    return next(name for upper, name in PERMEN_TABEL10 if temp_c < upper)


def probe_level(depth_cm: int, history: list[float], use_baseline: bool = True) -> ProbeVerdict:
    """history: suhu per jam sejak probe dipasang, nilai terakhir = sekarang.

    use_baseline=False untuk node pasca-kebakaran: aturan relatif terhadap baseline sendiri diganti postfire_level(),
    aturan absolut tetap berlaku.
    """
    h = clean(history)
    now = h[-1]
    shallow = depth_cm <= SHALLOW_MAX_DEPTH_CM
    base, path = learn_baseline(h)
    reasons: list[str] = []
    fire_c = EA_HOTSPOT_C if shallow else PERMEN_FIRE_C
    fire_src = "EA Tabel 23: titik panas mungkin ada" if shallow else "Permen PU 03/2013 Tabel 10: telah terjadi kebakaran TPA"

    above = use_baseline and base.value is not None and now - base.value > EA_ABOVE_BASELINE_C
    slope = None
    trend = False
    if use_baseline and base.status == "ready":
        resid = [v - b for v, b in zip(h[-RISE_WINDOW_H:], path[-RISE_WINDOW_H:]) if not np.isnan(b)]
        slope = theil_sen_per_day(resid)
        limit = RISE_SLOPE_SHALLOW if shallow and depth_cm < SHALLOW_MAX_DEPTH_CM else RISE_SLOPE_DEEP
        trend = slope is not None and slope > limit
    fast = len(h) > 24 and now - h[-25] > FAST_RISE_C_24H
    hot_persist = len(h) >= 2 and h[-1] > fire_c and h[-2] > fire_c

    level = Level.NORMAL
    if hot_persist:
        level = Level.AWAS
        reasons.append(f"{fmt(now)} C > {fire_c:.0f} C dua jam berturut-turut ({fire_src})")
    elif now > fire_c:
        level = Level.SIAGA
        reasons.append(f"{fmt(now)} C > {fire_c:.0f} C satu kali; menunggu konfirmasi bacaan berikutnya")
    elif now > EA_INVESTIGATE_C:
        if not shallow:
            level = Level.SIAGA
            reasons.append(f"{fmt(now)} C > {EA_INVESTIGATE_C:.0f} C di {depth_cm} cm (EA Tabel 23: di atas suhu anaerob biasa)")
        elif trend or above:
            level = Level.SIAGA
            reasons.append(f"{fmt(now)} C > {EA_INVESTIGATE_C:.0f} C di lapisan dangkal disertai tren atau kenaikan dari baseline")
        else:
            level = Level.WASPADA
            reasons.append(f"{fmt(now)} C > {EA_INVESTIGATE_C:.0f} C di lapisan dangkal; bisa normal untuk fase aerob, cek lapangan")

    if above:
        level = max(level, Level.WASPADA)
        reasons.append(f"{fmt(now - base.value, sign=True)} C di atas baseline {fmt(base.value)} C (EA Tabel 23: >10 C di atas normal)")
    if trend:
        level = max(level, Level.WASPADA)
        reasons.append(f"tren naik {fmt(slope, 2)} C/hari selama 7 hari (Theil-Sen; analog Bridgeton 0,24 sampai 0,4 C/hari)")
    if fast:
        level = max(level, Level.WASPADA)
        reasons.append(f"naik {fmt(now - h[-25])} C dalam 24 jam (cadangan kejadian cepat)")
    return ProbeVerdict(depth_cm, now, base, slope, level, reasons)


# ---------------------------------------------------------------- mode pasca-kebakaran
# Brief DRA 2026-10-30-bara-field-followup, perubahan 1 dan bagian 2.3. Deret yang dinilai adalah selisih harian
# (median) node blok terbakar dikurangi node kontrol pada kedalaman yang sama, sehingga pengaruh cuaca saling hapus.
POSTFIRE_DELTA_C = 10.0       # EA Tabel 23 (>10 C di atas normal), "normal" = node kontrol (EA 6.1.1.2 butir 3)
POSTFIRE_RISE_DEEP = 0.3      # C/hari terhadap kurva pendinginan, sama dengan aturan tren (analog Bridgeton)
POSTFIRE_RISE_SHALLOW = 0.6
POSTFIRE_STALL_SLOPE = -0.05  # C/hari selama 14 hari: pendinginan dianggap berhenti (penilaian DRA)
POSTFIRE_STALL_D = 14
POSTFIRE_COOLING_SLOPE = -0.02
POSTFIRE_TAU_RANGE = (14.0, 365.0)
POSTFIRE_CLEAR_D = 28         # analog 40 CFR 63.1961(a)(5)(viii): empat pembacaan mingguan berturut-turut
POSTFIRE_WATCH_D = 90         # EA 6.3: penyalaan ulang bisa terjadi "up to several months" kemudian


def daily_median(x: list[float]) -> np.ndarray:
    a = np.asarray(x, float)
    n = len(a) // 24
    return np.nanmedian(a[: n * 24].reshape(n, 24), axis=1) if n else np.array([])


def _ts_daily(y: np.ndarray) -> float | None:
    y = y[~np.isnan(y)]
    if len(y) < 3:
        return None
    i, j = np.triu_indices(len(y), 1)
    return float(np.median((y[j] - y[i]) / (j - i)))


@dataclass
class PostfireVerdict:
    depth_cm: int
    status: str               # "acuan belum ada", "commissioning", "mendingin", "berhenti mendingin", "naik", "kembali ke latar"
    level: Level
    delta_c: float | None     # selisih terakhir terhadap node kontrol
    expect_c: float | None    # selisih menurut kurva pendinginan
    tau_days: float | None
    start_class: str | None   # "mendingin", "stagnan", "menghangat" saat commissioning
    sentence: str
    flags: list[str] = field(default_factory=list)
    delta_series: list[float] = field(default_factory=list)
    expect_series: list[float] = field(default_factory=list)
    days_below: int = 0
    clear_eta_day: float | None = None


def postfire_level(depth_cm: int, hot: list[float], ref: list[float] | None) -> PostfireVerdict:
    """hot, ref: suhu per jam node blok terbakar dan node kontrol pada kedalaman sama, sejak node dipasang."""
    if not ref:
        return PostfireVerdict(depth_cm, "acuan belum ada", Level.NORMAL, None, None, None, None,
                               "Acuan latar belum ada: pasang node kontrol di sampah yang tidak terbakar.")
    n = min(len(hot), len(ref))
    d = daily_median([a - b for a, b in zip(hot[:n], ref[:n])])
    s0, s1 = SETTLE_H // 24, (SETTLE_H + BASELINE_MIN_H) // 24
    if len(d) <= s1:
        return PostfireVerdict(depth_cm, "commissioning", Level.NORMAL, float(d[-1]) if len(d) else None, None, None,
                               None, f"Commissioning pasca-kebakaran: hari {len(d)} dari {s1}.", delta_series=list(d))
    learn = d[s0:s1]
    slope0 = _ts_daily(learn)
    level0 = float(np.nanmedian(learn))
    if slope0 is not None and slope0 < POSTFIRE_COOLING_SLOPE and level0 > 0:
        tau = float(np.clip(-level0 / slope0, *POSTFIRE_TAU_RANGE))
        start = "mendingin"
    else:
        tau = None
        start = "menghangat" if slope0 is not None and slope0 > -POSTFIRE_COOLING_SLOPE else "stagnan"
    anchor = float(d[s1 - 1])
    days = np.arange(len(d))
    expect = np.full(len(d), np.nan)
    expect[s1 - 1:] = anchor * np.exp(-(days[s1 - 1:] - (s1 - 1)) / tau) if tau else anchor
    resid = d - expect
    today = len(d) - 1
    r7 = _ts_daily(resid[max(s1, today - 6): today + 1]) if today >= s1 + 6 else None
    s14 = _ts_daily(d[max(s0, today - POSTFIRE_STALL_D + 1): today + 1])
    rise_lim = POSTFIRE_RISE_SHALLOW if depth_cm < SHALLOW_MAX_DEPTH_CM else POSTFIRE_RISE_DEEP

    flags = []
    rise = r7 is not None and r7 > rise_lim
    above = resid[today] > POSTFIRE_DELTA_C
    stall = d[today] > POSTFIRE_DELTA_C and s14 is not None and s14 > POSTFIRE_STALL_SLOPE and today - s0 >= POSTFIRE_STALL_D - 1
    if rise:
        flags.append(f"naik melawan kurva pendinginan {fmt(r7, 2, True)} C/hari")
    if above:
        flags.append(f"{fmt(resid[today], 1, True)} C di atas kurva pendinginan")
    if stall:
        flags.append(f"pendinginan berhenti: selisih {fmt(d[today])} C, kemiringan 14 hari {fmt(s14, 2, True)} C/hari")
    level = Level.SIAGA if stall and (rise or above) else (Level.WASPADA if flags else Level.NORMAL)

    below = 0
    for v in d[::-1]:
        if v < POSTFIRE_DELTA_C:
            below += 1
        else:
            break
    eta = None
    if tau and d[today] > POSTFIRE_DELTA_C and anchor > POSTFIRE_DELTA_C:
        eta = (s1 - 1) + tau * np.log(anchor / POSTFIRE_DELTA_C)

    if rise or above:
        status, sentence = "naik", f"Naik melawan kurva pendinginan. Selisih dengan kontrol {fmt(d[today])} C."
    elif stall:
        status, sentence = "berhenti mendingin", (f"Pendinginan berhenti: selisih {fmt(d[today])} C bertahan "
                                                   f"{POSTFIRE_STALL_D} hari, kemungkinan masih ada bara.")
    elif below >= POSTFIRE_CLEAR_D:
        status, sentence = "kembali ke latar", (f"Kembali ke suhu latar selama {below} hari; pantauan pasca-kebakaran "
                                                f"berlanjut {POSTFIRE_WATCH_D} hari.")
    elif d[today] < POSTFIRE_DELTA_C:
        status, sentence = "mendingin", (f"Selisih {fmt(d[today])} C, di bawah 10 C selama {below} hari "
                                         f"(butuh {POSTFIRE_CLEAR_D} hari berturut-turut).")
    else:
        slope_now = _ts_daily(d[max(s0, today - 6): today + 1])
        eta_txt = f"; perkiraan di bawah 10 C sekitar hari ke-{eta:.0f}" if eta else ""
        status, sentence = "mendingin", (f"Mendingin {fmt(abs(slope_now or 0), 2)} C/hari, selisih dengan kontrol "
                                         f"{fmt(d[today])} C{eta_txt}.")
    return PostfireVerdict(depth_cm, status, level, float(d[today]), float(expect[today]), tau, start, sentence, flags,
                           [float(x) for x in d], [float(x) for x in expect], below, eta)


def gas_flags(series: dict[str, list[float]]) -> list[str]:
    """Penanda tren gas. Nilai mentah sensor MQ tidak dikonversi ke ppm, jadi hanya rasio yang dipakai."""
    flags = []
    for gas, values in series.items():
        if len(values) < MIN_GAS_SAMPLES:
            continue
        base = median(values[:-1])
        if base > 0 and values[-1] / base > GAS_TREND_RATIO:
            flags.append(f"{gas} naik {values[-1] / base:.1f}x dari median riwayat")
    return flags


def assess_block(block: str, probes: dict[int, list[float]], gases: dict[str, list[float]] | None = None,
                 mode: str = "normal", ref_probes: dict[int, list[float]] | None = None) -> BlockVerdict:
    """mode "pasca_kebakaran": aturan absolut tetap, aturan baseline sendiri diganti perbandingan dengan node kontrol."""
    postfire_mode = mode == "pasca_kebakaran"
    usable = {d: h for d, h in probes.items() if d >= MIN_RULE_DEPTH_CM and clean(h)}
    verdicts = [probe_level(d, h, use_baseline=not postfire_mode) for d, h in sorted(usable.items())]
    level = max((v.level for v in verdicts), default=Level.NORMAL)
    reasons = [f"probe {v.depth_cm} cm: {r}" for v in verdicts for r in v.reasons]
    pf: list[PostfireVerdict] = []
    if postfire_mode:
        for d, h in sorted(usable.items()):
            ref = (ref_probes or {}).get(d)
            pf.append(postfire_level(d, h, ref if ref and clean(ref) else None))
        level = max([level] + [v.level for v in pf])
        reasons += [f"probe {v.depth_cm} cm (pasca-kebakaran): {f}" for v in pf for f in v.flags]
    flags = gas_flags(gases or {})
    if flags and level < Level.WASPADA:
        level = Level.WASPADA
        reasons.append("gas naik tanpa kenaikan suhu: penanda tren saja, perlu cek lapangan")
    reasons += [f"gas: {f}" for f in flags]
    return BlockVerdict(block, Level(level), verdicts, flags, reasons, mode, pf)
