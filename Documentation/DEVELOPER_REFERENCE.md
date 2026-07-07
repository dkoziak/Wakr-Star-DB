# Wakr Analytics — Developer Reference Guide

**Last updated:** 2026-07-07  
**Audience:** New developers taking over maintenance of the analytics pipeline

---

## Related Documentation

| Document | Location | What it covers |
|----------|----------|----------------|
| [Testing Architecture & End-to-End Pipeline](README_TEST.md) | `~/Docs/Wakr/README_TEST.md` | How to run the full pipeline locally: starting the Star DB, running the scraper, triggering the ETL, starting the API, and verifying each step. Use this when setting up a local dev environment or debugging the pipeline end-to-end. |
| [Sold Boat Metrics — Installation & Operations](README_feat_sold_boat_metrics.md) | `~/Docs/Wakr/README_feat_sold_boat_metrics.md` | Deep-dive on the sold boat metrics feature (WAK-45–49): how `sold_at` and `estimated_sale_price` are set, the `fact_estimated_sale` ETL asset, the one-time backfill script, and the Directus `/reporting/sold-metrics` endpoint. Includes current production status and verification checklist. |
| [AWS Deployment Plan](IMPLEMENTATION_AWS.md) | `~/Docs/Wakr/IMPLEMENTATION_AWS.md` | Step-by-step instructions for provisioning the full AWS environment from scratch: VPC, RDS, SSM secrets, EC2 instances, systemd services, Directus bootstrap, and smoke tests. Reference this when standing up a new environment or onboarding a new AWS account. |
| [Data Architecture Reference](Wakr-Star-DB/Documentation/wakr_data_architecture.md) | `~/Docs/Wakr/Wakr-Star-DB/Documentation/wakr_data_architecture.md` | Star schema design for `wakr_stardb`: all dimension, fact, bridge, and mart table definitions with column-level detail. Distinguishes between tables that are **live** (implemented and populated by ETL) and **planned** (designed but not yet built). |

---

## Repository Map

| Repo | Language | Role |
|------|----------|------|
| `wakr-scrapper` | Python 3.11, Playwright | Scrapes dealer websites; writes to Directus |
| `wakeco-backend/cms_etl` | Python 3.12, Dagster | ETL: Directus → Star DB |
| `Wakr-Star-DB` | Python 3.11, FastAPI | REST API serving analytics from Star DB |
| `wakr-directus-extensions` | TypeScript / Node 18 | Custom Directus endpoints and hooks |

---

## Production Machines

| Machine | IP | Instance Type | SSH Key | Purpose |
|---------|-----|--------------|---------|---------|
| `wakr-etl` | 3.120.235.122 | t3.small | `wakr-test.pem` or `matviikey.pem` | Runs Dagster ETL pipeline (cms_etl). Transforms Directus data into the Star DB star schema. Fires daily at 02:00 UTC. |
| `wakr-scrapper` | 63.176.137.216 | t3.medium | `wakr-test.pem` or `matviikey.pem` | Runs the Playwright scraper as a Docker container. Visits dealer websites, writes inventory to Directus. Fires daily at 06:00 UTC via systemd timer. |
| `wakr-api` | 18.194.202.20 | t2.micro | `wakr-test.pem` or `matviikey.pem` | Runs the FastAPI analytics API (Wakr-Star-DB). Serves the 10 analytics endpoints on port 8000. Always-on service. |
| Directus CMS | api.gowakr.com | — (cloud) | — | Source of truth for boat inventory. Not an EC2 — cloud-hosted. Scraper writes here; ETL reads from here. |
| RDS PostgreSQL | internal DNS | db.t3.micro | — | Hosts `wakr_stardb` (analytics warehouse) and `dagster_cms` (Dagster state). Not directly SSH-accessible — connect via psql from any EC2. |

### Services on each machine

**`wakr-etl` (3.120.235.122)**
```bash
sudo systemctl status dagster-daemon      # runs ETL schedules — critical
sudo systemctl status dagster-webserver   # UI at http://3.120.235.122:3000
```

