import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  turbopack: {
    // Set workspace root to avoid lockfile detection warning
    root: __dirname,
  },
  // Treat pdf-parse as a server-external package (CommonJS, Node.js only)
  serverExternalPackages: ['pdf-parse'],
};

export default nextConfig;
