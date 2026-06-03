# FuelOpt

FuelOpt is a prototype route-based fuel optimizer for Spain. It combines station price data, route-aware candidate selection, and detour cost estimates to help drivers choose whether a cheaper fuel station is actually worth visiting.

## Problem It Solves

Fuel prices can vary meaningfully between nearby stations, but the cheapest price per litre is not always the cheapest real option. A station may require a detour that consumes time and fuel. FuelOpt estimates the tradeoff by comparing candidate stations near a selected route and calculating the net economic value after the extra distance.

## Main Features

- Route-based gas station optimization for origin and destination searches.
- Cheapest refuelling option ranking by effective total cost, not just displayed price.
- Detour-aware cost calculation using consumption, estimated extra kilometres, and reference fuel cost.
- Litres and euros input modes: optimize a fixed refill amount or a fixed budget.
- Brand filtering with inclusion and exclusion support, including independent/unrecognized stations.
- OpenRouteService geocoding, matrix, and directions support when `ORS_API_KEY` is configured.
- Haversine-based fallback/estimate routing for prototype flows and no-key local usage.
- Fuel price catalogue freshness/status endpoints for the local SQLite catalogue and source snapshot metadata.

## How The Optimization Works

1. The user selects an origin, destination, fuel type, consumption, input mode, and optional brand filters.
2. FuelOpt resolves the selected route. With OpenRouteService enabled it can use road-route data; otherwise it uses Haversine estimates with a configurable detour factor.
3. The backend searches nearby candidate stations from the SQLite price catalogue. For route trips it prefers candidates along the route corridor; for same-place/local searches it uses a local radius.
4. Candidate stations are filtered by available fuel price, brand rules, distance, and configured search limits.
5. Each candidate is scored by combining the refill cost with estimated detour fuel cost.
6. FuelOpt compares each candidate against the best reference alternative and reports estimated net savings or, in budget mode, estimated extra useful litres.

## Tech Stack

- Python
- FastAPI
- SQLite
- Leaflet
- HTML/CSS/JavaScript
- OpenRouteService, when configured through `ORS_API_KEY`

## Project Structure

```text
.
|-- app/
|   |-- api/                 FastAPI app, routes, UI loading, warnings
|   |-- data_sources/        MINETUR/Ballenoil adapters and brand catalogue logic
|   |-- legacy_cli/          Legacy command-line scraper/optimizer modules
|   |-- optimizer/           Route candidate ranking and detour-aware scoring
|   |-- routing/             OpenRouteService integration and route helpers
|   |-- storage/             SQLite persistence, validation, and publish helpers
|   |-- config.py            Environment and path configuration
|   `-- models.py            Shared data models
|-- data/
|   |-- cache/               Source snapshots and cached catalogue inputs
|   `-- db/                  Active SQLite station catalogue
|-- docs/                    Operational notes and cataloguing references
|-- scripts/                 Catalogue refresh, rebuild, release, and packaging scripts
|-- static/                  Leaflet frontend, styles, pages, and brand assets
|-- tests/                   Lightweight Python and static frontend checks
|-- main.py                  Compatibility entrypoint and local API launcher
|-- requirements-web.txt     Python web/runtime dependencies
|-- Dockerfile
`-- docker-compose.yml
```

## Local Installation

Requirements:

- Python 3.10 or newer
- An OpenRouteService API key for geocoding and road-route calculations
- Git

Set up a local environment:

```bash
git clone https://github.com/miguel-pajuelo/fuel-route-optimizer.git
cd fuel-route-optimizer
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-web.txt
cp .env.example .env
```

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-web.txt
Copy-Item .env.example .env
```

Edit `.env` and add private values only there. Do not commit `.env`.

## Environment Variables

Use `.env.example` as the source of expected configuration. It contains placeholder values only.