**`wakr-scrapper` (63.176.137.216)**
```bash
sudo systemctl status wakr-scrapper.timer    # daily trigger at 06:00 UTC
sudo systemctl status wakr-scrapper.service  # the actual scrape run (oneshot)
sudo docker images                           # wakr-scraper:latest
```

**`wakr-api` (18.194.202.20)**
```bash
sudo systemctl status wakr-stardb-api   # uvicorn, port 8000
```

---

## Deploying Changes to Each Machine

### How deployment works

None of the EC2 instances are git repositories. Code is deployed by copying files from your local machine. Each machine has a different deploy pattern depending on what it runs.

---

### `wakr-api` — FastAPI (Wakr-Star-DB)

The API is a Python venv running under systemd. Deploy by SCP'ing changed files and restarting the service.

```bash
# Copy changed file(s)
scp -i ~/.ssh/wakr-test.pem \
  ~/Docs/Wakr/Wakr-Star-DB/src/routers/inventory.py \
  ec2-user@18.194.202.20:/tmp/

# SSH in and install
ssh -i ~/.ssh/wakr-test.pem ec2-user@18.194.202.20
sudo cp /tmp/inventory.py /opt/wakr/Wakr-Star-DB/src/routers/inventory.py
sudo chown wakr-api:wakr-api /opt/wakr/Wakr-Star-DB/src/routers/inventory.py
sudo systemctl restart wakr-stardb-api
sudo systemctl status wakr-stardb-api --no-pager
sudo journalctl -u wakr-stardb-api -n 30 --no-pager
```

For changes to `requirements.txt`:
```bash
sudo /opt/wakr/Wakr-Star-DB/.venv/bin/pip install -r /opt/wakr/Wakr-Star-DB/src/requirements.txt
sudo systemctl restart wakr-stardb-api
```

---

### `wakr-etl` — Dagster (cms_etl)

The ETL is a Python venv running under systemd. SCP changed files, fix ownership, restart both Dagster services.

```bash
# Copy changed file(s) — example: updating an ETL asset
scp -i ~/.ssh/wakr-test.pem \
  ~/Docs/Wakr/wakeco-backend/cms_etl/cms_etl/assets/directus_to_stardb/mart_daily_snapshot.py \
  ec2-user@3.120.235.122:/tmp/

ssh -i ~/.ssh/wakr-test.pem ec2-user@3.120.235.122
sudo cp /tmp/mart_daily_snapshot.py \
  /opt/wakr/cms_etl/assets/directus_to_stardb/mart_daily_snapshot.py
sudo chown dagster:dagster \
  /opt/wakr/cms_etl/assets/directus_to_stardb/mart_daily_snapshot.py
sudo systemctl restart dagster-daemon dagster-webserver
sudo systemctl status dagster-daemon dagster-webserver --no-pager
```

The deploy path mirrors the repo: `wakeco-backend/cms_etl/cms_etl/` on disk becomes `/opt/wakr/cms_etl/` on the instance.

For changes to `pyproject.toml` / new dependencies:
```bash
sudo /opt/wakr/cms_etl/.venv/bin/pip install -e /opt/wakr/cms_etl
sudo systemctl restart dagster-daemon dagster-webserver
```

---

### `wakr-scrapper` — Playwright scraper (Docker)

The scraper runs as a Docker image. Any code change requires rebuilding the image. The instance is **not** a git repo, so deploy via `git archive` + SCP.

