// Sumber data dashboard. Mode biasa memanggil API FastAPI lewat /api/*. Mode statis
// (NEXT_PUBLIC_BARA_STATIC=1, dipakai untuk deploy) membaca file JSON hasil api/export_static.py di /data/*.
import type { Comparison, Series, Site, Status, Weather } from "./api";
import { get } from "./api";

export const STATIC = process.env.NEXT_PUBLIC_BARA_STATIC === "1";

let steps: Promise<number[]> | null = null;
const seriesCache = new Map<string, Promise<Series>>();

function getSteps(): Promise<number[]> {
  steps ??= get<{ steps: string[] }>("/data/steps.json").then((s) => s.steps.map((t) => Date.parse(t)));
  return steps;
}

export const loadSite = () => get<Site>(STATIC ? "/data/site.json" : "/api/site");
export const loadWeather = () => get<Weather>(STATIC ? "/data/weather.json" : "/api/weather");
export const loadComparison = () => get<Comparison>(STATIC ? "/data/comparison.json" : "/api/comparison");

export async function fieldAvailable(): Promise<boolean> {
  if (STATIC) return false;
  return get<Status>("/api/status?source=field").then(() => true, () => false);
}

export async function loadStatus(source: string, until: string | null, signal?: AbortSignal): Promise<Status> {
  if (!STATIC) {
    const q = new URLSearchParams({ source });
    if (until) q.set("until", until);
    return get<Status>(`/api/status?${q}`, signal);
  }
  const s = await getSteps();
  const t = until ? Date.parse(until) : Infinity;
  let i = s.length - 1;
  while (i > 0 && s[i] > t) i--;
  return get<Status>(`/data/status/${i}.json`, signal);
}

export async function loadSeries(node: string, source: string, until: string | null, signal?: AbortSignal): Promise<Series> {
  if (!STATIC) {
    const q = new URLSearchParams({ source });
    if (until) q.set("until", until);
    return get<Series>(`/api/nodes/${node}/series?${q}`, signal);
  }
  if (!seriesCache.has(node)) seriesCache.set(node, get<Series>(`/data/series/${node}.json`));
  const full = await seriesCache.get(node)!;
  const t = until ? Date.parse(until) : Infinity;
  const upto = <T extends { ts: string }>(a: T[]) => a.filter((r) => Date.parse(r.ts) <= t);
  let postfire = full.postfire;
  if (postfire) {
    const n = postfire.days.filter((d) => Date.parse(d) + 24 * 3600_000 <= t + 3600_000).length;
    postfire = {
      ...postfire,
      days: postfire.days.slice(0, n),
      depths: Object.fromEntries(Object.entries(postfire.depths).map(([k, v]) => [k, { delta: v.delta.slice(0, n), expect: v.expect.slice(0, n) }])),
    };
  }
  return { ...full, temps: upto(full.temps), ai: upto(full.ai), events: upto(full.events), postfire };
}
