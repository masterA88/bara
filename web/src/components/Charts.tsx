"use client";

import { scaleLinear, scaleSymlog, scaleTime } from "d3-scale";
import { area, line } from "d3-shape";
import { useMemo, useRef, useState, useEffect } from "react";
import type { Series } from "@/lib/api";
import { fmt2, fmtTime } from "@/lib/api";

const M = { top: 10, right: 16, bottom: 26, left: 40 };

function useWidth<T extends HTMLElement>(): [React.RefObject<T | null>, number] {
  const ref = useRef<T>(null);
  const [w, setW] = useState(700);
  useEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver(([e]) => setW(Math.max(320, e.contentRect.width)));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);
  return [ref, w];
}

const dayFmt = new Intl.DateTimeFormat("id-ID", { day: "numeric", month: "short", timeZone: "Asia/Jakarta" });

function TimeAxis({ x, h }: { x: ReturnType<typeof scaleTime>; h: number }) {
  return (
    <g className="axis" transform={`translate(0,${h - M.bottom})`}>
      {x.ticks(7).map((t) => (
        <g key={+t} transform={`translate(${x(t)},0)`}>
          <line y2={4} />
          <text y={17} textAnchor="middle">{dayFmt.format(t)}</text>
        </g>
      ))}
    </g>
  );
}

// Warna per kedalaman: dangkal pucat, dalam gelap, mengikuti warna tanah.
const DEPTH_COLORS: Record<number, string> = { 10: "#b9c3c0", 30: "#8fa39c", 60: "#a08766", 100: "#7a5a3a", 150: "#3f2e1f" };

export function TempChart({ series, aiOnset, aiFirst }: { series: Series; aiOnset: string | null; aiFirst: string | null }) {
  const [ref, w] = useWidth<HTMLDivElement>();
  const h = 250;
  const rows = series.temps;
  const { x, y, paths } = useMemo(() => {
    const ts = rows.map((r) => new Date(r.ts));
    const vals = rows.flatMap((r) => series.depths_cm.map((d) => r[`t_${d}`] as number | null)).filter((v): v is number => v != null);
    const x = scaleTime().domain([ts[0], ts[ts.length - 1]]).range([M.left, w - M.right]);
    const y = scaleLinear().domain([Math.floor(Math.min(...vals) - 1), Math.ceil(Math.max(...vals) + 1)]).nice().range([h - M.bottom, M.top]);
    const paths = series.depths_cm.map((d) => ({
      d,
      path: line<(typeof rows)[number]>()
        .defined((r) => r[`t_${d}`] != null)
        .x((r) => x(new Date(r.ts)))
        .y((r) => y(r[`t_${d}`] as number))(rows) ?? "",
    }));
    return { x, y, paths };
  }, [rows, series.depths_cm, w]);

  return (
    <div ref={ref}>
      <div className="chart-title">
        Suhu di dalam timbunan <span>°C per jam, tiap garis satu kedalaman</span>
      </div>
      <svg width={w} height={h} role="img" aria-label="Grafik suhu timbunan per kedalaman">
        <g className="axis">
          {y.ticks(5).map((t) => (
            <g key={t} transform={`translate(0,${y(t)})`}>
              <line x1={M.left} x2={w - M.right} stroke="var(--line)" strokeDasharray="2 4" />
              <text x={M.left - 8} y={4} textAnchor="end">{t}</text>
            </g>
          ))}
        </g>
        {aiOnset && (
          <g>
            <line x1={x(new Date(aiOnset))} x2={x(new Date(aiOnset))} y1={M.top} y2={h - M.bottom} stroke="var(--ai)" strokeDasharray="4 3" />
            <text x={x(new Date(aiOnset)) + 4} y={M.top + 10} fontSize="11" fill="var(--ai)">perkiraan mulai</text>
          </g>
        )}
        {aiFirst && (
          <g>
            <line x1={x(new Date(aiFirst))} x2={x(new Date(aiFirst))} y1={M.top} y2={h - M.bottom} stroke="var(--ai)" strokeWidth="2" />
            <text x={x(new Date(aiFirst)) + 4} y={M.top + 24} fontSize="11" fontWeight="700" fill="var(--ai)">AI mendeteksi</text>
          </g>
        )}
        {[60, 80].filter((t) => t <= y.domain()[1]).map((t) => (
          <g key={t}>
            <line x1={M.left} x2={w - M.right} y1={y(t)} y2={y(t)} stroke="var(--awas)" strokeDasharray="5 4" />
            <text x={w - M.right} y={y(t) - 4} fontSize="11" textAnchor="end" fill="var(--awas)">{t} °C (EA)</text>
          </g>
        ))}
        {paths.map((p) => (
          <path key={p.d} d={p.path} fill="none" stroke={DEPTH_COLORS[p.d] ?? "var(--ink)"} strokeWidth={p.d === 10 ? 1 : 1.6} />
        ))}
        <TimeAxis x={x} h={h} />
      </svg>
      <div className="legend">
        {series.depths_cm.map((d) => (
          <span key={d}><i style={{ background: DEPTH_COLORS[d] }} />{d} cm</span>
        ))}
        {y.domain()[1] < 60 && <span>Ambang EA 60 °C dan 80 °C berada di atas rentang grafik ini.</span>}
      </div>
    </div>
  );
}

