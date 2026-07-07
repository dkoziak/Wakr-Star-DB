# Feature: Sold Boat Metrics — Installation & Operations Guide

Tickets WAK-45 through WAK-49. Tracks when boats disappear from dealer listings, infers sale events, exposes aggregate sold-market metrics via the Directus reporting API, and loads inferred sales into the Star DB data lake for analytics.

---

## Current Production Status (as of 2026-07)

| Step | Status | Notes |
|------|--------|-------|
| `sold_at` / `estimated_sale_price` added to Directus `dealership_inventories` | ✅ Done | Added via Directus API |
| Scraper updated to write `sold_at` / `estimated_sale_price` on delist | ✅ Done | Deployed 2026-07-04 |
| cms_etl updated to read from `dealership_inventories` (env var) | ✅ Done | WAK-71 |
| `fact_estimated_sale` Dagster asset deployed | ✅ Done | Runs daily 02:00 UTC |
| Historical backfill (`seed_sold_at.py`) | ⏳ Pending | Run once to populate `sold_at` on pre-existing delisted records |

---

## Overview

Dealers don't publish sold dates. When a listing vanishes, it may mean the boat sold, was re-listed elsewhere, or was simply withdrawn. This feature uses listing disappearance as a proxy for sale.

**What changed across the repos:**

| Repo | Change |
|---|---|
| `wakr-scrapper` | Scraper sets `sold_at` (first missed scrape) and `estimated_sale_price` (last price × 0.93) when a boat is delisted |
| `wakr-directus-extensions` | `GET /reporting/sold-metrics` endpoint aggregates sold data from Directus |
| `wakeco-backend` (`cms_etl`) | `fact_estimated_sale` Dagster asset incrementally loads inferred sale events from Directus into Star DB; all assets now use `DIRECTUS_INVENTORY_COLLECTION` env var |
| `Wakr-Star-DB` | Reads `fact_estimated_sale` to power inventory and analytics endpoints |

**Data flow:**

```
Dealer websites
    ↓  [wakr-scrapper — sets sold_at, estimated_sale_price on delist]
Directus (dealership_inventories)
    ├─►  [wakr-directus-extensions] → GET /reporting/sold-metrics  (real-time aggregate)
    └─►  [cms_etl: fact_estimated_sale — daily at 02:00 UTC]
              ↓
         Star DB (fact_estimated_sale table)
              ↓
         [Wakr-Star-DB API] → /api/v1/inventory/*, /api/v1/pricing/*, /api/v1/regional/*
```

---

## Market Assumptions

| Constant | Default | Override | Meaning |
|---|---|---|---|
| `SOLD_RATE` | `0.67` | `SOLD_RATE` env var | ~67% of delisted boats are estimated to have actually sold |
| `LIST_TO_SALE_RATIO` | `0.93` | `LIST_TO_SALE_RATIO` env var | Sale price ≈ 93% of last listed price |
| `GRACE_PERIOD_MISSES` | `3` | code constant | Consecutive missed scrapes before a boat is marked delisted |

`SOLD_RATE` is applied at query time (not stored per-boat). `LIST_TO_SALE_RATIO` is applied once at delist time and stored as `estimated_sale_price`.

---

## Installation — Ordered by Dependency

### Step 1 — Directus Schema

**Status: ✅ Complete in production.**

Two nullable columns on `dealership_inventories`:

| Field | Type | Nullable | Notes |
|---|---|---|---|
| `sold_at` | Timestamp | Yes | Set on first missed scrape |
| `estimated_sale_price` | Decimal (10,2) | Yes | `last_price × LIST_TO_SALE_RATIO`, set when delisting |

To verify these exist:

```bash
cd ~/Docs/Wakr/wakr-scrapper
.venv/bin/python src/scripts/verify_history_schema.py
```

To add them to a new Directus instance, use the Directus admin UI or the `migrate_directus_fields.py` script:

```bash
cd ~/Docs/Wakr/wakr-scrapper
.venv/bin/python src/scripts/migrate_directus_fields.py
```

---

### Step 2 — Deploy `wakr-directus-extensions`

The `GET /reporting/sold-metrics` endpoint reads `sold_at` and `estimated_sale_price` from Directus.

```bash
cd ~/Docs/Wakr/wakr-directus-extensions
npm install
npm run build
```

Restart Directus to load the compiled extensions.

**Collection name:** The endpoint reads from the collection named in `endpoints/filter-locals/src/constants.js`. This file contains hardcoded collection references (`dealership_inventories`). If you need to change the collection, edit it and rebuild.

**Verify the endpoint is live:**

```bash
curl "https://api.gowakr.com/reporting/sold-metrics" \
  -H "Authorization: Bearer <directus_token>"
```

Expected response shape:

```json
{
  "delisted_count": 142,
  "estimated_sold_count": 95,
  "avg_days_on_market": 47,
  "avg_estimated_sale_price": 62400,
  "sold_rate_used": 0.67
}
```

Optional query parameters: `make`, `model`, `from_date` (ISO 8601), `to_date` (ISO 8601), `sold_rate` (float 0–1).

---

### Step 3 — Deploy `wakr-scrapper`

**Status: ✅ Deployed on EC2 63.176.137.216 (2026-07-04).**

The scraper sets `sold_at` and `estimated_sale_price` whenever a boat transitions to delisted.

```bash
cd ~/Docs/Wakr/wakr-scrapper
make install
playwright install chromium
```

**Key env vars** (`wakr-scrapper/.env`):

```env
DIRECTUS_API_URL=https://api.gowakr.com/
DIRECTUS_EMAIL=scrapper@wakr.co
DIRECTUS_PASSWORD=<password>
DIRECTUS_INVENTORY_COLLECTION=dealership_inventories
SOLD_RATE=0.67                  # optional override
LIST_TO_SALE_RATIO=0.93         # optional override
```

