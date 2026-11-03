"""Lapisan cuaca BARA: Drought Code (DC) dan Fine Fuel Moisture Code (FFMC) dari sistem FWI Kanada.

Dipakai sebagai konteks tingkat TPA, bukan pemicu per blok. Indonesia (BMKG, FDRS) memakai DC sebagai indikator
potensi kebakaran membara dan FFMC untuk kemudahan penyalaan bahan permukaan. Kelas di bawah disalin dari halaman
BMKG (sources/fdrs/bmkg-cuaca-karhutla-dc.md dan -ffmc.md, ditangkap 2026-10-30). Karena kelas "sangat kering"
(DC > 350) berlaku pada sekitar 71% hari Juli sampai Oktober di lokasi ini, dashboard juga menampilkan persentil DC
terhadap hari Juli sampai Oktober di lokasi itu sendiri.

Indeks dihitung dengan xclim 0.62.0 (cffwis_indices) dari cuaca jam 12 siang Open-Meteo. Tidak ada makalah yang
memvalidasi FWI untuk TPA; alasannya keterpakaian dan kesamaan dengan indeks resmi BMKG (brief DRA 2026-10-30, bagian 4).
"""
from __future__ import annotations

import warnings

import pandas as pd

from .site import LAT

DC_CLASSES = [(140, "basah"), (260, "lembap"), (350, "kering"), (float("inf"), "sangat kering")]
FFMC_CLASSES = [(72, "sulit terbakar"), (77, "cukup sulit terbakar"), (82, "mudah terbakar"), (float("inf"), "sangat mudah terbakar")]
SPINUP_DAYS = 120
DRY_SEASON_MONTHS = (7, 8, 9, 10)


def classify(value: float, classes) -> str:
    return next(name for upper, name in classes if value <= upper)


def fwi_codes(noon: pd.DataFrame) -> pd.DataFrame:
    """noon: kolom date, t_noon, rh_noon, wind_noon (km/jam), rain_24h (mm). Tambah dc, ffmc, dmc, fwi."""
    import xarray as xr
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from xclim.indices.fire import cffwis_indices

    d = noon.sort_values("date").reset_index(drop=True).copy()
    t = xr.DataArray(pd.to_datetime(d["date"]).values, dims="time", name="time")

    def da(col, units):
        return xr.DataArray(d[col].values.astype(float), coords={"time": t}, dims="time", attrs={"units": units})

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        dc, dmc, ffmc, isi, bui, fwi = cffwis_indices(
            tas=da("t_noon", "degC"), pr=da("rain_24h", "mm/d"), sfcWind=da("wind_noon", "km/h"),
            hurs=da("rh_noon", "%"), lat=xr.DataArray(LAT, attrs={"units": "degrees_north"}), season_method=None)
    for name, arr in {"dc": dc, "dmc": dmc, "ffmc": ffmc, "fwi": fwi}.items():
        d[name] = arr.values
    d = d[d["date"] >= d["date"].min() + pd.Timedelta(days=SPINUP_DAYS)].reset_index(drop=True)
    season = d[d["date"].dt.month.isin(DRY_SEASON_MONTHS)]["dc"].sort_values().to_numpy()
    d["dc_pct_dry_season"] = d["dc"].apply(lambda v: (season < v).mean())
    d["dc_class"] = d["dc"].apply(lambda v: classify(v, DC_CLASSES))
    d["ffmc_class"] = d["ffmc"].apply(lambda v: classify(v, FFMC_CLASSES))
    return d
