# FuelOpt Publication Roadmap

This roadmap defines the professional path to publish FuelOpt as a public web product. It assumes the current FastAPI + static frontend architecture remains in place and Railway is the preferred first deployment target.

## Executive recommendation

Launch FuelOpt in phases:

1. Private production beta on Railway Hobby.
2. Public beta with monitoring, refresh alerts, and usage guardrails.
3. Hardened public release with domain, analytics, and incident process.
4. Scale decision after real usage data.

Railway is a good first target because FuelOpt needs a persistent Python web service, scheduled refresh jobs, secrets, and a small persistent volume for SQLite/cache. A static-only platform is not enough for the current architecture.

## Current product state

Ready:

- Polished web UI served by FastAPI.
- Route-based optimization.
- Liters and euros input modes.
- Brand filtering and logo catalogue.
- ORS routing with fallback behavior.
- Protected catalog refresh endpoint.
- FastAPI docs hidden by default.
- Privacy page.
- Local SQLite catalogue and MINETUR snapshot.
- Lightweight release checks.

Known risks:

- SQLite/cache require persistent storage in production.
- MINETUR availability can degrade catalogue freshness.
- ORS daily limits can be reached if traffic grows.
- OSM tile usage should remain respectful; a tile provider may be needed later.
- No full production observability yet.

## Phase 0 - Deployment readiness

Goal: make the repository deployable without touching core app logic.

Tasks:

- Keep `railway.json` with the production start command.
- Use Railway Variables for secrets.
- Create a Railway Volume mounted at `/data`.
- Set production paths to `/data/...`.
- Confirm `/health` works as deployment healthcheck.
- Confirm `/docs` and `/openapi.json` remain disabled.
- Confirm `/catalog/refresh` returns 403 without token.

Estimated time: 2-4 hours.

Estimated cost: 0 EUR before deploy, except optional domain purchase.

Exit criteria:

- App deploys from GitHub.
- Public URL loads the polished UI.
- Logs show no missing environment variable errors.
- First manual catalogue refresh succeeds.

## Phase 1 - Private beta on Railway

Goal: run FuelOpt publicly but share the URL only with trusted testers.

Tools:

- Railway Hobby plan.
- Railway Volume mounted at `/data`.
- Railway Variables.
- OpenRouteService Standard API key.
- GitHub repository deployment.

Required Railway variables:

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

Operational steps:

1. Create Railway project from GitHub.
2. Select the FuelOpt repository.
3. Let Railway detect Python/Nixpacks.
4. Verify start command from `railway.json`.
5. Add variables.
6. Add volume mounted at `/data`.
7. Deploy.
8. Run one manual refresh.
9. Test real routes.

Estimated time: 0.5-1 day.

Estimated monthly cost:

- Railway Hobby minimum: about USD 5/month.
- Railway volume: about USD 0.15/GB/month.
- ORS Standard: 0 EUR if within public limits.
- Domain: optional, usually 10-20 EUR/year.

Expected first-month total: about 5-12 EUR/month plus optional domain.

Exit criteria:

- UI works on Railway URL.
- Liters mode works.
- Euros mode works.
- Logos render in cards and result panel.
- Catalogue status is not degraded after refresh.
- `/docs` returns 404.
- `/catalog/refresh` without token returns 403.

## Phase 2 - Scheduled catalogue refresh

Goal: keep prices fresh without manual intervention.

Preferred approach:

- Use the single web service as the only SQLite writer.
- Keep `railway.json` at `numReplicas: 1` and `requiredMountPath: /data`.
- Let the web process start one internal scheduler.
- Schedule: daily at 12:00 `Europe/Madrid`, including daylight-saving changes.
- Do not configure a Railway Cron Schedule.
- Do not create a separate refresh-worker service for SQLite writes.

Alternative approach:

- Use an external cron monitor that calls `POST /catalog/refresh`.
- Send `Authorization: Bearer <FUELOPT_ADMIN_TOKEN>`.

Recommendation:

Use the single web-service scheduler first. A separate Railway worker cannot be
assumed to share the same SQLite volume as the web service, and Railway Cron Jobs
are short-lived job runners rather than long-running scheduler processes.

Deployment cleanup:

- Delete or disable any old Railway dashboard cron service, especially any four-hour refresh cron.
- Keep the web service at one replica unless distributed locking is introduced.

Estimated time: 2-4 hours.

