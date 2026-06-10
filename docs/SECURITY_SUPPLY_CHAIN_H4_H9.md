# Supply-chain hardening: H4 (Leaflet SRI) / H9 (dependency audit)

## H4 — Subresource Integrity for Leaflet

Leaflet 1.9.4 is still loaded from the unpkg CDN in `static/index.html`. Both
tags now carry a Subresource Integrity (SRI) hash and `crossorigin="anonymous"`,
so the browser refuses to execute the asset if the bytes served by the CDN ever
change:

| Asset | SRI (sha384) |
|---|---|
| `leaflet@1.9.4/dist/leaflet.css` | `sha384-sHL9NAb7lN7rfvG5lfHpm643Xkcjzp4jFvuavGOndn6pjVqS6ny56CAt3nsEVT4H` |
| `leaflet@1.9.4/dist/leaflet.js`  | `sha384-cxOPjt7s7Iz04uaHJceBmS+qpjv2JkIHNVcuOrM+YHwZOmJGBXI00mdUXEq65HTH` |

### How the hashes were verified (not invented)

Each file was downloaded from **three independent CDNs** and the sha384 digest
was confirmed byte-identical across all of them before being pinned:

- `https://unpkg.com/leaflet@1.9.4/dist/<file>`
- `https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/<file>`
- `https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/<file>`

To regenerate / re-verify (e.g. after a Leaflet version bump):

```bash
python - <<'PY'
import urllib.request, hashlib, base64
def sri(u):
    b = urllib.request.urlopen(u, timeout=30).read()
    return "sha384-" + base64.b64encode(hashlib.sha384(b).digest()).decode()
for f in ("leaflet.css", "leaflet.js"):
    print(f, sri(f"https://unpkg.com/leaflet@1.9.4/dist/{f}"))
PY
```

`tests/frontend_static_check.py::test_external_leaflet_has_sri` enforces that any
external Leaflet tag keeps an `integrity` hash + `crossorigin`. Locally vendored
(same-origin) Leaflet is also accepted by that check.

> Note: a strict Content-Security-Policy is intentionally still not set (see
> `docs/SECURITY_HARDENING_H3_H6_H8.md`); SRI is the targeted mitigation for the
> CDN supply-chain risk.

## H9 — Dependency audit (`pip-audit`)

Audit command:

```bash
pip install pip-audit
pip-audit -r requirements-web.txt
```

The audit (run 2026-06-10, advisory DB current at that time) found 3 advisories
in 2 packages, both fixed with minimal version bumps:

| Package | Was | Advisory | Fixed in | Notes |
|---|---|---|---|---|
| `starlette` | 1.0.0 | PYSEC-2026-161 | **1.0.1** | `Host` header not validated when rebuilding `request.url`; path-based auth in middleware could be bypassed. Patch bump. |
| `requests` | 2.32.5 | CVE-2026-25645 | **2.33.0** | Predictable temp file in `extract_zipped_paths()`. FuelOpt does **not** call that function (standard HTTP only), so it was not exploitable here, but the pin is bumped for hygiene. |

After bumping the two pins, `pip-audit -r requirements-web.txt` reports
**"No known vulnerabilities found"**, and `pip install --dry-run -r
requirements-web.txt` resolves cleanly (`fastapi==0.136.0` is compatible with
`starlette==1.0.1`). No other dependencies were changed.
