import type { Metadata } from "next";
import { Public_Sans } from "next/font/google";
import "maplibre-gl/dist/maplibre-gl.css";
import "./globals.css";

const publicSans = Public_Sans({ subsets: ["latin"], variable: "--font-sans" });

export const metadata: Metadata = {
  title: "BARA: TPA Putri Cempo",
  description: "Peringatan dini kebakaran TPA dari probe suhu di dalam timbunan.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="id" className={publicSans.variable}>
      <body>{children}</body>
    </html>
  );
}