```bash
# 1. On your local machine — archive current main
cd ~/Docs/Wakr/wakr-scrapper
git archive --format=tar.gz HEAD -o /tmp/wakr-scrapper-latest.tar.gz

# 2. Copy to instance
scp -i ~/.ssh/wakr-test.pem \
  /tmp/wakr-scrapper-latest.tar.gz \
  ec2-user@63.176.137.216:/tmp/

# 3. SSH in and deploy
ssh -i ~/.ssh/wakr-test.pem ec2-user@63.176.137.216

# Stop the timer so no scrape fires mid-deploy
sudo systemctl stop wakr-scrapper.timer wakr-scrapper.service 2>/dev/null || true

# Preserve the .env (contains secrets not in the archive)
sudo cp /opt/wakr/scrapper/.env /tmp/scrapper.env.bak

# Replace source files
sudo rm -rf /opt/wakr/scrapper
sudo mkdir -p /opt/wakr/scrapper
sudo tar -xzf /tmp/wakr-scrapper-latest.tar.gz -C /opt/wakr/scrapper
sudo cp /tmp/scrapper.env.bak /opt/wakr/scrapper/.env
sudo chmod 600 /opt/wakr/scrapper/.env

# Rebuild Docker image (takes ~3 minutes — downloads Playwright/Chromium)
sudo docker build -t wakr-scraper:latest /opt/wakr/scrapper

# Re-enable timer
sudo systemctl start wakr-scrapper.timer
sudo systemctl list-timers wakr-scrapper.timer --no-pager
```

To test the new image immediately without waiting for the timer:
```bash
sudo systemctl start wakr-scrapper.service
sudo journalctl -u wakr-scrapper -f
```

---

### Directus extensions (`wakr-directus-extensions`)

Extensions are deployed to the cloud Directus at `api.gowakr.com`. Build locally and copy the compiled output to the Directus extensions directory, then restart Directus.

```bash
cd ~/Docs/Wakr/wakr-directus-extensions
npm install
npm run build   # compiles TypeScript → dist/index.js in each extension dir
```

Deployment depends on how the cloud Directus is managed — contact the Directus admin for the deploy process.

---

## End-to-End Analytics Workflow

```
┌──────────────────┐
│  Dealer Websites │
└────────┬─────────┘
         │  Playwright (headless Chromium)
         ▼
┌──────────────────────────────────────────────┐
│  wakr-scrapper                               │
│  EC2 63.176.137.216 — Docker, daily 06:00 UTC│
│                                              │
│  Reads:  config/Master Dealership List.csv   │
│  Writes: Directus dealership_inventories     │
│  Sets:   sold_at on first missed scrape      │
│          estimated_sale_price = price × 0.93 │
└────────┬─────────────────────────────────────┘
         │  Directus REST API (api.gowakr.com)
         ▼
┌──────────────────────────────────────────────┐
│  Directus CMS (cloud: api.gowakr.com)        │
│                                              │
│  Source collection: dealership_inventories   │
│  Key fields: brand_id, model_id, condition,  │
│    price, locations, first_seen_at, sold_at, │
│    estimated_sale_price, status              │
└────────┬─────────────────────────────────────┘
         │  Directus REST API (pagination, filters)
         ▼
┌──────────────────────────────────────────────┐
│  wakeco-backend/cms_etl (Dagster)            │
│  EC2 3.120.235.122 — daily 02:00 UTC         │
│                                              │
│  Job: directus_to_stardb_job                 │
│  Assets (run in dependency order):           │
│    dim_manufacturer  ← Directus brands       │
│    dim_boat_model    ← Directus boats_models │
│    dim_geography     ← unique states         │
│    dim_date          ← static date spine     │
│    mart_daily_snapshot ← active inventory    │
│    fact_estimated_sale ← delisted w/sold_at  │
│    mart_pricing_trends ← aggregates snapshot │
│    mart_regional_summary ← aggregates snapshot│
└────────┬─────────────────────────────────────┘
         │  psycopg2 (SQLAlchemy Core)
         ▼
┌──────────────────────────────────────────────┐
│  wakr_stardb (RDS PostgreSQL)                │
│  Star schema — analytics warehouse           │
└────────┬─────────────────────────────────────┘
         │  asyncpg (SQLAlchemy Core)
         ▼
┌──────────────────────────────────────────────┐
│  Wakr-Star-DB (FastAPI)                      │
│  EC2 18.194.202.20 — port 8000               │
│                                              │
│  Routers:                                    │
│    /api/v1/inventory/*  (3 endpoints)        │
│    /api/v1/pricing/*    (4 endpoints)        │
│    /api/v1/regional/*   (3 endpoints)        │
│                                              │
│  Auth: JWT Bearer (Auth0) — or DEBUG=true    │
└──────────────────────────────────────────────┘
```

