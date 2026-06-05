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

/*
 * Hosts allowed to load Next.js dev resources (/_next/*, HMR, fonts) from a
 * DIFFERENT origin than localhost. Next 16 blocks these by default, so opening
 * the dev server from a phone over ZeroTier/LAN (e.g. http://ZEROTIER_IP:3000)
 * silently fails to hydrate -> example chips never load and "Retrieve" does
 * nothing. List the LAN/ZeroTier IPs (and any extra dev hosts) here. Override or
 * extend via ALLOWED_DEV_ORIGINS (comma-separated) without editing code.
 * NOTE: dev-only; `next start` (production) ignores this.
 */
const ALLOWED_DEV_ORIGINS = (
  process.env.ALLOWED_DEV_ORIGINS ?? "ZEROTIER_IP,LAN_IP"
)
  .split(",")
  .map((h) => h.trim())
  .filter(Boolean);

const nextConfig: NextConfig = {
  allowedDevOrigins: ALLOWED_DEV_ORIGINS,
  async rewrites() {
    return [
      // App Router has no /api route handlers, so this prefix is free to proxy.
      { source: "/api/:path*", destination: `${BACKEND_ORIGIN}/api/:path*` },
      // Read-only socorico capture (images + PDFs) served by the backend mount.
      {
        source: "/socorico-assets/:path*",
        destination: `${BACKEND_ORIGIN}/socorico-assets/:path*`,
      },
    ];
  },
};

export default nextConfig;
