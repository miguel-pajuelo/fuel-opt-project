# Security hardening: H3 / H6 / H8

This note documents the operational flags introduced for the audit findings
H3 (proxy rate-limit keys), H6 (security headers) and H8 (IP logging / PII),
and what still must be verified in a real proxied deployment (Railway).

## Environment flags

| Variable | Default | Effect |
|---|---|---|
| `FUELOPT_TRUST_PROXY_HEADERS` | `false` | When `true`, the rate-limit key is taken from the **first valid IP** in `X-Forwarded-For`. When `false`, only the direct peer (`request.client.host`) is used and forwarded headers are ignored. |
| `FUELOPT_LOG_CLIENT_IP` | `false` | When `true`, access logs include the raw client IP. When `false`, only a coarsely anonymized IP is logged (IPv4 → `/24`, IPv6 → `/48`). |

Both default to the safe/local behavior. Set them explicitly **only** in a
public deployment that sits behind a trusted reverse proxy.

## H3 — what must be verified on Railway

`X-Forwarded-For` is only trusted when `FUELOPT_TRUST_PROXY_HEADERS=true`. The
current implementation trusts the **left-most** entry, which assumes a single
trusted edge proxy that prepends the real client IP. Before relying on per-IP
rate limiting in production, confirm on the actual platform:

1. The edge proxy **always overwrites/prepends** `X-Forwarded-For` and does not
   pass through a client-supplied value unchanged. If clients can inject extra
   left-most entries, switch to selecting the IP at a fixed offset from the
   right (based on the known number of proxy hops) instead of the left-most.
2. The number of proxy hops in front of the app is stable.
3. `uvicorn`/the ASGI server is started with proxy headers enabled
   (e.g. `--proxy-headers --forwarded-allow-ips="*"`) if you also want
   `request.client.host` itself to reflect the forwarded address.

Until the above is confirmed, leave `FUELOPT_TRUST_PROXY_HEADERS=false`
(rate limiting then keys on the direct connection, which is correct for local
use and conservative behind a proxy).

## H6 — security headers

Every response carries:

- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Referrer-Policy: no-referrer`
- `Permissions-Policy: geolocation=(self), camera=(), microphone=()`

`geolocation=(self)` is intentional: the map's "center on my location" control
uses the browser Geolocation API on the same origin.

**No `Content-Security-Policy` is set.** The UI loads Leaflet and OSM tiles from
`unpkg`/CDN, loads GoatCounter analytics, and uses inline `onerror` handlers and
inline `style` attributes. A strict CSP would break these without app changes,
so CSP is deliberately left out of this minimal hardening pass and can be added
later together with the necessary frontend refactor.

## H8 — IP logging

Access logs keep `request_id`, `method`, `path`, `status` and `elapsed_ms`. The
client IP is anonymized by default and only logged raw when
`FUELOPT_LOG_CLIENT_IP=true` (local/debug diagnostics).
