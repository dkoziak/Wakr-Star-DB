# Testing Architecture & End-to-End Data Pipeline

## Overview

The analytics pipeline has three stages. Each stage reads from the previous one.

| Component | Where | URL |
|-----------|-------|-----|
| Directus CMS | Cloud (`api.gowakr.com`) | `https://api.gowakr.com/` |
| PostgreSQL (`wakr_stardb`) | Local Docker or RDS | `localhost:5433` (local) |
| cms_etl (Dagster) | Local venv or EC2 | `http://localhost:3000` (UI) |
| Wakr-Star-DB API | Local venv or EC2 | `http://localhost:8001` (local) |

The scraper writes boat inventory to the **remote** Directus. The ETL pulls from Directus and loads directly into `wakr_stardb`. The Star DB API reads from `wakr_stardb` to serve analytics endpoints.

---

## Data Flow

```
Dealer websites
    ↓  [wakr-scrapper — daily, sets sold_at on delist]
Remote Directus (api.gowakr.com)
    → collection: dealership_inventories
    ↓  [cms_etl: directus_to_stardb_job — daily 02:00 UTC]
wakr_stardb PostgreSQL
    → dim_manufacturer, dim_boat_model, dim_geography, dim_date
    → mart_daily_snapshot
    → mart_pricing_trends
    → mart_regional_summary
    → fact_estimated_sale
    ↓  [Wakr-Star-DB API]
REST endpoints
    → /api/v1/inventory/*
    → /api/v1/pricing/*
    → /api/v1/regional/*
```

---

## Step 1 — Start Local Star DB PostgreSQL

The Star DB API and Dagster ETL both need a local PostgreSQL with the `wakr_stardb` database. Start it via Docker Compose:

```bash
cd ~/Docs/Wakr
docker compose -f docker-compose.local.yml up -d
```

This starts:
- **PostgreSQL** on port 5433 — `wakr_stardb` database
- **PostgreSQL** on port 5434 — `dagster_cms` database (Dagster state)

Verify:
```bash
psql -h 127.0.0.1 -p 5433 -U postgres -d wakr_stardb -c "SELECT 1"
```

---

## Step 2 — Run the Scraper → Directus (optional)

Only needed if you want to refresh inventory data from dealer websites. The scraper reads dealer URLs from `wakr-scrapper/config/Master Dealership List - MASTER.csv`, scrapes boat inventory, and writes to the remote Directus `dealership_inventories` collection.

```bash
cd ~/Docs/Wakr/wakr-scrapper
pip install -e .
playwright install chromium

# Test run — 2 dealers only
python src/parser/parse_dealers_from_config.py --limit 2 --verbose

# Full daily run (1/7 of dealers based on weekday)
python src/parser/parse_dealers_from_config.py --daily --verbose
```

**Key env vars** (`wakr-scrapper/.env`):
```
DIRECTUS_API_URL=https://api.gowakr.com/
DIRECTUS_EMAIL=scrapper@wakr.co
DIRECTUS_PASSWORD=<password>
DIRECTUS_INVENTORY_COLLECTION=dealership_inventories
```

> `DIRECTUS_INVENTORY_COLLECTION` controls which Directus collection the scraper reads and writes. It must match what the ETL uses.

---

## Step 3 — ETL: Directus → Star DB

The ETL (`wakeco-backend/cms_etl`) is a Dagster pipeline with a single job `directus_to_stardb_job` that pulls from Directus and loads all dimension, fact, and mart tables directly into `wakr_stardb`.

```bash
cd ~/Docs/Wakr/wakeco-backend/cms_etl
pip install -e .

# Launch Dagster UI
DAGSTER_HOME=$(pwd) dagster dev -m cms_etl.definitions
# Open http://localhost:3000 → Jobs → directus_to_stardb_job → Materialize All
```

Or run headlessly:
```bash
cd ~/Docs/Wakr/wakeco-backend/cms_etl
DAGSTER_HOME=$(pwd) python -c "
from cms_etl.definitions import defs
result = defs.get_job('directus_to_stardb_job').execute_in_process()
print('Success:', result.success)
"
```

**Key env vars** (`wakeco-backend/cms_etl/.env`):
```
DIRECTUS_API_URL=https://api.gowakr.com/
DIRECTUS_EMAIL=etl-service@wakr.co
DIRECTUS_PASSWORD=<password>
DIRECTUS_INVENTORY_COLLECTION=dealership_inventories
STARDB_URL=postgresql+psycopg2://postgres:postgres@127.0.0.1:5433/wakr_stardb
DAGSTER_POSTGRES_URL=postgresql://postgres:postgres@127.0.0.1:5434/dagster_cms
DAGSTER_HOME=/path/to/wakeco-backend/cms_etl
BATCH_SIZE=500
```