> Note: The env var is `DIRECTUS_INVENTORY_COLLECTION`, not the older `DIRECTUS_OUTPUT_COLLECTION`.

---

### Step 4 — Backfill existing data (one-time, required)

**Status: ⏳ Pending.**

For boats that were already delisted before this feature shipped, `sold_at` and `estimated_sale_price` will be null. The backfill script populates them using `status_changed_at` as a proxy for `sold_at`.

```bash
cd ~/Docs/Wakr/wakr-scrapper

# Preview changes without writing
.venv/bin/python src/scripts/seed_sold_at.py --dry-run

# Apply
.venv/bin/python src/scripts/seed_sold_at.py
```

Only touches boats where `sold_at IS NULL`. Safe to re-run.

---

### Step 5 — Deploy `cms_etl` (`wakeco-backend`)

**Status: ✅ Deployed on EC2 3.120.235.122.**

The `fact_estimated_sale` Dagster asset loads inferred sale events from Directus into the Star DB on a daily schedule. All ETL assets use `DIRECTUS_INVENTORY_COLLECTION` to determine which Directus collection to read from.

**Key env vars** (`wakeco-backend/cms_etl/.env`):

```env
DIRECTUS_API_URL=https://api.gowakr.com/
DIRECTUS_EMAIL=etl-service@wakr.co
DIRECTUS_PASSWORD=<password>
DIRECTUS_INVENTORY_COLLECTION=dealership_inventories
STARDB_URL=postgresql+psycopg2://stardb:secret@<rds-host>:5432/wakr_stardb
DAGSTER_POSTGRES_URL=postgresql://dagster:secret@<rds-host>:5432/dagster_cms
DAGSTER_HOME=/opt/wakr/cms_etl
```

**One-off run to verify:**

```bash
cd ~/Docs/Wakr/wakeco-backend/cms_etl
DAGSTER_HOME=$(pwd) python -c "
from cms_etl.definitions import defs
result = defs.get_job('directus_to_stardb_job').execute_in_process()
print('Success:', result.success)
"
```

---

### Step 6 — Deploy `Wakr-Star-DB`

**Status: ✅ Deployed on EC2 18.194.202.20.**

The Star DB API reads from `fact_estimated_sale` to serve inventory and analytics endpoints.

```bash
cd ~/Docs/Wakr/Wakr-Star-DB
python3 -m venv .venv
source .venv/bin/activate
pip install -r src/requirements.txt
```

**`src/.env`:**

```env
STARDB_URL=postgresql+asyncpg://stardb:secret@<rds-host>:5432/wakr_stardb
TOKEN_ISSUER=https://wakr.us.auth0.com/
TOKEN_AUDIENCE=https://api.wakr.co
JWT_PUBLIC_KEY=-----BEGIN PUBLIC KEY-----
...
-----END PUBLIC KEY-----
```

---

## Daemon Setup

### Dagster ETL — `directus_to_stardb_job`

The `fact_estimated_sale` asset (and all other Star DB assets) run daily at **02:00 UTC** on EC2 `wakr-etl` (3.120.235.122).

#### Local development

```bash
cd ~/Docs/Wakr/wakeco-backend/cms_etl
DAGSTER_HOME=$(pwd) dagster dev -m cms_etl.definitions
# Dagster UI at http://localhost:3000
```

#### Production

Two systemd services on `wakr-etl`:

```bash
sudo systemctl status dagster-daemon     # schedule runner
sudo systemctl status dagster-webserver  # UI at port 3000
```

Restart both:
```bash
sudo systemctl restart dagster-daemon dagster-webserver
```

---

## Verification Checklist

After setup or re-deployment:

- [ ] `sold_at` and `estimated_sale_price` columns exist on `dealership_inventories` in Directus
- [ ] `verify_history_schema.py` — all green
- [ ] Scraper run produces at least one delisted boat with `sold_at` set
- [ ] `GET /reporting/sold-metrics` returns valid JSON with non-null counts
- [ ] Dagster ETL run completes without errors; rows appear in `fact_estimated_sale`
- [ ] `GET /api/v1/inventory/summary?time_range=trailing_30` returns `boats_sold > 0`

---

## Unit Tests

**wakr-scrapper:**
```bash
cd ~/Docs/Wakr/wakr-scrapper
.venv/bin/python -m pytest src/tests/ -v
```

Covers: `sold_at` set on first miss, not overwritten on subsequent misses, `estimated_sale_price` computed at delist, null/missing price handling, integer rounding, custom ratio override.

**Wakr-Star-DB:**
```bash
cd ~/Docs/Wakr/Wakr-Star-DB/src
python3 -m pytest tests/ -v
```

---

## Troubleshooting

**`sold_at` is null on delisted boats** — Either the backfill hasn't run, or the scraper ran before the schema columns were added. Run `seed_sold_at.py`.

**`/reporting/sold-metrics` returns `delisted_count: 0`** — Confirm `dealership_inventories` is the correct collection and that `sold_at IS NOT NULL` records exist. Check the hardcoded collection name in `wakr-directus-extensions/endpoints/filter-locals/src/constants.js`.

**Dagster ETL inserts 0 rows into `fact_estimated_sale`** — The high-water mark (`MAX(date_key)`) may be ahead of the available data. Verify `sold_at` is populated in Directus. On first run from an empty table, all matching records are loaded.

**Star DB API returns 404 `NO_DATA`** — Trigger `directus_to_stardb_job` manually from the Dagster UI at `http://3.120.235.122:3000`.

**Dagster 400 errors on `sold_at` filter** — The `sold_at` field doesn't exist on `dealership_inventories` in Directus. Add it via the admin UI (timestamp, nullable).
