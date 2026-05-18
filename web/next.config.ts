import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  allowedDevOrigins: ["o2monitor.local.sparkcodelabs.com"],
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: "http://localhost:7071/api/:path*",
      },
    ];
  },
};

export default nextConfig;
