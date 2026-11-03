"""Data lokasi TPA Putri Cempo dan kejadian kebakaran yang tercatat.

Koordinat dan bounding box dari OpenStreetMap way 1221584229 (landuse=landfill), diambil 2026-10-30.
Tanggal kebakaran dari berita lokal (Metro TV, iNews, detikJateng).
"""
from dataclasses import dataclass
from datetime import date

LAT = -7.5360184
LON = 110.8561647
BBOX = {"south": -7.5383142, "north": -7.5334981, "west": 110.8538427, "east": 110.8585465}
AREA_HA = 17  # luas TPA menurut Katadata 2026-09-03


@dataclass(frozen=True)
class FireEvent:
    start: date
    end: date | None
    note: str
    source: str
    start_exact: bool = True


FIRES = [
    FireEvent(date(2019, 10, 9), None,
              "Posko kesehatan dibuka Rabu 9/10 karena asap; pemadaman sekitar satu minggu. Tanggal mulai tidak diketahui, "
              "9 Oktober adalah batas paling lambat.",
              "republika-pz3z90335-posko-kebakaran-2019.md; detik-d-6934735-kebakaran-2023.md", start_exact=False),
    FireEvent(date(2023, 9, 16), date(2023, 9, 23), "Kebakaran 16 sampai 23 September 2023, metana diduga pemicu.",
              "medcom-RkjMmLRb-padam-2023.md; detik-d-6934735-kebakaran-2023.md"),
    FireEvent(date(2026, 9, 2), date(2026, 9, 16), "Tanggap darurat 3 sampai 16 September 2026; Blok B, C, D.",
              "cnbcindonesia-20260903161722-lalap-217-hektare.md; kompas-20260904104119178-status-tanggap-darurat.md"),
    FireEvent(date(2026, 9, 24), None, "Terbakar lagi 24 September 2026 di Blok B, C, D1, D2.",
              "rctiplus-5480512-kembali-terbakar-24-sep.md"),
]

# Blok sementara. Nama B, C, D1, D2 dari berita (RCTI 5480512); posisinya ASUMSI pada grid bounding box OSM
# sampai DLH memberi peta blok resmi. Jangan dipakai sebagai lokasi lapangan.
# burned_2026: blok yang terbakar pada 2 atau 24 September 2026 menurut berita (Kompas 4 Sep; RCTI 5480512).
BLOCKS = {
    "A": {"lat": -7.53470, "lon": 110.85500, "assumed": True, "burned_2026": False},
    "B": {"lat": -7.53470, "lon": 110.85730, "assumed": True, "burned_2026": True},
    "C": {"lat": -7.53600, "lon": 110.85500, "assumed": True, "burned_2026": True},
    "D1": {"lat": -7.53600, "lon": 110.85730, "assumed": True, "burned_2026": True},
    "D2": {"lat": -7.53740, "lon": 110.85620, "assumed": True, "burned_2026": True},
}
