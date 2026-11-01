import type { NextConfig } from "next";

// Dev server opened from other devices on the LAN (Next blocks dev assets from non-localhost origins otherwise):
// DEV_ORIGINS=192.168.1.20,other-host in web/.env.local, comma-separated.
const devOrigins = (process.env.DEV_ORIGINS || "").split(",").map((s) => s.trim()).filter(Boolean);

const nextConfig: NextConfig = {
  reactStrictMode: true,
  images: { unoptimized: true },
  allowedDevOrigins: [...devOrigins, "*.local"],
};

export default nextConfig;
