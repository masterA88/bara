"use client";

import { scaleLinear } from "d3-scale";
import type { BlockStatus } from "@/lib/api";
import { PERMEN_SHORT, fmt1, fmt2, fmtTime, signed } from "@/lib/api";

const W = 250;
const H = 440;
const TOP = 38;
const BOTTOM = 18;
const COL_X = 36;
const COL_W = 54;
const MAX_DEPTH = 2.0;

// Warna probe menurut kenaikan dari baseline (C). Ambang +10 C adalah EA Tabel 23; 3 dan 6 C hanya pembagi warna.
function heat(delta: number | null): string {
  if (delta == null) return "var(--soil-light)";
  if (delta >= 10) return "var(--awas)";
  if (delta >= 6) return "var(--siaga)";
  if (delta >= 3) return "var(--waspada)";
  return "var(--paper)";
}

export default function Borehole({ block }: { block: BlockStatus }) {
  const y = scaleLinear().domain([0, MAX_DEPTH]).range([TOP, H - BOTTOM]);
  const probes = Object.entries(block.latest.probes).map(([d, t]) => {
    const depth = Number(d);
    const p = block.probes.find((x) => x.depth_cm === depth);
    const pf = block.postfire.find((x) => x.depth_cm === depth);
    const delta = pf ? pf.delta_c : p && p.baseline_c != null && t != null ? t - p.baseline_c : null;
    return { depth, t, delta, ruleProbe: !!p, permen: block.latest.permen?.[d] ?? null };
  });
  const ai = block.ai;
  const postfire = block.mode === "pasca_kebakaran";
  const zAi = ai?.detected && ai.z_m != null ? ai.z_m : null;

  return (
    <figure style={{ margin: 0 }}>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img"
           aria-label={`Penampang tali probe node ${block.node} di blok ${block.block}`}>
        <defs>
          <pattern id="strata" width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(25)">
            <rect width="8" height="8" fill="var(--soil)" />
            <line x1="0" y1="0" x2="0" y2="8" stroke="#7a6b58" strokeWidth="3" />
          </pattern>
        </defs>

        <text x={COL_X} y={14} fontSize="12" fill="var(--mute)">Udara {fmt1(block.latest.t_air)} °C</text>
        <line x1={4} x2={W - 4} y1={TOP} y2={TOP} stroke="var(--ink)" strokeWidth="1.5" />
        <text x={W - 4} y={TOP - 6} fontSize="11" fill="var(--mute)" textAnchor="end">permukaan timbunan</text>

        <rect x={COL_X} y={TOP} width={COL_W} height={H - BOTTOM - TOP} fill="url(#strata)" opacity="0.9" />
        <rect x={COL_X + COL_W / 2 - 3} y={TOP - 10} width={6} height={y(1.5) - TOP + 18} fill="#9aa3a6" rx="2" />

        {[0.5, 1, 1.5, 2].map((d) => (
          <g key={d}>
            <line x1={COL_X - 6} x2={COL_X} y1={y(d)} y2={y(d)} stroke="var(--mute)" />
            <text x={COL_X - 8} y={y(d) + 4} fontSize="10" fill="var(--mute)" textAnchor="end">{fmt1(d)}</text>
          </g>
        ))}

        {zAi != null && (
          <g>
            <rect x={COL_X - 4} y={y(zAi) - 14} width={COL_W + 8} height={28} fill="var(--ai)" opacity="0.18" rx="3" />
            <line x1={COL_X - 4} x2={COL_X + COL_W + 4} y1={y(zAi)} y2={y(zAi)} stroke="var(--ai)" strokeWidth="2" strokeDasharray="5 3" />
          </g>
        )}

        {probes.map(({ depth, t, delta, ruleProbe, permen }) => {
          const cy = y(depth / 100);
          return (
            <g key={depth}>
              <circle cx={COL_X + COL_W / 2} cy={cy} r={8} fill={heat(delta)} stroke="var(--ink)" strokeWidth="1.5" />
              <text x={COL_X + COL_W + 12} y={cy - 2} fontSize="13" fontWeight="700" fill="var(--ink)">{fmt1(t)} °C</text>
              <text x={COL_X + COL_W + 12} y={cy + 12} fontSize="11" fill="var(--mute)">
                {depth} cm{ruleProbe ? (delta != null ? `, ${signed(delta)} ${postfire ? "dari kontrol" : "dari normal"}` : ", baseline belum siap") : ", untuk difusivitas"}
              </text>
              {ruleProbe && permen && (
                <text x={COL_X + COL_W + 12} y={cy + 24} fontSize="10" fill="var(--mute)">Permen PU: {PERMEN_SHORT[permen] ?? permen}</text>
              )}
            </g>
          );
        })}

        {zAi != null && (
          <text x={COL_X + COL_W + 12} y={Math.min(y(zAi) + 4, H - 4)} fontSize="11" fontWeight="700" fill="var(--ai)"
                dy={probes.some((p) => Math.abs(y(p.depth / 100) - y(zAi)) < 22) ? 26 : 0}>
            perkiraan sumber {fmt2(zAi)} m
          </text>
        )}
      </svg>
      <figcaption className="foot">
        {zAi != null
          ? `Model termal memperkirakan sumber panas di kedalaman sekitar ${fmt2(zAi)} m, mulai ${fmtTime(ai!.onset)}.`
          : "Model termal belum melihat sumber panas di tali probe ini."}
      </figcaption>
    </figure>
  );
}
