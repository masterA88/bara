"""Penerima data node: POST JSON ke /ingest, ditambah ke data/processed/readings.csv.

Hanya pustaka standar Python, untuk demo dan uji node. Belum ada autentikasi, jadi jangan dibuka ke internet
tanpa token (tambahkan sebelum dipasang di TPA).

Run: .venv/bin/python ingest/server.py [port]
Uji: curl -X POST localhost:8765/ingest -d '{"node":"N1","block":"B","t_30":41.2,"t_air":30.1,"mq_raw":410}'
"""
import csv
import json
import sys
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "data" / "processed" / "readings.csv"
FIELDS = ["ts", "node", "block", "seq", "t_10", "t_30", "t_60", "t_100", "t_150", "tc_100", "t_air", "rh", "mq_raw", "simulated"]
WIB = timezone(timedelta(hours=7))


def append(rec: dict) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    new = not OUT.exists()
    rec = {k: rec.get(k) for k in FIELDS}
    rec["ts"] = rec["ts"] or datetime.now(WIB).isoformat(timespec="seconds")
    rec["simulated"] = rec["simulated"] or False
    with OUT.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader()
        w.writerow(rec)


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/ingest":
            self.send_error(404)
            return
        try:
            rec = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            if not rec.get("node") or not rec.get("block"):
                raise ValueError("node dan block wajib")
            append(rec)
        except (ValueError, json.JSONDecodeError) as e:
            self.send_error(400, str(e))
            return
        self.send_response(204)
        self.end_headers()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    print(f"BARA ingest di :{port}/ingest -> {OUT}")
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()