| Variable | Purpose |
| --- | --- |
| `ORS_API_KEY` | OpenRouteService key for geocoding, directions, and route matrix calls. |
| `GAS_DB_PATH` | Path to the active SQLite fuel station database. |
| `MINETUR_SNAPSHOT_PATH` | Path to the cached MINETUR source snapshot. |
| `BALLENOIL_RESULT_PATH` | Path to the legacy Ballenoil scraper output. |
| `BALLENOIL_PRICES_PATH` | Path to cached Ballenoil price data. |
| `CONSUMPTION_L_100KM` | Default vehicle consumption used by the optimizer. |
| `MAX_ROUTE_CANDIDATES` | Maximum candidates scored per optimization request. |
| `PREFILTER_RADIUS_KM` | Initial local station search radius. |
| `LOCAL_SEARCH_RADIUS_KM` | Preferred radius for local/same-place searches. |
| `CORRIDOR_RADIUS_KM` | Preferred route corridor width for route searches. |
| `MAX_SEARCH_EXTENT_KM` | Upper bound for economic search expansion. |
| `OPTIMIZATION_MODE` | Ranking mode, such as `economic`, `balanced`, or `minimal_detour`. |
| `ROUTE_DETOUR_FACTOR` | Multiplier used by Haversine fallback route estimates. |
| `SAME_PLACE_THRESHOLD_KM` | Distance threshold for treating origin/destination as local search. |
| `MAX_BRANDS_PER_REQUEST` | Limit for selected brand filters. |
| `CORS_ORIGINS` | Optional comma-separated allowed frontend origins. |
| `ALERT_WEBHOOK_URL` | Optional webhook for backend failure alerts. |
| `GMAIL_USER` | Optional SMTP sender for feedback messages. |
| `GMAIL_APP_PASSWORD` | Optional SMTP app password for feedback messages. |
| `FEEDBACK_RECIPIENT` | Optional feedback recipient address. |
| `FUELOPT_PROJECT_ROOT` | Optional explicit project root for packaged/runtime flows. |
| `FUELOPT_ALLOW_LAN` | Optional launcher setting for LAN exposure. |
| `BALLENOIL_MAX_WORKERS` | Optional legacy scraper concurrency setting. |

## Running Locally

Run through the compatibility entrypoint:

```bash
python main.py --reload
```

Or run FastAPI directly:

```bash
uvicorn app.api.main:app --reload
```

Then open:

- Frontend: `http://127.0.0.1:8000/`
- API docs: `http://127.0.0.1:8000/docs`
- Health: `http://127.0.0.1:8000/health`
- Catalogue status: `http://127.0.0.1:8000/catalog/status`
- Price status: `http://127.0.0.1:8000/prices/status`

## Refreshing The Price Catalogue

FuelOpt includes catalogue refresh scripts. The main refresh flow stages a candidate SQLite database, validates it, and swaps it into place only if validation passes.

```bash
python scripts/refresh_catalog.py --source auto
```

Useful options:

```bash
python scripts/refresh_catalog.py --source minetur
python scripts/refresh_catalog.py --source snapshot
python scripts/refresh_catalog.py --write-report data/reports/catalog_refresh_report.json
```

The API also exposes `POST /catalog/refresh`, guarded by an in-process lock. Use it carefully in local or controlled environments.

The current active catalogue is stored in `data/db/gas_stations.sqlite`. Source freshness/status is reported by the `/catalog/status` and `/prices/status` endpoints. Data freshness depends on upstream source availability and the last successful refresh.

## Checks

Lightweight checks available in this repository include:

```bash
python -m compileall app scripts tests main.py fuelopt_launcher.py
python tests/sanity_check.py
python tests/frontend_static_check.py
python tests/refresh_policy_check.py
python tests/web_pipeline_check.py
```

Some checks may depend on the local catalogue files being present.

## Known Limitations

- Prototype/demo status: the project is not production-ready unless hardened and operated with proper monitoring.
- Fuel data freshness depends on source availability, cache state, and successful refresh runs.
- Route estimates may use Haversine approximations unless OpenRouteService is configured and requested.
- Detour cost is an estimate based on configured consumption and route assumptions.
- Public deployment requires careful API key handling, CORS review, rate limiting, logging review, and catalogue refresh operations.
- The included SQLite catalogue is a convenient local artifact, not a substitute for a managed production data pipeline.

## Security Notes

- Do not expose OpenRouteService, SMTP, webhook, or deployment keys in frontend code.
- Do not commit `.env` or any local credentials.
- Keep real secrets in local environment files or a deployment secret manager.
- Be careful with public deployments: review CORS, rate limits, logs, feedback SMTP settings, and any catalogue refresh endpoint exposure.
- Do not commit private dumps, generated backup databases, local cache folders, or runtime reports.

## Roadmap

- Add stronger automated test coverage for optimizer edge cases and catalogue validation.
- Add a managed scheduled refresh workflow with alerting and retention policy.
- Improve ORS/Haversine fallback transparency in the UI.
- Add richer fuel type support and clearer station data provenance.
- Add deployment hardening documentation and production configuration examples.
- Add optional CI checks for Python compilation, static frontend checks, and secret scanning.

## License

License not specified yet.
