"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Borehole from "./Borehole";
import { DroughtChart, PostfireChart, ScoreChart, TempChart } from "./Charts";
import type { BlockStatus, Comparison, Series, Site, Status, Weather } from "@/lib/api";
import { LEVEL_LABEL, MODE_LABEL, POSTFIRE_STATUS, fmt1, fmt2, fmtDate, fmtTime, keyPostfire } from "@/lib/api";
import { fieldAvailable as checkField, loadComparison, loadSeries, loadSite, loadStatus, loadWeather } from "@/lib/data";

const SiteMap = dynamic(() => import("./SiteMap"), { ssr: false, loading: () => <div className="map" /> });

const STEP_H = 3;
const HOUR = 3600_000;

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

export default function Dashboard() {
  const [source, setSource] = useState<"sim" | "field">("sim");
  const [fieldAvailable, setFieldAvailable] = useState(false);
  const [site, setSite] = useState<Site | null>(null);
  const [weather, setWeather] = useState<Weather | null>(null);
  const [comparison, setComparison] = useState<Comparison | null>(null);
  const [status, setStatus] = useState<Status | null>(null);
  const [series, setSeries] = useState<Series | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [range, setRange] = useState<[number, number] | null>(null);
  const [offset, setOffset] = useState<number | null>(null); // jam sejak awal data; null = terbaru
  const [node, setNode] = useState<string | null>(null);
  const [playing, setPlaying] = useState(false);

  useEffect(() => {
    loadSite().then(setSite).catch((e) => setError(e.message));
    loadWeather().then(setWeather).catch(() => {});
    loadComparison().then(setComparison).catch(() => {});
    checkField().then(setFieldAvailable);
  }, []);

  const until = useMemo(() => {
    if (!range || offset == null) return null;
    return new Date(range[0] + offset * HOUR).toISOString();
  }, [range, offset]);
  const untilDebounced = useDebounced(until, playing ? 0 : 120);

  useEffect(() => {
    const ctl = new AbortController();
    loadStatus(source, untilDebounced, ctl.signal)
      .then((s) => {
        setStatus(s);
        setError(null);
        const r: [number, number] = [Date.parse(s.range.start), Date.parse(s.range.end)];
        setRange((old) => (old && old[0] === r[0] && old[1] === r[1] ? old : r));
        setNode((n) => n ?? s.blocks[0]?.node ?? null);
      })
      .catch((e) => e.name !== "AbortError" && setError(e.message));
    return () => ctl.abort();
  }, [source, untilDebounced]);

  useEffect(() => {
    if (!node) return;
    const ctl = new AbortController();
    loadSeries(node, source, untilDebounced, ctl.signal)
      .then(setSeries)
      .catch((e) => e.name !== "AbortError" && setError(e.message));
    return () => ctl.abort();
  }, [node, source, untilDebounced]);

  const maxOffset = range ? Math.floor((range[1] - range[0]) / HOUR) : 0;
  const current = offset ?? maxOffset;

  // Putar ulang: maju 3 jam tiap langkah, berhenti di akhir data.
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  useEffect(() => {
    if (!playing) return;
    timer.current = setInterval(() => {
      setOffset((o) => {
        const next = (o ?? 0) + STEP_H;
        if (next >= maxOffset) {
          setPlaying(false);
          return null;
        }
        return next;
      });
    }, 450);
    return () => {
      if (timer.current) clearInterval(timer.current);
    };
  }, [playing, maxOffset]);

  const togglePlay = useCallback(() => {
    if (!playing && (offset == null || offset >= maxOffset)) setOffset(3 * 24 + 14 * 24);
    setPlaying((p) => !p);
  }, [playing, offset, maxOffset]);

  const selected: BlockStatus | undefined = status?.blocks.find((b) => b.node === node);
  const aiFirst = series?.ai.find((p) => p.detected)?.ts ?? null;

  return (
    <div className="shell">
      <header className="top">
        <div className="brand">
          <h1>BARA</h1>
          <p>Peringatan dini kebakaran TPA Putri Cempo, Surakarta</p>
        </div>
        {status?.simulated ? <span className="badge-sim">Data simulasi, bukan pengukuran di TPA</span> : <span />}
        <div className="source-switch" role="group" aria-label="Sumber data">
          <button aria-pressed={source === "sim"} onClick={() => { setSource("sim"); setOffset(null); setRange(null); setNode(null); }}>Simulasi</button>
          <button aria-pressed={source === "field"} disabled={!fieldAvailable}
                  title={fieldAvailable ? undefined : "Belum ada data dari node lapangan"}
                  onClick={() => { setSource("field"); setOffset(null); setRange(null); setNode(null); }}>Node lapangan</button>
        </div>
      </header>

      {error && <p className="error">Data tidak bisa dimuat: {error}. Jika memakai API lokal, pastikan API berjalan di port 8000.</p>}

      {range && (
        <section className="timeline" aria-label="Putar ulang data">
          <button className="play" onClick={togglePlay} aria-label={playing ? "Jeda putar ulang" : "Putar ulang dari akhir commissioning"}>
            {playing ? (
              <svg viewBox="0 0 14 14"><rect x="2" y="1" width="3.5" height="12" fill="currentColor" /><rect x="8.5" y="1" width="3.5" height="12" fill="currentColor" /></svg>
            ) : (
              <svg viewBox="0 0 14 14"><path d="M3 1 L13 7 L3 13 Z" fill="currentColor" /></svg>
            )}
          </button>
          <input type="range" min={0} max={maxOffset} step={1} value={current} aria-label="Waktu"
                 onChange={(e) => { setPlaying(false); const v = Number(e.target.value); setOffset(v >= maxOffset ? null : v); }} />
          <span className="now">{fmtTime(status?.until)}</span>
          <div className="ticks"><span>{fmtTime(new Date(range[0]).toISOString())}</span><span>{fmtTime(new Date(range[1]).toISOString())}</span></div>
        </section>
      )}

      {!status && !error && <p className="loading">Memuat status blok...</p>}

      {status && (
        <div className="main">
          <nav className="rail" aria-label="Daftar blok">
            {status.blocks.map((b) => (
              <button key={b.node} className={`block-btn lv-${b.level}`} aria-pressed={b.node === node} onClick={() => setNode(b.node)}>
                <span className="block-code">{b.block}</span>
                <span className="block-level">{LEVEL_LABEL[b.level]}</span>
                <span className="block-meta">
                  Node {b.node}{MODE_LABEL[b.mode] ? <>, <span className="mode-tag">{MODE_LABEL[b.mode]}</span></> : null}.{" "}
                  {b.mode === "pasca_kebakaran" ? POSTFIRE_STATUS[keyPostfire(b.postfire)?.status ?? "commissioning"]
                    : b.ai?.detected ? <span className="ai-on">AI: panas di sekitar {fmt2(b.ai.z_m)} m</span>
                    : b.ai ? "AI: normal" : "AI: commissioning"}
                </span>
              </button>
            ))}
            {weather && (
              <section className="panel" aria-label="Cuaca">
                <h2>Cuaca di TPA</h2>
                <p className="sub">Per {fmtDate(weather.latest.date)}, dari data reanalisis Open-Meteo. Konteks seluruh TPA, bukan pemicu per blok.</p>
                <div className="weather-now">
                  <div><div className="v">{weather.latest.dc}</div><div className="c">Drought Code</div><div className="m">{weather.latest.dc_class}, persentil {Math.round(weather.latest.dc_pct_dry_season * 100)} musim kemarau</div></div>
                  <div><div className="v">{fmt1(weather.latest.ffmc)}</div><div className="c">FFMC</div><div className="m">{weather.latest.ffmc_class}</div></div>
                </div>
              </section>
            )}
          </nav>

          {site && <SiteMap site={site} blocks={status.blocks} selected={node} onSelect={setNode} />}
          {selected && (
            <section className={`panel verdict lv-${selected.level}`} aria-live="polite">
              <div className="verdict-head">
                <span className="code">{selected.block}</span>
                <span className="lvl">{LEVEL_LABEL[selected.level]}</span>
              </div>
              <p className="action">{selected.action}</p>
              {selected.mode === "pasca_kebakaran" && (
                <p className="postfire-note">
                  Blok bekas terbakar{selected.since ? ` sejak ${fmtDate(selected.since)}` : ""}, dibandingkan dengan node
                  kontrol {selected.reference ?? "(belum ada)"}. {keyPostfire(selected.postfire)?.sentence}
                </p>
              )}
              <div className="layers">
                <div className="layer">
                  <h3>{selected.mode === "pasca_kebakaran" ? "Aturan EA, Permen PU, dan kontrol" : "Aturan EA dan Permen PU"}</h3>
                  <div className="big">{LEVEL_LABEL[selected.rule_level]}</div>
                  <div className="foot">
                    {selected.mode === "pasca_kebakaran"
                      ? `Selisih dengan kontrol di ${keyPostfire(selected.postfire)?.depth_cm ?? "-"} cm: ${fmt1(keyPostfire(selected.postfire)?.delta_c)} °C`
                      : `Baseline ${selected.commissioning}`}
                  </div>
                </div>
                <div className="layer ai">
                  <h3>Model termal (AI)</h3>
                  <div className="big">{selected.ai ? (selected.ai.detected ? `Panas di ${fmt2(selected.ai.z_m)} m` : "Normal") : "Belajar"}</div>
                  <div className="foot">
                    {!selected.ai ? "Menunggu 14 hari commissioning"
                      : selected.ai.effect === "naikkan" ? `Skor ${fmt2(selected.ai.score)}, menaikkan level (skor ${status.ai_level_score} ke atas)`
                      : selected.ai.effect === "perhatian" ? (selected.mode === "pasca_kebakaran"
                          ? `Skor ${fmt2(selected.ai.score)}; di blok bekas terbakar hanya informasi`
                          : `Skor ${fmt2(selected.ai.score)}; perhatian saja, level naik di skor ${status.ai_level_score}`)
                      : `Skor ${fmt2(selected.ai.score)}, di bawah ambang 1`}
                  </div>
                </div>
              </div>
              {selected.reasons.length > 0 ? (
                <>
                  <ul className="reasons">{selected.reasons.slice(0, 4).map((r) => <li key={r}>{r}</li>)}</ul>
                  {selected.reasons.length > 4 && (
                    <details className="more">
                      <summary>{selected.reasons.length - 4} alasan lain</summary>
                      <ul className="reasons">{selected.reasons.slice(4).map((r) => <li key={r}>{r}</li>)}</ul>
                    </details>
                  )}
                </>
              ) : (
                <p className="foot">Tidak ada aturan yang terpicu di blok ini.</p>
              )}
            </section>
          )}
        </div>
      )}

      {status && selected && series && (
        <section className="panel row-node" aria-label={`Detail node ${selected.node}`}>
          <div>
            <h2>Tali probe {selected.node}</h2>
            <p className="sub">Penampang 0 sampai 2 m di blok {selected.block}.</p>
            <Borehole block={selected} />
          </div>
          <div className="charts">
            <TempChart series={series} aiOnset={selected.ai?.detected ? selected.ai.onset : null} aiFirst={aiFirst} />
            {series.postfire ? <PostfireChart series={series} reference={selected.reference} />
              : <ScoreChart series={series} range={[status.range.start, status.until]} />}
          </div>
        </section>
      )}

      {status && (
        <div className="row-bottom">
          {comparison && status.simulated && (
            <section className="panel">
              <h2>Seberapa cepat tiap lapisan mendeteksi</h2>
              <p className="sub">Jam setelah sumber panas mulai menyala, pada satu simulasi 30 hari.</p>
              <table className="cmp">
                <thead><tr><th>Blok</th><th>Skenario</th><th>Aturan dan mode pasca-kebakaran</th><th>AI melihat</th><th>AI menaikkan level</th></tr></thead>
                <tbody>
                  {comparison.rows.map((r) => {
                    const none = r.truth ? "tidak terdeteksi" : "tanpa alarm";
                    return (
                      <tr key={r.node}>
                        <td>{r.block}</td>
                        <td>{r.truth ? `${r.mode === "pasca_kebakaran" ? "Bekas terbakar, menyala lagi" : "Pemanasan"} ${r.truth.q_w_m3} W/m³ di ${fmt2(r.truth.z_m)} m` : r.scenario ?? "Tanpa sumber"}</td>
                        <td>{r.rule_hours_after_onset != null ? `${r.rule_hours_after_onset} jam` : r.truth ? none : r.mode === "pasca_kebakaran" ? "pendinginan berhenti terdeteksi" : none}</td>
                        <td className="ai">{r.ai_hours_after_onset != null ? `${r.ai_hours_after_onset} jam, ${fmt2(r.ai_z_m)} m` : none}</td>
                        <td>{r.mode === "pasca_kebakaran" ? "tidak dipakai" : r.ai_lift_hours_after_onset != null ? `${r.ai_lift_hours_after_onset} jam` : none}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              <p className="foot" style={{ marginTop: 10 }}>{comparison.note}</p>
            </section>
          )}
          {weather && site && (
            <section className="panel">
              <h2>Kekeringan setahun terakhir</h2>
              <p className="sub">Drought Code harian di titik TPA. Garis merah menandai kebakaran September 2026.</p>
              <DroughtChart data={weather.series} fires={site.fires.map((f) => f.start)} />
            </section>
          )}
        </div>
      )}

      {status && (
        <p className="foot">
          Ambang suhu: Environment Agency (Inggris) SC010066, Tabel 23. Kelas Drought Code dan FFMC: BMKG.
          Model termal: konduksi panas 1D yang dikalibrasi pada data commissioning tiap node. Rincian di BIBLE.md.
        </p>
      )}
    </div>
  );
}
