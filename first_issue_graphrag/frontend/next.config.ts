import type { NextConfig } from "next";

/*
 * Next.js config — reverse-proxy the API to FastAPI.
 *
 * The browser calls the SAME origin it loaded from (relative `/api/*`), and
 * Next rewrites those requests to the FastAPI backend server-side. This means:
 *   - only port 3000 needs to be exposed externally (e.g. over ZeroTier);
 *     FastAPI on 8090 stays bound to localhost and is never reached by the
 *     remote browser directly;
 *   - no CORS is required (the browser only ever talks to the Next origin).
 *
 * The destination uses 127.0.0.1 (NOT `localhost`) on purpose: Node's resolver
 * tries IPv6 `::1` first and waits ~10s before falling back to IPv4, so
 * `localhost:8090` would make every proxied call slow. Override with the
 * BACKEND_ORIGIN env var if the backend ever moves.
 */
const BACKEND_ORIGIN = process.env.BACKEND_ORIGIN ?? "http://127.0.0.1:8090";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      // App Router has no /api route handlers, so this prefix is free to proxy.
      { source: "/api/:path*", destination: `${BACKEND_ORIGIN}/api/:path*` },
    ];
  },
};

export default nextConfig;