---

## Key Environment Variables

### `wakr-scrapper/.env` (on EC2 at `/opt/wakr/scrapper/.env`)
```env
DIRECTUS_API_URL=https://api.gowakr.com/
DIRECTUS_EMAIL=scrapper@wakr.co
DIRECTUS_PASSWORD=<from SSM /wakr/test/DIRECTUS_SCRAPPER_PASS>
DIRECTUS_INVENTORY_COLLECTION=dealership_inventories
SOLD_RATE=0.67
LIST_TO_SALE_RATIO=0.93
```

### `wakeco-backend/cms_etl/.env` (on EC2 at `/opt/wakr/cms_etl/.env`)
```env
DIRECTUS_API_URL=https://api.gowakr.com/
DIRECTUS_EMAIL=etl-service@wakr.co
DIRECTUS_PASSWORD=<from SSM /wakr/test/DIRECTUS_ETL_PASS>
DIRECTUS_INVENTORY_COLLECTION=dealership_inventories
STARDB_URL=postgresql+psycopg2://stardb:pass@<rds-host>:5432/wakr_stardb
DAGSTER_POSTGRES_URL=postgresql://dagster:pass@<rds-host>:5432/dagster_cms
DAGSTER_HOME=/opt/wakr/cms_etl
BATCH_SIZE=500
```

### `Wakr-Star-DB/src/.env` (on EC2 at `/opt/wakr/Wakr-Star-DB/src/.env`)
```env
STARDB_URL=postgresql+asyncpg://stardb:pass@<rds-host>:5432/wakr_stardb
DEBUG=false
TOKEN_ISSUER=https://wakr.us.auth0.com/
TOKEN_AUDIENCE=https://api.wakr.co
JWT_PUBLIC_KEY=-----BEGIN PUBLIC KEY-----...
```

> `DIRECTUS_INVENTORY_COLLECTION` must be identical in both the scraper and cms_etl. Mismatch means the ETL reads from a different collection than the scraper writes to.

---

## Significant Changes Made (2026 Q2–Q3)

### WAK-71: Replace hardcoded `dealership_inventories_copy` with env var
**Repos:** `wakr-scrapper`, `wakeco-backend/cms_etl`

Previously all ETL assets and the scraper hardcoded `dealership_inventories_copy` (a staging collection). This caused the ETL to read from a table the production scraper never wrote to.

**Changes:**
- `DirectusResource` in `cms_etl/resources/directus.py` now has `inventory_collection: str`
- `definitions.py` binds it to `EnvVar("DIRECTUS_INVENTORY_COLLECTION")`
- All ETL asset files use `directus.inventory_collection` instead of a hardcoded string
- Scraper env var renamed from `DIRECTUS_OUTPUT_COLLECTION` to `DIRECTUS_INVENTORY_COLLECTION`

### WAK-45–49: Sold boat metrics
**Repos:** `wakr-scrapper`, `wakeco-backend/cms_etl`, `Wakr-Star-DB`

Adds inference of sale events from listing disappearances.

**Changes:**
- `sold_at` (timestamp, nullable) and `estimated_sale_price` (decimal 10,2, nullable) added to `dealership_inventories` in Directus
- `directus_importer.py`: sets `sold_at = now` on first missed scrape; sets `estimated_sale_price = price × 0.93` at delist
- New Dagster asset `fact_estimated_sale`: incremental load using `sold_at` as high-water mark
- `seed_sold_at.py`: backfill script for pre-existing delisted records (still needs to be run against production)

### WAK-61: CORS middleware
**Repo:** `Wakr-Star-DB`

Added `CORSMiddleware` in `src/main.py` allowing `https://intel-dashboard-mvp.pages.dev`.

### Scraper bug: `prefiltered_make` KeyError (0% scrape success)
**Repo:** `wakr-scrapper` (commit `7430c78`, deployed 2026-07-04)

Stats dict used key `prefiltered_make_or_category` but summary loop referenced old key `prefiltered_make`. Silently caught as a parse error, causing every dealer sync to be skipped. Fixed in main; production image rebuilt.

