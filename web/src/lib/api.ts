export type LevelName = "NORMAL" | "WASPADA" | "SIAGA" | "AWAS";

export interface AiState {
  detected: boolean;
  effect: "naikkan" | "perhatian" | "tidak";
  calibrated: boolean;
  score: number;
  z_m: number | null;
  onset: string | null;
  alpha: number;
  alpha_source: "data" | "prior";
  learn_end: string;
}

export interface ProbeState {
  depth_cm: number;
  temp_c: number | null;
  baseline_c: number | null;
  baseline_status: "settling" | "learning" | "ready";
  slope_c_day: number | null;
  level: LevelName;
  permen: string | null;
}

export interface PostfireState {
  depth_cm: number;
  status: string;
  level: LevelName;
  sentence: string;
  delta_c: number | null;
  expect_c: number | null;
  tau_days: number | null;
  start_class: string | null;
  flags: string[];
  days_below: number;
}

export interface EventItem {
  ts: string;
  type: string;
  note: string;
}

export interface BlockStatus {
  node: string;
  block: string;
  level: LevelName;
  rule_level: LevelName;
  action: string;
  commissioning: string;
  reasons: string[];
  gas_flags: string[];
  ai: AiState | null;
  mode: "normal" | "kontrol" | "pasca_kebakaran";
  reference: string | null;
  since: string | null;
  postfire: PostfireState[];
  events: EventItem[];
  latest: { ts: string; t_air: number | null; probes: Record<string, number | null>; permen: Record<string, string | null> };
  probes: ProbeState[];
}

export interface Status {
  ai_level_score: number;
  source: string;
  simulated: boolean;
  until: string;
  range: { start: string; end: string };
  blocks: BlockStatus[];
}

export interface Series {
  node: string;
  depths_cm: number[];
  temps: ({ ts: string; t_air: number | null } & Record<string, number | null | string>)[];
  ai: { ts: string; score: number; detected: boolean; z_m: number | null }[];
  postfire: { days: string[]; depths: Record<string, { delta: (number | null)[]; expect: (number | null)[] }>; limit_c: number } | null;
  events: EventItem[];
}

export interface Site {
  name: string;
  lat: number;
  lon: number;
  area_ha: number;
  outline: GeoJSON.FeatureCollection | null;
  blocks: { id: string; lat: number; lon: number; assumed: boolean }[];
  fires: { start: string; end: string | null; note: string; start_exact: boolean }[];
}

export interface Weather {
  latest: { date: string; dc: number; dc_class: string; dc_pct_dry_season: number; ffmc: number; ffmc_class: string };
  series: { date: string; dc: number; ffmc: number }[];
}

export interface Comparison {
  rows: {
    node: string;
    block: string;
    truth: { z_m: number; q_w_m3: number; onset: string } | null;
    mode: string;
    scenario: string | null;
    ai_hours_after_onset: number | null;
    ai_lift_hours_after_onset: number | null;
    ai_z_m: number | null;
    rule_hours_after_onset: number | null;
  }[];
  note: string;
}

export async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(path, { signal, cache: "no-store" });
  if (!res.ok) {
    let detail = `${res.status}`;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {}
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

const num = new Intl.NumberFormat("id-ID", { maximumFractionDigits: 1, minimumFractionDigits: 1 });
const num2 = new Intl.NumberFormat("id-ID", { maximumFractionDigits: 2, minimumFractionDigits: 2 });
export const fmt1 = (v: number | null | undefined) => (v == null ? "-" : num.format(v));
export const fmt2 = (v: number | null | undefined) => (v == null ? "-" : num2.format(v));
export const signed = (v: number) => (v >= 0 ? "+" : "−") + num.format(Math.abs(v));

const dt = new Intl.DateTimeFormat("id-ID", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZone: "Asia/Jakarta" });
const d = new Intl.DateTimeFormat("id-ID", { day: "numeric", month: "long", year: "numeric", timeZone: "Asia/Jakarta" });
export const fmtTime = (iso: string | null | undefined) => (iso ? dt.format(new Date(iso)) : "-");
export const fmtDate = (iso: string) => d.format(new Date(iso));

export const LEVEL_LABEL: Record<LevelName, string> = {
  NORMAL: "Normal",
  WASPADA: "Waspada",
  SIAGA: "Siaga",
  AWAS: "Awas",
};

export const MODE_LABEL: Record<string, string> = {
  normal: "",
  kontrol: "Node kontrol",
  pasca_kebakaran: "Bekas terbakar",
};

/** Kedalaman pasca-kebakaran yang paling menentukan: level tertinggi, lalu selisih terbesar. */
export function keyPostfire(pf: PostfireState[]): PostfireState | null {
  const order: Record<LevelName, number> = { NORMAL: 0, WASPADA: 1, SIAGA: 2, AWAS: 3 };
  const deep = pf.filter((p) => p.depth_cm >= 60);
  if (!deep.length) return null;
  return [...deep].sort((a, b) => order[b.level] - order[a.level] || (b.delta_c ?? 0) - (a.delta_c ?? 0))[0];
}

export const PERMEN_SHORT: Record<string, string> = {
  "suhu normal TPA": "normal",
  "peningkatan aktivitas biologi": "aktivitas biologi naik",
  "peningkatan aktivitas biologi abnormal": "abnormal",
  "telah terjadi kebakaran TPA": "kebakaran",
};

export const POSTFIRE_STATUS: Record<string, string> = {
  "acuan belum ada": "acuan kontrol belum ada",
  commissioning: "commissioning pasca-kebakaran",
  mendingin: "mendingin",
  "berhenti mendingin": "pendinginan berhenti",
  naik: "naik melawan pendinginan",
  "kembali ke latar": "kembali ke suhu latar",
};
