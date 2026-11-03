"""Pesan Telegram BARA: peringatan per blok, dan ringkasan di awal shift.

Env: TELEGRAM_BOT_TOKEN (dari @BotFather) dan TELEGRAM_CHAT_ID. Tanpa keduanya skrip berjalan dry-run
dan hanya mencetak pesan.

Run:
  .venv/bin/python bot/telegram_alert.py [csv]           peringatan blok WASPADA ke atas
  .venv/bin/python bot/telegram_alert.py --shift [csv]   ringkasan shift (satu arah; balasan petugas setelah 8 Nov)

Ringkasan shift mengikuti notulensi tim: inspeksi manual dalam enam shift. Jam shift di data/shifts.json; tanpa file itu
dipakai enam shift @ 4 jam mulai 00.00, yang masih ASUMSI karena arti "enam shift" belum dikonfirmasi DLH.
Pemeriksaan kamera termal dijadwalkan pada putaran sebelum matahari terbit (EA SC010066 4.3.1.1; Fjelsted 2019;
Tanda 2020: kontras permukaan kecil dan mudah tertutup panas matahari).
"""
import json
import os
import sys
from datetime import datetime, time, timedelta
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from bara import nodes as node_cfg  # noqa: E402
from bara.assess import ai_effect, assess_readings, is_simulated  # noqa: E402
from bara.risk import ACTIONS, Level  # noqa: E402

SHIFTS = ROOT / "data" / "shifts.json"
DEFAULT_SHIFTS = [{"name": f"Shift {i + 1}", "start": f"{4 * i:02d}:00", "hours": 4} for i in range(6)]
PREDAWN = (time(4, 0), time(6, 0))
BULAN = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]


def tgl(t: datetime) -> str:
    return f"{t.day} {BULAN[t.month - 1]} {t:%H.%M}"
STATUS_TEXT = {"naik": "naik melawan pendinginan", "berhenti mendingin": "pendinginan berhenti",
               "mendingin": "mendingin", "kembali ke latar": "kembali ke suhu latar",
               "commissioning": "commissioning", "acuan belum ada": "acuan kontrol belum ada"}
SAFETY = ("Keselamatan: bawa detektor CO pribadi. Injeksi air yang sedikit atau terputus-putus pada bara dapat membentuk "
          "gas air (hidrogen dan CO) yang beracun dan mudah meledak; jauhkan api dan mesin dari titik injeksi (EA SC010066).")


def send(text: str) -> None:
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        print("(dry-run)\n" + text + "\n")
        return
    r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", data={"chat_id": chat, "text": text}, timeout=20)
    r.raise_for_status()


def key_postfire(v):
    deep = [p for p in v.postfire if p.depth_cm >= 60]
    return max(deep, key=lambda p: (p.level, p.delta_c or 0)) if deep else None


def alert_message(v, simulated: bool) -> str:
    head = f"[BARA] {v.level.name} di blok {v.block}"
    if simulated:
        head = "[SIMULASI] " + head
    lines = [head]
    pf = key_postfire(v)
    if pf:
        lines.append(f"Blok bekas terbakar: {pf.sentence}")
    lines += [f"Tindakan: {v.action}", "Alasan:"] + [f"- {r}" for r in v.reasons[:5]]
    if v.level >= Level.SIAGA:
        lines.append(SAFETY)
    return "\n".join(lines)


def load_shifts() -> list[dict]:
    return json.loads(SHIFTS.read_text()) if SHIFTS.exists() else DEFAULT_SHIFTS


def current_shift(now: datetime, shifts: list[dict]) -> tuple[dict, datetime, datetime]:
    for s in shifts:
        h, m = map(int, s["start"].split(":"))
        start = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if start > now:
            start -= timedelta(days=1)
        end = start + timedelta(hours=s["hours"])
        if start <= now < end:
            return s, start, end
    s = shifts[0]
    return s, now, now + timedelta(hours=s["hours"])


def covers_predawn(start: datetime, end: datetime) -> bool:
    t = start
    while t < end:
        if PREDAWN[0] <= t.time() < PREDAWN[1]:
            return True
        t += timedelta(minutes=30)
    return False


def shift_briefing(verdicts, now: datetime, simulated: bool) -> str:
    shift, start, end = current_shift(now, load_shifts())
    order = {"naik": 0, "berhenti mendingin": 1, "mendingin": 2, "commissioning": 3}

    def sort_key(v):
        pf = key_postfire(v)
        return (-int(v.level), order.get(pf.status, 9) if pf else 9, v.block)

    head = f"[BARA] Ringkasan {shift['name']}, {tgl(start)} sampai {end:%H.%M}"
    lines = [("[SIMULASI] " if simulated else "") + head, ""]
    for v in sorted(verdicts, key=sort_key):
        pf = key_postfire(v)
        status = f"; bekas terbakar, {STATUS_TEXT.get(pf.status, pf.status)}" if pf else ""
        lines.append(f"{v.block}: {v.level.name}{status}")
        if v.level >= Level.WASPADA:
            lines.append(f"  {ACTIONS[v.level]}")
    lines.append("")
    if covers_predawn(start, end):
        lines.append("Kamera termal: lakukan putaran kamera di shift ini sebelum matahari terbit, mulai dari blok teratas. "
                     "Pindai titik probe dan lingkaran 10 m di sekitarnya.")
    else:
        lines.append("Kamera termal: dijadwalkan di shift yang mencakup jam sebelum matahari terbit; siang hari panas "
                     "matahari menutupi panas dari dalam timbunan.")
    if any(v.level >= Level.SIAGA for v in verdicts):
        lines.append(SAFETY)
    return "\n".join(lines)


def apply_ai(verdicts, df: pd.DataFrame, path: Path) -> None:
    """Samakan dengan dashboard: deteksi AI dengan skor >= 20 menaikkan blok normal ke WASPADA."""
    pre = ROOT / "data" / "processed" / "thermal_scan.csv"
    if path.name != "sim_readings.csv" or not pre.exists():
        return  # data lapangan: lapisan AI dihitung oleh API, bot hanya memakai lapisan aturan
    scan = pd.read_csv(pre)
    cfg = node_cfg.load(is_simulated(df))
    for v in verdicts:
        node = v.block.split("(")[-1].rstrip(")")
        s = scan[scan["node"] == node]
        if s.empty:
            continue
        r = s.iloc[-1]
        if ai_effect(r, node_cfg.role(cfg, node)["mode"]) == "naikkan" and v.level < Level.WASPADA:
            v.level = Level.WASPADA
            v.reasons.insert(0, f"model termal: sumber panas di sekitar {r['z_m']:.2f} m, skor {r['score']:.0f}".replace(".", ","))


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    path = Path(args[0]) if args else ROOT / "data" / "processed" / "sim_readings.csv"
    df = pd.read_csv(path)
    simulated = is_simulated(df)
    verdicts = assess_readings(df)
    apply_ai(verdicts, df, path)
    if "--shift" in sys.argv:
        now = pd.to_datetime(df["ts"]).max().to_pydatetime() if simulated else datetime.now().astimezone()
        send(shift_briefing(verdicts, now, simulated))
        return
    alerts = [v for v in verdicts if v.level >= Level.WASPADA]
    for v in sorted(alerts, key=lambda v: -v.level):
        send(alert_message(v, simulated))
    print(f"{len(alerts)} peringatan dari {path.name}")


if __name__ == "__main__":
    main()