Estimated monthly cost:

- Usually small additional compute because the job only runs every 4 hours.
- Budget 1-5 USD/month extra until measured.

Exit criteria:

- Refresh job runs every 4 hours.
- Previous run exits cleanly.
- Catalogue `source_fetched_at` updates.
- Alert is triggered if refresh fails or catalogue becomes degraded.

## Phase 3 - Monitoring and safety guardrails

Goal: know quickly when FuelOpt is broken, stale, or too expensive.

Tools:

- Railway logs and metrics.
- UptimeRobot, Better Stack, or similar uptime monitor.
- Optional webhook alert to email/Discord/Slack.
- ORS dashboard/API usage page.

Checks to monitor:

- `/health` returns 200.
- Catalogue status is fresh/recent.
- Refresh job exits successfully.
- ORS errors and 429 rate limits.
- 5xx errors on `/optimize`, `/geocode`, `/route/stopover`.
- Railway spend and memory usage.

Estimated time: 0.5-1 day.

Estimated monthly cost:

- Basic uptime monitor: 0-10 EUR/month.
- Railway extra logs/usage: included in platform usage.

Exit criteria:

- You receive an alert when the site is down.
- You receive an alert when refresh fails.
- You know daily ORS usage.
- You have a documented rollback path.

## Phase 4 - Public launch

Goal: make FuelOpt available to anyone.

Tasks:

- Buy and configure domain.
- Enable HTTPS on Railway domain mapping.
- Update privacy page with production contact/channel.
- Add lightweight analytics if desired.
- Add support/feedback routing.
- Publish announcement.
- Watch logs during the first 48 hours.

Estimated time: 0.5-1 day.

Estimated monthly cost:

- Railway: 5-20 USD/month for small beta.
- Domain: 10-20 EUR/year.
- ORS: 0 EUR while within Standard limits.
- Monitoring/analytics: 0-10 EUR/month initially.

Exit criteria:

- Public domain works with HTTPS.
- Product works without local dependencies.
- Refresh has run at least twice in production.
- No public API docs are exposed.
- No secrets are in the repository.

## Phase 5 - Scale decision

Trigger this phase only after real usage data shows demand.

Potential upgrades:

- Move from Railway Hobby to Pro if reliability/team needs justify it.
- Move SQLite to Postgres if write contention, snapshots, or concurrent workloads become limiting.
- Add a proper tile provider if public OSM tiles become inappropriate.
- Add ORS paid/custom/on-prem alternative if limits are hit.
- Add caching for geocoding/routing to reduce API calls.
- Add a queue for long route optimizations if latency grows.

Estimated time: 2-5 days depending on scope.

Estimated monthly cost:

- Small production: 20-35 EUR/month.
- Growing traffic: 35-100+ EUR/month depending on routing, map tiles, monitoring, and database.

## Budget scenarios

| Scenario | Monthly estimate | When it applies |
| --- | ---: | --- |
| Local only | 0 EUR | Development only |
| Railway private beta | 5-12 EUR | Low traffic, Hobby plan |
| Public beta | 10-25 EUR | Domain, monitoring, scheduled refresh |
| Small production | 20-35 EUR | More traffic, stronger monitoring |
| Growth | 35-100+ EUR | Higher ORS usage, tile provider, DB upgrade |

## Go/no-go checklist

Go when all are true:

- Deployment is reproducible from GitHub.
- Secrets live only in Railway Variables.
- Volume is mounted and used by DB/cache paths.
- `/health` is green.
- Catalogue is fresh or recent, not degraded.
- Refresh job has completed successfully.
- `/docs` is hidden.
- `/catalog/refresh` is protected.
- Liters and euros modes both produce sensible results.
- Brand logos render correctly.
- Privacy page is accessible.

Do not launch publicly if any are true:

- Catalogue is degraded for unknown reasons.
- ORS quota is already close to limits during beta.
- Refresh job depends on your local machine.
- `.env` or credentials are staged/tracked.
- Public docs or refresh endpoint are exposed accidentally.

## Sources checked

- Railway pricing: https://docs.railway.com/pricing
- Railway build/deploy: https://docs.railway.com/build-deploy
- Railway cron jobs: https://docs.railway.com/reference/cron-jobs
- Railway volumes: https://docs.railway.com/volumes
- OpenRouteService plans: https://staging.openrouteservice.org/plans/
