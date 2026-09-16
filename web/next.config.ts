import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  experimental: {
    // Static generation otherwise forks child processes, which this Windows
    // environment rejects with EPERM.
    workerThreads: true,
  },
  typescript: {
    // `npm run build` runs `tsc --noEmit` first. Skipping Next's duplicate
    // checker avoids its Windows child-process spawn path.
    ignoreBuildErrors: true,
  },
};

export default nextConfig;