---

## Dagster Asset Dependency Graph

```
dim_manufacturer
    ↓
dim_boat_model ─────────────────────────┐
                                        │
dim_date                                │
                                        │
dim_geography                           │
    │                                   ▼
    └─────────────────► mart_daily_snapshot
                               │
                        ┌──────┴──────┐
                        ▼             ▼
             mart_pricing_trends  mart_regional_summary

dim_manufacturer + dim_boat_model + dim_date
    └─────────────────► fact_estimated_sale
```

All assets run as part of `directus_to_stardb_job` daily at **02:00 UTC**.

---

## Common Operations

### Manually trigger the full ETL
```bash
# Via Dagster UI (recommended)
# Open http://3.120.235.122:3000 → Jobs → directus_to_stardb_job → Launch Run

# Or via CLI on the ETL machine
ssh -i ~/.ssh/wakr-test.pem ec2-user@3.120.235.122
source /opt/wakr/cms_etl/.venv/bin/activate
export DAGSTER_HOME=/opt/wakr/cms_etl
dagster job execute -m cms_etl.definitions -j directus_to_stardb_job
```

### Run the scraper manually
```bash
ssh -i ~/.ssh/wakr-test.pem ec2-user@63.176.137.216
sudo systemctl start wakr-scrapper.service
sudo journalctl -u wakr-scrapper -f
```

### Run the sold_at backfill (one-time)
```bash
cd ~/Docs/Wakr/wakr-scrapper
.venv/bin/python src/scripts/seed_sold_at.py --dry-run   # preview first
.venv/bin/python src/scripts/seed_sold_at.py
```

### Restart all services after a reboot
All services are `systemctl enable`'d and start automatically on reboot. To restart manually:
```bash
# wakr-etl
sudo systemctl restart dagster-daemon dagster-webserver

# wakr-scrapper (timer only — don't restart the service directly unless you want an immediate run)
sudo systemctl restart wakr-scrapper.timer

# wakr-api
sudo systemctl restart wakr-stardb-api
```

### Disable the scraper (if running elsewhere)
```bash
ssh -i ~/.ssh/wakr-test.pem ec2-user@63.176.137.216
sudo systemctl disable --now wakr-scrapper.timer
# Re-enable later:
sudo systemctl enable --now wakr-scrapper.timer
```

---

## Open Bugs (Linear)

| Ticket | Area | Description |
|--------|------|-------------|
| WAK-67 | `mart_daily_snapshot` | `days_supply` uses single-day removal count — produces None on most days |
| WAK-68 | `mart_pricing_trends` | `avg_list_price` is unweighted average of daily averages |
| WAK-69 | `mart_pricing_trends` | `pct_listings_with_price_cut` and `discount_pressure_pct` hardcoded NULL |
| WAK-70 | `mart_regional_summary` | Uses `removed_listings` as sold proxy instead of `fact_estimated_sale` |

---

## Directus Collection Schema Reference

### `dealership_inventories` — fields used by analytics

| Field | Type | Set by |
|-------|------|--------|
| `id` | UUID | Directus |
| `status` | String | Scraper (`active` \| `delisted`) |
| `condition` | String | Scraper (`New` \| `Used`) |
| `price` | Decimal | Scraper |
| `brand_id` | FK → brands | Scraper |
| `model_id` | FK → boats_models | Scraper |
| `make` | String | Scraper |
| `locations` | JSON array | Scraper — `[{"state": "FL", ...}]` |
| `first_seen_at` | Timestamp | Scraper — date listing first appeared |
| `sold_at` | Timestamp (nullable) | Scraper — set on first missed scrape |
| `estimated_sale_price` | Decimal (nullable) | Scraper — set at delist (`price × 0.93`) |
| `consecutive_misses` | Integer | Scraper |

### `boats_models` — used by `dim_boat_model`

| Field | Type |
|-------|------|
| `id` | Integer |
| `name` | String |
| `brand_id` | FK → brands |
| `model_year` | Integer |