Verify load:
```bash
psql -h 127.0.0.1 -p 5433 -U postgres -d wakr_stardb \
  -c "SELECT COUNT(*) FROM mart_daily_snapshot"
```

---

## Step 4 — Start Wakr-Star-DB API

The Star DB reads from `wakr_stardb` and serves the analytics endpoints.

```bash
cd ~/Docs/Wakr/Wakr-Star-DB/src
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8001 --reload
```

Set `DEBUG=true` in `Wakr-Star-DB/src/.env` for local development — this bypasses JWT validation:

```env
STARDB_URL=postgresql+asyncpg://postgres:postgres@127.0.0.1:5433/wakr_stardb
DEBUG=true
```

Verify:
```bash
curl -H "Authorization: Bearer test" \
  "http://localhost:8001/api/v1/inventory/summary?time_range=trailing_30"

curl -H "Authorization: Bearer test" \
  "http://localhost:8001/api/v1/pricing/summary?time_range=trailing_30"

curl -H "Authorization: Bearer test" \
  "http://localhost:8001/api/v1/regional/summary?time_range=trailing_30"
```

---

## All Available Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/inventory/summary` | Active listings, avg DOM, price stats |
| GET | `/api/v1/inventory/trends` | Listing count trends over time |
| GET | `/api/v1/inventory/velocity` | DOM velocity by model |
| GET | `/api/v1/pricing/summary` | Price distribution and band breakdown |
| GET | `/api/v1/pricing/trends` | MoM price movement |
| GET | `/api/v1/pricing/model-efficiency` | Price vs DOM efficiency by model |
| GET | `/api/v1/pricing/dom-by-price-tier` | DOM distribution by price band |
| GET | `/api/v1/regional/summary` | State-level market comparison |
| GET | `/api/v1/regional/state-overview` | Per-state stats |
| GET | `/api/v1/regional/market-leaders` | Top models by state |

All endpoints require `Authorization: Bearer <token>`. With `DEBUG=true` locally, any token works.

---

## Running Tests

### Unit tests (no Docker required)
```bash
# Scraper
cd ~/Docs/Wakr/wakr-scrapper
python -m pytest src/tests/ -v

# ETL
cd ~/Docs/Wakr/wakeco-backend/cms_etl
python -m pytest tests/ -v

# Star DB API
cd ~/Docs/Wakr/Wakr-Star-DB/src
python -m pytest tests/ -v
```

### Export a Directus collection to CSV
```bash
# Uses remote Directus (DIRECTUS_API_URL in env)
python tests/directus_export.py dealership_inventories
python tests/directus_export.py dealers
python tests/directus_export.py boats_models
```

---

## Credential Reference

| Secret | File | Note |
|--------|------|------|
| Directus scraper account | `wakr-scrapper/.env` | `scrapper@wakr.co` |
| Directus ETL account | `wakeco-backend/cms_etl/.env` | `etl-service@wakr.co` |
| Local Postgres | `docker-compose.local.yml` | `postgres/postgres` |
| Google geocoding | `wakr-scrapper/.env` | `GOOGLE_API_KEY` |
| OpenAI (scraper LLM) | `wakr-scrapper/.env` | `OPENAI_API_KEY` |

---

## Troubleshooting

**`relation "mart_daily_snapshot" does not exist`** — Run `Wakr-Star-DB/src/db/init_stardb.sql` against `wakr_stardb` to initialise the schema before running the ETL.

**ETL job logs `0 active listings`** — Confirm `DIRECTUS_INVENTORY_COLLECTION=dealership_inventories` in `cms_etl/.env` and that the scraper has run against the same collection.

**`fact_estimated_sale` inserts 0 rows** — Normal on first run if `sold_at` is not yet populated on any delisted records. Run `wakr-scrapper/src/scripts/seed_sold_at.py` to backfill.

**Star DB API returns 404 `NO_DATA`** — The ETL has not run yet, or `mart_daily_snapshot` is empty. Trigger `directus_to_stardb_job` from the Dagster UI.

**Dagster 400 errors on Directus filter** — Confirm `sold_at` and `estimated_sale_price` fields exist on `dealership_inventories` in Directus. Add them via the Directus admin UI if missing (both nullable; `sold_at` is timestamp, `estimated_sale_price` is decimal 10,2).

**`DEBUG=true` in production** — Never set on any internet-facing instance. It bypasses all JWT authentication.
