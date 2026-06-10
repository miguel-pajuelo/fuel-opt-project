# Secrets & environment handling (H5)

FuelOpt keeps all real secrets out of the repository. This note explains the
rules and the manual rotation actions that follow from the security audit.

## Golden rules

- **`.env` is local-only.** It is listed in `.gitignore` and must never be
  committed. Verify with:
  ```bash
  git ls-files .env          # must print nothing (untracked)
  git check-ignore -v .env   # must report a .gitignore match
  ```
- **`.env.example` holds placeholders only.** Never put a real key in it. Copy
  it to `.env` locally and fill in real values there:
  ```bash
  cp .env.example .env
  ```
- **Never share `.env`.** Do not paste it into chats, issues, or commits, and do
  not post screenshots, terminal recordings, or logs that show its contents.
- **Releases do not ship `.env`.** `scripts/package_release.cmd` copies
  `.env.example` (not `.env`) and excludes `.env`/`.env.local` from directory
  copies (`robocopy /XF`). `scripts/secrets_check.py` is part of the release
  gate (`scripts/release_check.cmd`).

## Required rotations (do these manually)

These cannot be done from the repo; perform them in the respective provider
console and then update your local `.env` and your hosting provider's secrets.

- **`ORS_API_KEY` — rotate.** Before the H1 fix, the OpenRouteService key could
  be echoed in client-facing geocoding error responses, so treat it as
  potentially exposed. Generate a new key in the OpenRouteService dashboard,
  revoke the old one, and update `.env` / the deployment secret.
- **`GMAIL_APP_PASSWORD` — rotate if ever exposed.** If `.env` was ever shared,
  or appeared in a screenshot/log/recording, revoke the Google App Password and
  create a new one. (Standard usage otherwise keeps it local-only.)
- **`FUELOPT_ADMIN_TOKEN` — use a long random value** and rotate it if it may
  have leaked. It guards `POST /catalog/refresh`.

## Verifying rate-limit dependencies

SlowAPI must be installed for `/feedback` and other rate limits to actually
enforce at runtime:

```bash
python -c "import app.api.main as a; print(a._slowapi_available)"
```

`True` means limits are enforced. `False` means the no-op fallback is active —
install dependencies before any public exposure:

```bash
pip install -r requirements-web.txt
```

## Deployment variables (configure manually in Railway / your host)

Set these as provider-managed secrets/variables, never in a committed file:

| Variable | Purpose |
|---|---|
| `ORS_API_KEY` | OpenRouteService key (rotated). |
| `FUELOPT_ADMIN_TOKEN` | Long random token guarding `/catalog/refresh`. |
| `GMAIL_USER`, `GMAIL_APP_PASSWORD`, `FEEDBACK_RECIPIENT` | Feedback SMTP (optional). |
| `CORS_ORIGINS` | Comma-separated allowed origins (empty = same-origin only). |
| `ALERT_WEBHOOK_URL` | Optional 5xx alert webhook. |
| `FUELOPT_ENABLE_API_DOCS` | `false` in production. |
| `FUELOPT_ALLOW_LAN` | Keep `0` unless intentionally exposing on LAN. |
| `FUELOPT_TRUST_PROXY_HEADERS` | `1` only behind a trusted reverse proxy (see `docs/SECURITY_HARDENING_H3_H6_H8.md`). |
| `FUELOPT_LOG_CLIENT_IP` | `0` by default (logs anonymized IPs); `1` only for local/debug. |

No real secret values appear in this repository.
