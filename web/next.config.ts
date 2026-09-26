import type { NextConfig } from "next";

const backend = process.env.RAILSYNC_API_ORIGIN ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  experimental: { workerThreads: true, cpus: 1 },
  // Local constrained hosts can run `tsc --noEmit` separately before setting this flag.
  typescript: { ignoreBuildErrors: process.env.RAILSYNC_SKIP_NEXT_TYPECHECK === "1" },
  async rewrites() {
    return [{ source: "/api/v1/:path*", destination: `${backend}/api/v1/:path*` }];
  },
};

export default nextConfig;
