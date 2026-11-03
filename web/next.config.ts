import type { NextConfig } from "next";

// API Python (FastAPI) berjalan terpisah. Semua /api/* diteruskan ke sana agar browser tidak perlu CORS.
const API = process.env.BARA_API_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  async rewrites() {
    // Mode statis (deploy) membaca /data/*.json dan tidak butuh API.
    if (process.env.NEXT_PUBLIC_BARA_STATIC === "1") return [];
    return [{ source: "/api/:path*", destination: `${API}/api/:path*` }];
  },
};

export default nextConfig;