export function ScoreChart({ series, range }: { series: Series; range: [string, string] }) {
  const [ref, w] = useWidth<HTMLDivElement>();
  const h = 165;
  const pts = series.ai;
  const x = scaleTime().domain([new Date(range[0]), new Date(range[1])]).range([M.left, w - M.right]);
  const max = Math.max(2, ...pts.map((p) => p.score));
  const y = scaleSymlog().domain([0, max]).range([h - M.bottom, M.top]);
  const ln = line<(typeof pts)[number]>().x((p) => x(new Date(p.ts))).y((p) => y(p.score));
  const ar = area<(typeof pts)[number]>().x((p) => x(new Date(p.ts))).y0(y(0)).y1((p) => y(p.score));
  const last = pts[pts.length - 1];

  return (
    <div ref={ref}>
      <div className="chart-title">
        Skor model termal
        <span>{last ? `sekarang ${fmt2(last.score)}; alarm jika di atas 1` : "menunggu commissioning selesai"}</span>
      </div>
      <svg width={w} height={h} role="img" aria-label="Grafik skor deteksi model termal">
        <g className="axis">
          {[0, 1, 10, 100, 1000].filter((t) => t <= max).map((t) => (
            <g key={t} transform={`translate(0,${y(t)})`}>
              <text x={M.left - 8} y={4} textAnchor="end">{t}</text>
            </g>
          ))}
        </g>
        <line x1={M.left} x2={w - M.right} y1={y(1)} y2={y(1)} stroke="var(--ink)" strokeDasharray="4 3" />
        <text x={w - M.right} y={y(1) - 5} fontSize="11" textAnchor="end" fill="var(--mute)">ambang, dikalibrasi pada data node ini</text>
        {pts.length > 1 && (
          <>
            <path d={ar(pts) ?? ""} fill="var(--ai)" opacity="0.12" />
            <path d={ln(pts) ?? ""} fill="none" stroke="var(--ai)" strokeWidth="2" />
          </>
        )}
        <TimeAxis x={x} h={h} />
      </svg>
    </div>
  );
}

export function DroughtChart({ data, fires }: { data: { date: string; dc: number }[]; fires: string[] }) {
  const [ref, w] = useWidth<HTMLDivElement>();
  const h = 170;
  const x = scaleTime().domain([new Date(data[0].date), new Date(data[data.length - 1].date)]).range([M.left, w - M.right]);
  const y = scaleLinear().domain([0, Math.max(400, ...data.map((d) => d.dc))]).nice().range([h - M.bottom, M.top]);
  const ar = area<(typeof data)[number]>().x((d) => x(new Date(d.date))).y0(y(0)).y1((d) => y(d.dc));
  const inRange = fires.filter((f) => new Date(f) >= new Date(data[0].date));
  return (
    <div ref={ref}>
      <svg width={w} height={h} role="img" aria-label="Grafik Drought Code setahun terakhir">
        <g className="axis">
          {y.ticks(4).map((t) => (
            <g key={t} transform={`translate(0,${y(t)})`}>
              <text x={M.left - 8} y={4} textAnchor="end">{t}</text>
            </g>
          ))}
        </g>
        <path d={ar(data) ?? ""} fill="var(--soil)" opacity="0.55" />
        <line x1={M.left} x2={w - M.right} y1={y(350)} y2={y(350)} stroke="var(--ink)" strokeDasharray="4 3" />
        <text x={M.left + 4} y={y(350) - 5} fontSize="11" fill="var(--mute)">350: batas sangat kering (BMKG)</text>
        {inRange.map((f) => (
          <g key={f}>
            <line x1={x(new Date(f))} x2={x(new Date(f))} y1={M.top} y2={h - M.bottom} stroke="var(--awas)" strokeWidth="1.5" />
          </g>
        ))}
        <TimeAxis x={x} h={h} />
      </svg>
      <div className="legend"><span><i style={{ background: "var(--awas)" }} />tanggal kebakaran</span><span>{data.length} hari terakhir</span></div>
    </div>
  );
}

