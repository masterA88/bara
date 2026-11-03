"use client";

import * as maplibregl from "maplibre-gl";
import { useEffect, useRef } from "react";
import type { BlockStatus, Site } from "@/lib/api";

// MapLibre 6 memuat web worker dari URL. Bundler Next.js tidak menyalinnya, jadi file worker disalin ke
// public/maplibre/ (lihat script "postinstall" di package.json).
maplibregl.setWorkerUrl("/maplibre/maplibre-gl-worker.mjs");

const COLORS: Record<string, string> = {
  NORMAL: "#3d7a68",
  WASPADA: "#c9961a",
  SIAGA: "#cf5a26",
  AWAS: "#a8231c",
  none: "#9aa3a6",
};

function blocksGeo(site: Site, blocks: BlockStatus[], selected: string | null): GeoJSON.FeatureCollection {
  return {
    type: "FeatureCollection",
    features: site.blocks.map((b) => {
      const st = blocks.find((x) => x.block === b.id);
      return {
        type: "Feature",
        properties: {
          id: b.id,
          node: st?.node ?? null,
          color: COLORS[st?.level ?? "none"],
          label: st ? b.id : `${b.id} (tanpa node)`,
          selected: st?.node != null && st.node === selected,
        },
        geometry: { type: "Point", coordinates: [b.lon, b.lat] },
      };
    }),
  };
}

// Tambahkan sumber dan lapisan titik blok jika belum ada. Dipanggil saat peta selesai dimuat dan setiap data berubah,
// karena pada pemuatan pertama di produksi titik blok sempat tidak tergambar.
function ensureBlocks(m: maplibregl.Map, site: Site, blocks: BlockStatus[], selected: string | null) {
  if (!m.isStyleLoaded()) return;
  const src = m.getSource("blocks") as maplibregl.GeoJSONSource | undefined;
  if (src) {
    src.setData(blocksGeo(site, blocks, selected));
    return;
  }
  m.addSource("blocks", { type: "geojson", data: blocksGeo(site, blocks, selected) });
  m.addLayer({
    id: "blocks-halo", type: "circle", source: "blocks", filter: ["==", ["get", "selected"], true],
    paint: { "circle-radius": 22, "circle-color": "#1e2b30", "circle-opacity": 0.15 },
  });
  m.addLayer({
    id: "blocks", type: "circle", source: "blocks",
    paint: { "circle-radius": 13, "circle-color": ["get", "color"], "circle-stroke-color": "#f6f7f5", "circle-stroke-width": 2.5 },
  });
  m.addLayer({
    id: "blocks-label", type: "symbol", source: "blocks",
    layout: { "text-field": ["get", "label"], "text-size": 13, "text-offset": [0, 1.7], "text-font": ["Noto Sans Bold"] },
    paint: { "text-color": "#1e2b30", "text-halo-color": "#f6f7f5", "text-halo-width": 1.5 },
  });
}

export default function SiteMap({ site, blocks, selected, onSelect }: {
  site: Site; blocks: BlockStatus[]; selected: string | null; onSelect: (node: string) => void;
}) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const latest = useRef({ blocks, selected });
  const onSelectRef = useRef(onSelect);
  useEffect(() => {
    latest.current = { blocks, selected };
    onSelectRef.current = onSelect;
  });

  useEffect(() => {
    if (!el.current || map.current) return;
    const m = new maplibregl.Map({
      container: el.current,
      style: "https://tiles.openfreemap.org/styles/positron",
      center: [site.lon, site.lat],
      zoom: 16.2,
      attributionControl: { compact: true },
    });
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    m.scrollZoom.disable();
    m.on("load", () => {
      if (site.outline) {
        m.addSource("outline", { type: "geojson", data: site.outline });
        m.addLayer({ id: "outline-fill", type: "fill", source: "outline", paint: { "fill-color": "#8a7a66", "fill-opacity": 0.18 } });
        m.addLayer({ id: "outline-line", type: "line", source: "outline", paint: { "line-color": "#5c4f40", "line-width": 1.5 } });
      }
      ensureBlocks(m, site, latest.current.blocks, latest.current.selected);
      m.on("click", "blocks", (e: maplibregl.MapLayerMouseEvent) => {
        const node = e.features?.[0]?.properties?.node;
        if (node && node !== "null") onSelectRef.current(node);
      });
      m.on("mouseenter", "blocks", () => (m.getCanvas().style.cursor = "pointer"));
      m.on("mouseleave", "blocks", () => (m.getCanvas().style.cursor = ""));
    });
    map.current = m;
    return () => {
      m.remove();
      map.current = null;
    };
  }, [site]);

  useEffect(() => {
    const m = map.current;
    if (!m) return;
    ensureBlocks(m, site, blocks, selected);
    if (!m.isStyleLoaded()) m.once("idle", () => ensureBlocks(m, site, latest.current.blocks, latest.current.selected));
  }, [site, blocks, selected]);

  return (
    <div className="map-wrap">
      <div ref={el} className="map" aria-label="Peta TPA Putri Cempo dengan status tiap blok" />
      <p className="map-note">Batas TPA dari OpenStreetMap. Posisi blok masih perkiraan sampai ada peta blok dari DLH.</p>
    </div>
  );
}
