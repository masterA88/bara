# Perbandingan waktu deteksi: lapisan AI dan lapisan aturan

Data: `sim_readings.csv`. Langkah 3 jam. Waktu dalam WIB.

| Node | Mode | Kebenaran (simulasi) | AI skor > 1 | AI skor >= 20 (menaikkan level) | Perkiraan AI (kedalaman, mulai) | Aturan pertama WASPADA | Aturan pertama SIAGA |
|---|---|---|---|---|---|---|---|
| N1 (A) | kontrol | tanpa sumber baru | tidak dalam rentang data | tidak dalam rentang data | - | tidak dalam rentang data | tidak dalam rentang data |
| N2 (C) | normal | sumber 40 W/m3 di 1.00 m, mulai 19 Oct 00:00 | 20 Oct 11:00 | 25 Oct 23:00 | 1.10 m, 18 Oct 21:00 | 22 Oct 03:00 | tidak dalam rentang data |
| N3 (D1) | pasca_kebakaran | sumber 150 W/m3 di 0.80 m, mulai 21 Oct 00:00 | 26 Oct 11:00 | tidak dipakai (mode pasca-kebakaran) | 0.80 m, 22 Oct 18:00 | 24 Oct 00:00 | 26 Oct 00:00 |
| N4 (B) | pasca_kebakaran | tanpa sumber baru | tidak dalam rentang data | tidak dipakai (mode pasca-kebakaran) | - | 18 Oct 00:00 | tidak dalam rentang data |

Ambang AI dikalibrasi pada data commissioning tiap node (3x statistik maksimum tanpa sumber), dengan ambang node kontrol sebagai batas bawah. Lapisan AI hanya menaikkan level jika skor >= 20; di blok pasca-kebakaran AI hanya informasi. Data simulasi memakai model fisika yang sama dengan detektor, ditambah pemanasan matahari, hujan, derau, dan drift yang tidak dimodelkan detektor. Hasil ini satu simulasi 30 hari dan batas atas, bukan klaim kinerja lapangan. Uji DRA 60 hari menemukan alarm palsu AI tanpa batas skor 20.
