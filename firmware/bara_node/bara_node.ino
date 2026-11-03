// BARA node: 5 probe DS18B20 di timbunan (10, 30, 60, 100, 150 cm), DHT22 untuk udara, sensor gas MQ (analog),
// opsional satu thermocouple K-type (MAX31855) di 100 cm untuk rentang suhu tinggi.
//
// Catatan desain (brief DRA 2026-10-30):
// - Tiap probe di bus OneWire sendiri. Di lapangan tiap bus perlu pull-up 4,7 kOhm ke 3,3 V dan probe diberi daya
//   dari VDD. Jangan pakai parasite power: reset saat daya turun membuat sensor membaca +85 C.
// - Bacaan tepat 85,00 C dibaca ulang sekali. Jika tetap 85,00 dan bacaan baik sebelumnya di bawah 70 C, dikirim null.
// - Probe 10 cm dipakai server untuk memperkirakan difusivitas sampah dari gelombang suhu harian.
// - Pemanas MQ memakai lebih dari 99% energi node, jadi dinyalakan berkala lewat MOSFET di MQ_HEATER_PIN.
//   Siklus demo: pemanas menyala MQ_WARM_MS sebelum dibaca. Ini hanya untuk tren, bukan ppm.
// - DS18B20 akurat +-0,5 C sampai 85 C dan berhenti di 125 C. Untuk blok bekas terbakar aktifkan USE_MAX31855.
//
// Keluaran: satu baris JSON per siklus ke Serial, dan HTTP POST ke INGEST_URL jika WiFi tersambung.
// Wokwi: SSID "Wokwi-GUEST" tanpa password. Simulator Wokwi tidak bisa menjangkau localhost laptop,
// jadi INGEST_URL harus alamat publik (mis. tunnel). Tanpa itu, cukup baca JSON di Serial Monitor.

#include <WiFi.h>
#include <HTTPClient.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <DHTesp.h>
// #define USE_MAX31855
#ifdef USE_MAX31855
#include <Adafruit_MAX31855.h>
#endif

#define NODE_ID   "N1"
#define BLOCK_ID  "A"
const char* WIFI_SSID = "Wokwi-GUEST";
const char* WIFI_PASS = "";
const int WIFI_CHANNEL = 6;          // Wokwi-GUEST ada di kanal 6; di lapangan isi 0 (cari kanal otomatis)
const char* INGEST_URL = "";          // contoh: "https://xxxx.trycloudflare.com/ingest"
const uint32_t PERIOD_MS = 10000;     // demo: 10 detik. Lapangan: 15 menit (900000)

const int N_PROBES = 5;
const int PROBE_PINS[N_PROBES]   = {4, 16, 17, 18, 19};
const int PROBE_DEPTHS[N_PROBES] = {10, 30, 60, 100, 150};   // cm
const int DHT_PIN = 15;
const int MQ_PIN  = 34;                // ADC1, aman dipakai bersama WiFi
const int MQ_HEATER_PIN = 25;          // gerbang MOSFET pemanas MQ
const uint32_t MQ_WARM_MS = 5000;      // demo. Lapangan: sesuai datasheet sensor yang dipakai
const int MQ_EVERY_N = 4;              // gas dibaca tiap 4 siklus
const float RESET_C = 85.0;

OneWire wires[N_PROBES] = {OneWire(PROBE_PINS[0]), OneWire(PROBE_PINS[1]), OneWire(PROBE_PINS[2]),
                           OneWire(PROBE_PINS[3]), OneWire(PROBE_PINS[4])};
DallasTemperature probes[N_PROBES] = {DallasTemperature(&wires[0]), DallasTemperature(&wires[1]),
                                      DallasTemperature(&wires[2]), DallasTemperature(&wires[3]),
                                      DallasTemperature(&wires[4])};
float lastGood[N_PROBES] = {NAN, NAN, NAN, NAN, NAN};
DHTesp dht;
#ifdef USE_MAX31855
Adafruit_MAX31855 tc(14, 5, 12);       // CLK, CS, DO
#endif
uint32_t seq = 0;

void connectWifi() {
  if (strlen(INGEST_URL) == 0) {        // tanpa tujuan pengiriman, data cukup lewat Serial
    Serial.println("Mode lokal: INGEST_URL kosong, data dikirim lewat Serial");
    return;
  }
  WiFi.begin(WIFI_SSID, WIFI_PASS, WIFI_CHANNEL);
  for (int i = 0; i < 80 && WiFi.status() != WL_CONNECTED; i++) delay(250);   // tunggu sampai 20 detik
  Serial.println(WiFi.status() == WL_CONNECTED ? "WiFi tersambung" : "WiFi gagal, lanjut tanpa jaringan");
}

float readProbe(int i) {
  probes[i].requestTemperatures();
  float t = probes[i].getTempCByIndex(0);
  if (t == DEVICE_DISCONNECTED_C) return NAN;
  if (t == RESET_C) {                                   // kemungkinan nilai reset, baca ulang sekali
    delay(800);
    probes[i].requestTemperatures();
    t = probes[i].getTempCByIndex(0);
    if (t == DEVICE_DISCONNECTED_C) return NAN;
    if (t == RESET_C && !(lastGood[i] >= 70.0)) return NAN;
  }
  lastGood[i] = t;
  return t;
}

String num(float v, int digits) { return isnan(v) ? String("null") : String(v, digits); }

String reading() {
  String j = "{\"node\":\"" NODE_ID "\",\"block\":\"" BLOCK_ID "\",\"seq\":" + String(seq);
  for (int i = 0; i < N_PROBES; i++) {
    j += ",\"t_" + String(PROBE_DEPTHS[i]) + "\":" + num(readProbe(i), 2);
  }
#ifdef USE_MAX31855
  j += ",\"tc_100\":" + num(tc.readCelsius(), 1);
#endif
  TempAndHumidity a = dht.getTempAndHumidity();
  j += ",\"t_air\":" + num(a.temperature, 2);
  j += ",\"rh\":" + num(a.humidity, 1);
  if (seq % MQ_EVERY_N == 0) {
    digitalWrite(MQ_HEATER_PIN, HIGH);
    delay(MQ_WARM_MS);
    j += ",\"mq_raw\":" + String(analogRead(MQ_PIN));
    digitalWrite(MQ_HEATER_PIN, LOW);
  }
  j += "}";
  seq++;
  return j;
}

void post(const String& body) {
  if (strlen(INGEST_URL) == 0 || WiFi.status() != WL_CONNECTED) return;
  HTTPClient http;
  http.begin(INGEST_URL);
  http.addHeader("Content-Type", "application/json");
  int code = http.POST(body);
  Serial.printf("POST %d\n", code);
  http.end();
}

void setup() {
  Serial.begin(115200);
  for (auto& p : probes) p.begin();
  dht.setup(DHT_PIN, DHTesp::DHT22);
  pinMode(MQ_HEATER_PIN, OUTPUT);
  digitalWrite(MQ_HEATER_PIN, LOW);
  analogReadResolution(12);
#ifdef USE_MAX31855
  tc.begin();
#endif
  connectWifi();
}

void loop() {
  String body = reading();
  Serial.println(body);
  post(body);
  delay(PERIOD_MS);
}
