import path from "node:path";

import { loadEnvConfig } from "@next/env";
import type { NextConfig } from "next";

// Share the repository-root .env with the backend during local development.
// Real environment variables always take precedence.
loadEnvConfig(path.resolve(process.cwd(), ".."));

const backendUrl = (process.env.BACKEND_INTERNAL_URL ?? "http://localhost:8000").replace(/\/$/, "");

const nextConfig: NextConfig = {
  output: "standalone",
  cacheComponents: true,
  partialPrefetching: true,
  poweredByHeader: false,
  experimental: {
    // With proxy.ts present, Next.js buffers request bodies and silently truncates them
    // above this size, which breaks proxied uploads. Keep it at least the backend's
    // MAX_MEDIA_UPLOAD_BYTES (video/audio library uploads, 100 MB by default).
    proxyClientMaxBodySize: (process.env.MAX_PROXY_BODY_SIZE ?? "105mb") as `${number}mb`,
  },
  // Django routes end in "/"; don't let Next redirect them away before proxying.
  skipTrailingSlashRedirect: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  // Baseline browser hardening for every page. Script sources are not restricted yet
  // (Next.js inline bootstrap scripts need nonces); see docs/security/review.md.
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "same-origin" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
          {
            key: "Content-Security-Policy",
            value: "frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'",
          },
        ],
      },
    ];
  },
  // The browser only ever talks to this origin. /api/* is proxied to Django, which
  // keeps session cookies first-party and avoids CORS (docs/decisions/0003).
  async rewrites() {
    // `:path*` drops a trailing slash, so the slash-terminated form is matched first.
    return [
      { source: "/api/:path*/", destination: `${backendUrl}/api/:path*/` },
      { source: "/api/:path*", destination: `${backendUrl}/api/:path*` },
    ];
  },
};

export default nextConfig;
