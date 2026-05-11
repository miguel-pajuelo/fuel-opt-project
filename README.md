# ⛽ Fuel Route Optimizer

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![SQLite](https://img.shields.io/badge/SQLite-003B57?style=flat&logo=sqlite&logoColor=white)](https://sqlite.org)

REST API that scrapes real-time fuel prices from official Spanish sources and computes the most cost-efficient driving route between two points, factoring in detour cost, fuel savings and consumption.

---

## 🧠 How it works

Most route optimizers only minimize distance or time. This one minimizes **total trip cost**: it finds the fuel station where stopping actually saves you money after accounting for the detour.

1. User provides origin, destination, fuel type and consumption
2. API scrapes live prices from MINETUR (official Spanish registry) and Ballenoil
3. Candidate stations are filtered by corridor and radius around the route
4. Each candidate is scored: `savings = price_diff × liters - detour_cost`
5. The optimal station and full route breakdown are returned

---

## 🏗️ Architecture
app/
├── api/
│   ├── main.py              # FastAPI endpoints
│   └── ui.py                # Embedded web frontend
├── data_sources/
│   ├── minetur.py           # Official MINETUR API scraping
│   ├── ballenoil.py         # Ballenoil price scraping
│   └── adapters.py          # Unified data adapters
├── optimizer/
│   └── ranking.py           # Haversine + multi-criteria ranking
├── routing/
│   └── ors.py               # OpenRouteService geocoding
└── storage/
└── database.py          # SQLite persistence

---

## ⚙️ Stack

- **FastAPI + Pydantic** — REST API with automatic validation and docs
- **Scraping** — MINETUR (official registry) + Ballenoil
- **Optimization** — Haversine distance + multi-criteria economic ranking
- **Geocoding** — OpenRouteService (ORS)
- **Storage** — SQLite with automatic refresh

---

## 🚀 Setup

```bash
git clone https://github.com/miguel-pajuelo/fuel-route-optimizer
cd fuel-route-optimizer
cp .env.example .env        # add your ORS API key
pip install -r requirements-web.txt
uvicorn app.api.main:app --reload
```

API docs available at `http://localhost:8000/docs` once running.

---

## 📡 Main endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/optimize` | Returns optimal fuel stop and route breakdown |
| `GET` | `/stations` | Lists all stations with live prices |
| `GET` | `/health` | Database and data freshness status |
| `GET` | `/brands` | Available fuel brand catalog |

---

## 📦 Key features

- **Multi-source scraping** — combines official government data with private station prices
- **Economic ranking** — accounts for detour distance, not just raw price
- **Corridor search** — only considers stations that make sense geographically
- **Configurable** — fuel type, consumption, search radius, max candidates all adjustable
- **Embedded UI** — lightweight frontend served directly from the API
