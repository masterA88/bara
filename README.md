# BARA

Peringatan dini kebakaran TPA Putri Cempo dari probe suhu timbunan, sensor gas, dan cuaca.

Hilmi, https://master-hilmi.vercel.app/

## Video

[Video_Marketing_BARA.mp4](video/Video_Marketing_BARA.mp4): demo tanpa suara, sekitar 3 menit, dengan subtitle bahasa Indonesia. Semua angka dashboard di video berasal dari data simulasi.

Dashboard online: https://bara-putri-cempo.vercel.app

## Menyiapkan

```bash
cd bara
uv venv -p 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt
```

## Menjalankan tahap 0

```bash
.venv/bin/python data/fetch_weather.py          # cuaca jam 12 siang 2015 sampai sekarang
.venv/bin/python data/backtest_weather.py       # Drought Code dan FFMC, uji mundur pada 4 kebakaran
.venv/bin/python sim/simulate_nodes.py          # data node simulasi (model konduksi, 30 hari)
.venv/bin/python data/run_thermal.py            # lapisan AI, dan perbandingan waktu deteksi dengan aturan
.venv/bin/python bot/telegram_alert.py          # peringatan (dry-run tanpa token)
.venv/bin/python bot/telegram_alert.py --shift  # ringkasan awal shift (dry-run tanpa token)
.venv/bin/python -m pytest -q tests
```

Opsional:

```bash
FIRMS_MAP_KEY=... .venv/bin/python data/fetch_firms.py
TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=... .venv/bin/python bot/telegram_alert.py
.venv/bin/python ingest/server.py               # terima POST JSON di :8765/ingest
```

## Dashboard web

Dua proses, di dua terminal:

```bash
.venv/bin/uvicorn api.main:app --port 8000 --reload   # API, dokumentasi di http://localhost:8000/docs
cd web && npm install && npm run dev                   # dashboard di http://localhost:3000
```

Jika API berjalan di alamat lain, set `BARA_API_URL` sebelum `npm run dev`. Node mengirim data ke `POST /api/ingest`.

## Deploy dashboard (versi statis)

Versi online memakai data simulasi yang dihitung sebelumnya, tanpa server Python. Akun: Vercel pribadi `masterardian-7257` (aturan akun di `~/.claude/CLAUDE.md`).

```bash
.venv/bin/python api/export_static.py           # tulis web/public/data/*.json
# salin web/ ke folder tanpa .git dan tanpa node_modules, lalu dari folder itu:
vercel -Q ~/.vercel-masterardian --scope masterardian-gmailcoms-projects deploy --prod --yes --build-env NEXT_PUBLIC_BARA_STATIC=1
```

Alamat: https://bara-putri-cempo.vercel.app

## Peran node

Node di blok bekas terbakar memakai mode pasca-kebakaran dan butuh node kontrol di sampah yang tidak terbakar. Untuk data lapangan, tulis `data/nodes.json`, misalnya:

```json
{"N1": {"mode": "kontrol"}, "N3": {"mode": "pasca_kebakaran", "reference": "N1", "since": "2026-09-24"}}
```

Jam shift untuk ringkasan Telegram ada di `data/shifts.json` (daftar `{"name", "start", "hours"}`). Tanpa file itu dipakai enam shift @ 4 jam mulai 00.00.

## Node di Wokwi

Buat proyek ESP32 baru di https://wokwi.com, lalu tempel isi `firmware/bara_node/bara_node.ino` ke `sketch.ino`, `wokwi/diagram.json` ke `diagram.json`, dan `wokwi/libraries.txt` ke Library Manager. Ubah suhu probe dengan mengklik sensornya saat simulasi berjalan.

## Struktur

| Folder | Isi |
|---|---|
| `bara/` | Paket Python: lokasi, lapisan aturan (`risk.py`), lapisan AI (`thermal.py`), cuaca (`weather.py`) |
| `data/` | Skrip unduh dan uji mundur; `raw/` dan `processed/` berisi hasilnya |
| `sim/` | Generator data node simulasi |
| `firmware/`, `wokwi/` | Kode ESP32 dan rangkaian simulasi |
| `api/` | API FastAPI di atas mesin BARA, termasuk penerima data node |
| `ingest/` | Penerima data node lama (pustaka standar Python) |
| `web/` | Dashboard web (Next.js, MapLibre) |
| `bot/` | Peringatan Telegram |
| `tests/` | Tes mesin risiko |
| `video/` | Video pemasaran tanpa suara (subtitle, zoom, dan sorotan) |
