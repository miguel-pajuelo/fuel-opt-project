# Railway Deployment Guide

This guide describes the first production deployment path for FuelOpt on Railway.

## 1. Create the Railway project

1. Open Railway.
2. Create a new project from GitHub.
3. Select the FuelOpt repository.
4. Let Railway build with Nixpacks.
5. Confirm the start command is loaded from `railway.json`.

Start command:

```bash
uvicorn app.api.main:app --host 0.0.0.0 --port $PORT
```

## 2. Configure variables

Add the values from `.env.railway.example` in Railway Variables. Real secrets must only be stored in Railway, never in Git.

Minimum required variables:

```env
ORS_API_KEY=<secret>
FUELOPT_ADMIN_TOKEN=<secret>
FUELOPT_ENABLE_API_DOCS=false
GAS_DB_PATH=/data/db/gas_stations.sqlite
MINETUR_SNAPSHOT_PATH=/data/cache/minetur_snapshot.json
BALLENOIL_RESULT_PATH=/data/cache/ballenoil_espana_combustible.txt
BALLENOIL_PRICES_PATH=/data/cache/ballenoil_precios.json
```

Optional feedback variables:

```env
GMAIL_USER=<secret>
GMAIL_APP_PASSWORD=<secret>
FEEDBACK_RECIPIENT=<secret>
```

## 3. Add persistent storage

Create a Railway Volume and mount it at:

```text
/data
```

FuelOpt should use:

```text
/data/db/gas_stations.sqlite
/data/cache/minetur_snapshot.json
```

Without a volume, the SQLite database and cache may be lost across redeploys.

## 4. First refresh

After the first deploy, run:

```bash
python scripts/refresh_catalog.py --source minetur
```

Then check:

```text
/health
```

The catalogue should not be degraded after a successful refresh.

## 5. Scheduled refresh

The web service owns the automatic refresh scheduler. Do not create a second
Railway worker service for SQLite refreshes; Railway volumes are service-instance
storage, so a separate worker may write a different `/data` volume from the web
service.

Required web-service deployment settings from `railway.json`:

```json
{
  "startCommand": "uvicorn app.api.main:app --host 0.0.0.0 --port $PORT",
  "cronSchedule": null,
  "numReplicas": 1,
  "requiredMountPath": "/data"
}
```

The web process starts one internal scheduler on startup. It waits until the next
12:00 `Europe/Madrid` slot, runs the existing safe refresh pipeline, then waits
for the next local calendar day.

Manual Railway cleanup:

- Delete or disable any existing Railway Cron Job for FuelOpt, especially an old
  four-hour refresh cron.
- Do not configure a Railway Cron Schedule on the web service.
- Do not run a separate refresh-worker service against `/data/db/gas_stations.sqlite`.
- Do not scale the web service above one replica unless distributed locking is
  added later.

## 6. Production verification

Before sharing the URL publicly:

- Home page returns 200.
- `/health` returns 200.
- `/docs` returns 404.
- `/openapi.json` returns 404.
- `POST /catalog/refresh` without token returns 403.
- Liters mode returns a sensible recommendation.
- Euros mode returns useful liters/liters advantage, not fake 0 EUR savings.
- Brand logos render in the filter panel and result card.
- Privacy page loads.

## 7. Domain

After the Railway URL is stable:

1. Add a custom domain in Railway.
2. Configure DNS as Railway instructs.
3. Wait for HTTPS certificate provisioning.
4. Re-test the production verification checklist.

## 8. Rollback

If a deployment breaks:

1. Roll back to the previous Railway deployment.
2. Check Railway logs.
3. Check `/health`.
4. If the catalogue was corrupted, restore from the previous SQLite/snapshot backup if available.
5. Do not run a destructive database command without a backup.
