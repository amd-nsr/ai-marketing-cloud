# 0003 — Browser talks to one origin; Next.js proxies `/api/*` to Django

**Status:** Accepted (2026-10-19)

## Context
Phase 1 introduces authentication. Options:

1. **Token (JWT) auth from the browser to a separate API origin.** Requires CORS, token
   storage in JS (XSS exposure) or a refresh-token dance.
2. **Django session cookies on a separate API origin.** Requires CORS with credentials
   and cross-site cookie configuration; fragile with third-party-cookie restrictions.
3. **Same origin:** the browser only talks to the Next.js origin; `/api/*` is proxied to
   Django. Django's session cookie is first-party, HttpOnly, and protected by Django's
   CSRF middleware.

## Decision
Option 3. `next.config.ts` rewrites `/api/:path*/` and `/api/:path*` to
`BACKEND_INTERNAL_URL` (the slash-terminated rule is listed first because `:path*`
drops trailing slashes and Django requires them). Phase 1 will use Django session
authentication with CSRF protection; no CORS middleware is installed.

## Consequences
- No CORS configuration, no tokens in browser JavaScript.
- `BACKEND_INTERNAL_URL` is compiled into the production frontend build (rewrites are
  build-time), so it is a Docker build argument. If per-environment images become a
  problem, replace the rewrite with a runtime Route Handler proxy.
- All browser API traffic passes through the Next.js server: one extra hop. Large media
  uploads should go directly to object storage via signed URLs (Phase 2), not through
  the proxy.
- Django sees the proxy's `Host` (`backend` in Compose); it must be in
  `DJANGO_ALLOWED_HOSTS`. Production must forward `X-Forwarded-Proto` correctly.
- Django's own admin is served directly by the backend, not through the frontend.
