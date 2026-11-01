import type { Metadata } from "next";
import { Barlow_Condensed, Courier_Prime } from "next/font/google";
import "./globals.css";

const type = Courier_Prime({ subsets: ["latin"], weight: ["400", "700"], variable: "--font-type", display: "swap" });
const head = Barlow_Condensed({ subsets: ["latin"], weight: ["500", "700", "800"], variable: "--font-head", display: "swap" });

export const metadata: Metadata = {
  title: "AnyScene",
  description: "Turn a reference image into a photoreal Blender scene, and watch it being built.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${type.variable} ${head.variable}`}>
      <body>{children}</body>
    </html>
  );
}