export { fmtTime };

const PF_COLORS: Record<string, string> = { "60": "#a08766", "100": "#7a5a3a", "150": "#3f2e1f" };

/** Selisih harian blok bekas terbakar terhadap node kontrol, dengan kurva pendinginan yang diharapkan. */
export function PostfireChart({ series, reference }: { series: Series; reference: string | null }) {
  const [ref, w] = useWidth<HTMLDivElement>();
  const h = 190;
  const pf = series.postfire;
  if (!pf) return null;
  const days = pf.days.map((d) => new Date(d));
  const keys = ["60", "100", "150"].filter((k) => pf.depths[k]);
  const vals = keys.flatMap((k) => [...pf.depths[k].delta, ...pf.depths[k].expect]).filter((v): v is number => v != null);
  const x = scaleTime().domain([days[0], days[days.length - 1]]).range([M.left, w - M.right]);
  const y = scaleLinear().domain([Math.min(0, ...vals) - 1, Math.max(pf.limit_c + 2, ...vals) + 1]).nice().range([h - M.bottom, M.top]);
  const ln = (arr: (number | null)[]) =>
    line<number | null>().defined((v) => v != null).x((_, i) => x(days[i])).y((v) => y(v as number))(arr) ?? "";
  return (
    <div ref={ref}>
      <div className="chart-title">
        Selisih dengan node kontrol {reference ?? ""}
        <span>median harian, °C; garis putus-putus = kurva pendinginan yang diharapkan</span>
      </div>
      <svg width={w} height={h} role="img" aria-label="Grafik selisih suhu blok bekas terbakar terhadap node kontrol">
        <g className="axis">
          {y.ticks(5).map((t) => (
            <g key={t} transform={`translate(0,${y(t)})`}>
              <line x1={M.left} x2={w - M.right} stroke="var(--line)" strokeDasharray="2 4" />
              <text x={M.left - 8} y={4} textAnchor="end">{t}</text>
            </g>
          ))}
        </g>
        <line x1={M.left} x2={w - M.right} y1={y(pf.limit_c)} y2={y(pf.limit_c)} stroke="var(--awas)" strokeDasharray="5 4" />
        <text x={w - M.right} y={y(pf.limit_c) - 5} fontSize="11" textAnchor="end" fill="var(--awas)">
          10 °C: batas kembali ke suhu latar (EA Tabel 23)
        </text>
        {series.events.map((e) => (
          <g key={e.ts}>
            <line x1={x(new Date(e.ts))} x2={x(new Date(e.ts))} y1={M.top} y2={h - M.bottom} stroke="var(--ai)" strokeWidth="1.5" />
            <text x={x(new Date(e.ts)) + 4} y={M.top + 10} fontSize="11" fill="var(--ai)">{e.type}</text>
          </g>
        ))}
        {keys.map((k) => (
          <g key={k}>
            <path d={ln(pf.depths[k].expect)} fill="none" stroke={PF_COLORS[k]} strokeWidth="1.2" strokeDasharray="4 3" />
            <path d={ln(pf.depths[k].delta)} fill="none" stroke={PF_COLORS[k]} strokeWidth="2" />
          </g>
        ))}
        <TimeAxis x={x} h={h} />
      </svg>
      <div className="legend">
        {keys.map((k) => <span key={k}><i style={{ background: PF_COLORS[k] }} />{k} cm</span>)}
      </div>
    </div>
  );
}
