# Wakr Market Intelligence API

REST API serving boat market intelligence data from the Wakr Data Lake.

- **Backend:** Python 3.11+ / FastAPI  
- **Database:** PostgreSQL 16 via SQLAlchemy Core (async)  
- **Auth:** OAuth 2.0 Bearer token (RS256 JWT)  
- **API version:** 1.6.0-draft

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Installation](#installation)
3. [Configuration](#configuration)
4. [Running in Development](#running-in-development)
5. [Running as a systemd Service (Linux)](#running-as-a-systemd-service-linux)
6. [Authentication](#authentication)
7. [API Reference](#api-reference)
   - [Inventory Tab](#inventory-tab)
   - [Pricing Tab](#pricing-tab)
   - [Regional Tab](#regional-tab)
8. [Error Responses](#error-responses)
9. [Response Envelope](#response-envelope)

---

## Prerequisites

- Python 3.11 or later
- PostgreSQL 16 with the Wakr Data Lake schema applied
- A configured OAuth 2.0 identity provider (Auth0, Cognito, etc.) — or set `DEBUG=true` to bypass token validation during development

---

## Installation

```bash
# 1. Clone / navigate to the project
cd /opt/wakr/Wakr-Star-DB

# 2. Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r src/requirements.txt
```

---

## Configuration

Copy `.env.example` to `.env` inside `src/` and fill in your values:

```bash
cp src/.env.example src/.env
```

| Variable | Description | Example |
|----------|-------------|---------|
| `DATABASE_URL` | Async PostgreSQL connection string | `postgresql+asyncpg://wakr:secret@localhost:5432/wakr` |
| `DEBUG` | `true` accepts any Bearer token — **never use in production** | `false` |
| `TOKEN_ISSUER` | JWT `iss` claim — your IdP's issuer URL | `https://wakr.us.auth0.com/` |
| `TOKEN_AUDIENCE` | JWT `aud` claim | `https://api.wakr.co` |
| `JWT_PUBLIC_KEY` | RS256 public key PEM string (single line or multiline) | `-----BEGIN PUBLIC KEY-----...` |

The application reads `.env` from the directory it is **started from**. When running as a systemd service, set `WorkingDirectory` to the `src/` folder (see below).

---

## Running in Development

```bash
cd src
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Interactive docs are available at `http://localhost:8000/docs` (Swagger UI) and `http://localhost:8000/redoc`.

---

## Running as a systemd Service (Linux)

### 1. Create a dedicated system user

```bash
sudo useradd --system --no-create-home --shell /usr/sbin/nologin wakr-api
```

### 2. Place the application files

```bash
sudo mkdir -p /opt/wakr/Wakr-Star-DB
sudo cp -r /path/to/Wakr-Star-DB /opt/wakr/
sudo chown -R wakr-api:wakr-api /opt/wakr/wakr
```

### 3. Create the virtual environment as root, owned by the service user

```bash
sudo -u wakr-api python3 -m venv /opt/wakr/Wakr-Star-DB/.venv
sudo -u wakr-api /opt/wakr/Wakr-Star-DB/.venv/bin/pip install \
    -r /opt/wakr/Wakr-Star-DB/src/requirements.txt
```

### 4. Create the `.env` file

```bash
sudo -u wakr-api tee /opt/wakr/Wakr-Star-DB/src/.env > /dev/null << 'EOF'
DATABASE_URL=postgresql+asyncpg://wakr:secret@localhost:5432/wakr
DEBUG=false
TOKEN_ISSUER=https://wakr.us.auth0.com/
TOKEN_AUDIENCE=https://api.wakr.co
JWT_PUBLIC_KEY=-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w...your key here...
-----END PUBLIC KEY-----
EOF

sudo chmod 600 /opt/wakr/Wakr-Star-DB/src/.env
```

### 5. Create the systemd unit file

```bash
sudo tee /etc/systemd/system/wakr-api.service > /dev/null << 'EOF'
[Unit]
Description=Wakr Market Intelligence API
After=network.target postgresql.service
Wants=postgresql.service

[Service]
Type=exec
User=wakr-api
Group=wakr-api
WorkingDirectory=/opt/wakr/Wakr-Star-DB/src
ExecStart=/opt/wakr/Wakr-Star-DB/.venv/bin/uvicorn main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers 4 \
    --no-access-log
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=wakr-api

# Harden the service
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths=/opt/wakr/Wakr-Star-DB/src

[Install]
WantedBy=multi-user.target
EOF
```

### 6. Enable and start

```bash
sudo systemctl daemon-reload
sudo systemctl enable wakr-api
sudo systemctl start wakr-api
sudo systemctl status wakr-api
```

### 7. View logs

```bash
# Live log tail
sudo journalctl -u wakr-api -f

# Last 100 lines
sudo journalctl -u wakr-api -n 100
```

### 8. Reload after a code update

```bash
sudo systemctl restart wakr-api
```

### Putting it behind nginx (recommended)

```nginx
server {
    listen 443 ssl;
    server_name api.wakr.co;

    ssl_certificate     /etc/letsencrypt/live/api.wakr.co/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.wakr.co/privkey.pem;

    location / {
        proxy_pass         http://127.0.0.1:8000;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
    }
}
```

---

## Authentication

Every request requires a valid OAuth 2.0 Bearer token in the `Authorization` header.

```
Authorization: Bearer <access_token>
```

### Obtaining a token (server-to-server / Prisma consumer)

```bash
curl -s -X POST https://wakr.us.auth0.com/oauth/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=client_credentials" \
  -d "client_id=YOUR_CLIENT_ID" \
  -d "client_secret=YOUR_CLIENT_SECRET" \
  -d "audience=https://api.wakr.co"
```

Response:

```json
{
  "access_token": "eyJhbGci...",
  "token_type": "Bearer",
  "expires_in": 3600,
  "scope": "wakr:read"
}
```

Cache the token and refresh before expiry. All examples below assume the token is stored in the `TOKEN` shell variable:

```bash
TOKEN="eyJhbGci..."
BASE="https://api.wakr.co"
```

---

## API Reference

### Common query parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `time_range` | `string` | **required** | `trailing_7` \| `trailing_30` \| `trailing_90` \| `last_month` \| `last_quarter` \| `ytd` \| `l12m` |
| `inventory_type` | `string` | `combined` | `new` \| `used` \| `combined` |
| `make` | `string` | all makes | Manufacturer name, e.g. `Malibu`. Omit or pass `all` for all makes. |
| `model` | `string` | all models | Boat model name, e.g. `23 LSV`. Only valid when `make` is also specified. |
| `state` | `string` | all states | Two-letter US state code, e.g. `FL`. Regional endpoints only. |

---

### Inventory Tab

#### `GET /api/v1/inventory/summary`

Headline KPI cards: active listings, boats sold, inventory added, avg DOM, aging %, DOM distribution.

```bash
curl -s "$BASE/api/v1/inventory/summary?time_range=trailing_30&inventory_type=new&make=Malibu" \
  -H "Authorization: Bearer $TOKEN" | jq
```

```bash
# All makes, combined inventory, trailing 90 days
curl -s "$BASE/api/v1/inventory/summary?time_range=trailing_90" \
  -H "Authorization: Bearer $TOKEN" | jq
```

**Example response:**

```json
{
  "data": {
    "active_listings": 3201,
    "boats_sold": 148,
    "inventory_added": 820,
    "avg_days_on_market": 23.0,
    "pct_aging_past_30d": 13.0,
    "dom_distribution": {
      "bucket_0_7": 897,
      "bucket_8_15": 1082,
      "bucket_16_30": 762,
      "bucket_31_60": 748,
      "bucket_60_plus": 0
    }
  },
  "data_as_of": "2026-05-13T06:00:00",
  "generated_at": "2026-05-21T14:22:10Z",
  "filters_applied": {
    "time_range": "trailing_30",
    "inventory_type": "new",
    "make": "Malibu"
  }
}
```

---

#### `GET /api/v1/inventory/trend`

Time-series of active listing counts for the Total Inventory Trend chart.

```bash
curl -s "$BASE/api/v1/inventory/trend?time_range=l12m&inventory_type=combined" \
  -H "Authorization: Bearer $TOKEN" | jq
```

```bash
# New Supra inventory trend, last 90 days
curl -s "$BASE/api/v1/inventory/trend?time_range=trailing_90&inventory_type=new&make=Supra" \
  -H "Authorization: Bearer $TOKEN" | jq
```

**Example response:**

```json
{
  "data": {
    "series": [
      { "snapshot_date": "2025-05-21", "active_listings": 2940 },
      { "snapshot_date": "2025-05-28", "active_listings": 3012 },
      { "snapshot_date": "2026-05-14", "active_listings": 3201 }
    ]
  },
  "data_as_of": "2026-05-13T06:00:00",
  "generated_at": "2026-05-21T14:22:10Z",
  "filters_applied": { "time_range": "l12m", "inventory_type": "combined" }
}
```

---

#### `GET /api/v1/inventory/velocity`

Inventory & Velocity table: per model-year rows with avg DOM, active units, boats sold, and momentum classification.

> **Note:** This endpoint accepts `state` instead of `model`.

```bash
curl -s "$BASE/api/v1/inventory/velocity?time_range=trailing_30&make=Centurion" \
  -H "Authorization: Bearer $TOKEN" | jq
```

```bash
# All makes, Florida only
curl -s "$BASE/api/v1/inventory/velocity?time_range=trailing_30&state=FL" \
  -H "Authorization: Bearer $TOKEN" | jq
```

**Example response:**

```json
{
  "data": {
    "rows": [
      {
        "model_year": "2026 Centurion Fi23",
        "manufacturer": "Centurion",
        "model": "Fi23",
        "year": 2026,
        "avg_days_on_market": 14.2,
        "dom_velocity_label": "Fast",
        "active_units": 42,
        "boats_sold": 18,
        "momentum": "Accelerating"
      }
    ]
  },
  "data_as_of": "2026-05-13T06:00:00",
  "generated_at": "2026-05-21T14:22:10Z",
  "filters_applied": { "time_range": "trailing_30", "make": "Centurion" }
}
```

**Momentum thresholds:** DOM decreased >10% vs prior window → `Accelerating` | within ±10% → `Stable` | increased >10% → `Slowing`

**DOM velocity labels:** `Fast` <15d | `Healthy` 15–22d | `Slow` 23–30d | `Very Slow` 30d+

---

### Pricing Tab

#### `GET /api/v1/pricing/summary`

Headline price KPIs: avg list price, median price, month-over-month price change, top selling price band.

> `mom_price_change_pct` always compares the two most recently completed calendar months, regardless of `time_range`.

```bash
curl -s "$BASE/api/v1/pricing/summary?time_range=trailing_30&make=Malibu" \
  -H "Authorization: Bearer $TOKEN" | jq
```

**Example response:**

```json
{
  "data": {
    "avg_list_price": 142500.00,
    "median_list_price": 136000.00,
    "mom_price_change_pct": -4.1,
    "top_selling_band": {
      "band": "over_140k",
      "band_label": "Over $140k",
      "units_sold": 134
    }
  },
  "data_as_of": "2026-05-13T06:00:00",
  "generated_at": "2026-05-21T14:22:10Z",
  "filters_applied": { "time_range": "trailing_30", "make": "Malibu" }
}
```

---

#### `GET /api/v1/pricing/dom-by-price-tier`

Average days on market for each of the six price bands.

```bash
curl -s "$BASE/api/v1/pricing/dom-by-price-tier?time_range=trailing_30&inventory_type=new" \
  -H "Authorization: Bearer $TOKEN" | jq
```

**Example response:**

```json
{
  "data": {
    "bands": [
      { "band": "under_60k",    "band_label": "Under $60k",  "avg_days_on_market": 0.0,  "velocity_label": "Very Slow" },
      { "band": "60k_80k",      "band_label": "$60–80k",     "avg_days_on_market": 31.4, "velocity_label": "Very Slow" },
      { "band": "80k_100k",     "band_label": "$80–100k",    "avg_days_on_market": 22.1, "velocity_label": "Healthy" },
      { "band": "100k_120k",    "band_label": "$100–120k",   "avg_days_on_market": 19.8, "velocity_label": "Healthy" },
      { "band": "120k_140k",    "band_label": "$120–140k",   "avg_days_on_market": 17.3, "velocity_label": "Healthy" },
      { "band": "over_140k",    "band_label": "Over $140k",  "avg_days_on_market": 24.5, "velocity_label": "Slow" }
    ]
  },
  "data_as_of": "2026-05-13T06:00:00",
  "generated_at": "2026-05-21T14:22:10Z",
  "filters_applied": { "time_range": "trailing_30", "inventory_type": "new" }
}
```

All six bands are always returned. Bands with zero listings return `avg_days_on_market: 0.0`.

---

#### `GET /api/v1/pricing/listings-by-price-tier`

Active listing count per price band (drives the horizontal bar chart).

```bash
curl -s "$BASE/api/v1/pricing/listings-by-price-tier?time_range=trailing_30" \
  -H "Authorization: Bearer $TOKEN" | jq
```

**Example response:**

```json
{
  "data": {
    "bands": [
      { "band": "under_60k",  "band_label": "Under $60k",  "listings": 12  },
      { "band": "60k_80k",    "band_label": "$60–80k",     "listings": 204 },
      { "band": "80k_100k",   "band_label": "$80–100k",    "listings": 618 },
      { "band": "100k_120k",  "band_label": "$100–120k",   "listings": 891 },
      { "band": "120k_140k",  "band_label": "$120–140k",   "listings": 743 },
      { "band": "over_140k",  "band_label": "Over $140k",  "listings": 733 }
    ]
  },
  "data_as_of": "2026-05-13T06:00:00",
  "generated_at": "2026-05-21T14:22:10Z",
  "filters_applied": { "time_range": "trailing_30" }
}
```

---

#### `GET /api/v1/pricing/model-efficiency`

Model Price Efficiency table — per model-year rows ranked fastest-to-slowest by avg DOM.

```bash
curl -s "$BASE/api/v1/pricing/model-efficiency?time_range=trailing_30&make=Malibu" \
  -H "Authorization: Bearer $TOKEN" | jq
```

```bash
# Specific model
curl -s "$BASE/api/v1/pricing/model-efficiency?time_range=trailing_30&make=Centurion&model=Ri245" \
  -H "Authorization: Bearer $TOKEN" | jq
```

**Example response:**

```json
{
  "data": {
    "rows": [
      {
        "rank": 1,
        "model_year": "2021 Centurion Ri235",
        "manufacturer": "Centurion",
        "model": "Ri235",
        "year": 2021,
        "avg_list_price": 79500.00,
        "price_band_low": 68000.00,
        "price_band_high": 91000.00,
        "price_band_label": "$68k–$91k",
        "avg_days_on_market": 12.4,
        "dom_velocity_label": "Fast",
        "listings": 38
      }
    ]
  },
  "data_as_of": "2026-05-13T06:00:00",
  "generated_at": "2026-05-21T14:22:10Z",
  "filters_applied": { "time_range": "trailing_30", "make": "Centurion", "model": "Ri245" }
}
```

Rows are ranked by `avg_days_on_market` ascending (fastest movers first). Consumer implements free-text search client-side.

---

### Regional Tab

#### `GET /api/v1/regional/summary`

National KPI cards: avg DOM, fastest/slowest markets, top growth state, sales trend direction counts.

```bash
curl -s "$BASE/api/v1/regional/summary?time_range=trailing_30" \
  -H "Authorization: Bearer $TOKEN" | jq
```

```bash
# Filtered to one make
curl -s "$BASE/api/v1/regional/summary?time_range=trailing_30&make=Malibu" \
  -H "Authorization: Bearer $TOKEN" | jq
```

**Example response:**

```json
{
  "data": {
    "national_avg_dom": 23.1,
    "fastest_market": {
      "state": "TX",
      "state_name": "Texas",
      "avg_dom": 14.9,
      "pct_vs_national": 35.5
    },
    "slowest_market": {
      "state": "VT",
      "state_name": "Vermont",
      "avg_dom": 34.1,
      "pct_vs_national": 47.6
    },
    "top_growth_state": {
      "state": "TX",
      "state_name": "Texas",
      "yoy_supply_change_pct": 9.1
    },
    "sales_trends": {
      "states_rising": 8,
      "states_falling": 10
    }
  },
  "data_as_of": "2026-05-13T06:00:00",
  "generated_at": "2026-05-21T14:22:10Z",
  "filters_applied": { "time_range": "trailing_30" }
}
```

> `pct_vs_national` on `fastest_market`: positive = how much faster than national avg (e.g. 35.5 = 35.5% faster).  
> `pct_vs_national` on `slowest_market`: positive = how much slower than national avg.

---

#### `GET /api/v1/regional/state-overview`

State Market Overview table and choropleth map data — one row per state.

```bash
curl -s "$BASE/api/v1/regional/state-overview?time_range=trailing_30" \
  -H "Authorization: Bearer $TOKEN" | jq
```

```bash
# New boats only, specific make
curl -s "$BASE/api/v1/regional/state-overview?time_range=trailing_30&inventory_type=new&make=Supra" \
  -H "Authorization: Bearer $TOKEN" | jq
```

**Example response:**

```json
{
  "data": {
    "national_total_boats_sold": 1482,
    "rows": [
      {
        "state": "FL",
        "state_name": "Florida",
        "listings": 487,
        "avg_days_on_market": 21.3,
        "dom_velocity_label": "Healthy",
        "boats_sold": 226,
        "pct_market": 15.2,
        "avg_list_price": 128400.00
      },
      {
        "state": "TX",
        "state_name": "Texas",
        "listings": 412,
        "avg_days_on_market": 14.9,
        "dom_velocity_label": "Fast",
        "boats_sold": 198,
        "pct_market": 13.4,
        "avg_list_price": 119800.00
      }
    ]
  },
  "data_as_of": "2026-05-13T06:00:00",
  "generated_at": "2026-05-21T14:22:10Z",
  "filters_applied": { "time_range": "trailing_30" }
}
```

Rows are sorted by `boats_sold` descending. The consumer renders both the choropleth map and the sortable table from this single payload.

---

#### `GET /api/v1/regional/market-leaders`

Top and bottom N states by boats sold.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `top_n` | integer | `5` | Number of top and bottom states to return (max 50) |

```bash
curl -s "$BASE/api/v1/regional/market-leaders?time_range=trailing_30&top_n=5" \
  -H "Authorization: Bearer $TOKEN" | jq
```

```bash
# Top 10 for a specific make
curl -s "$BASE/api/v1/regional/market-leaders?time_range=trailing_30&make=Malibu&top_n=10" \
  -H "Authorization: Bearer $TOKEN" | jq
```

**Example response:**

```json
{
  "data": {
    "top_states": [
      { "rank": 1, "state": "FL", "state_name": "Florida",    "boats_sold": 226, "listings": 487 },
      { "rank": 2, "state": "TX", "state_name": "Texas",      "boats_sold": 198, "listings": 412 },
      { "rank": 3, "state": "CA", "state_name": "California", "boats_sold": 174, "listings": 389 }
    ],
    "bottom_states": [
      { "rank": 1, "state": "AK", "state_name": "Alaska",     "boats_sold": 2,  "listings": 7  },
      { "rank": 2, "state": "VT", "state_name": "Vermont",    "boats_sold": 4,  "listings": 12 },
      { "rank": 3, "state": "ND", "state_name": "North Dakota","boats_sold": 5,  "listings": 14 }
    ]
  },
  "data_as_of": "2026-05-13T06:00:00",
  "generated_at": "2026-05-21T14:22:10Z",
  "filters_applied": { "time_range": "trailing_30" }
}
```

---

## Error Responses

All errors use a consistent envelope:

```json
{ "error": { "code": "INVALID_PARAM", "message": "Unknown make: Foobar", "field": "make" } }
```

| HTTP Status | Code | Condition |
|-------------|------|-----------|
| `400` | `INVALID_PARAM` | Unknown `make` or `model` value, invalid enum |
| `400` | `MISSING_PARAM` | Required parameter absent |
| `401` | `UNAUTHORIZED` | Missing or invalid Bearer token |
| `403` | `FORBIDDEN` | Valid token but missing `wakr:read` scope |
| `404` | `NO_DATA` | Valid filters but zero rows in the requested window |
| `422` | `INSUFFICIENT_DATA` | Window too narrow for a derived metric (e.g. MoM requires at least one completed calendar month) |
| `500` | `INTERNAL` | Unhandled server error |

---

## Response Envelope

Every successful response is wrapped in a standard envelope:

```json
{
  "data": { ... },
  "data_as_of": "2026-05-13T06:00:00",
  "generated_at": "2026-05-21T14:22:10Z",
  "filters_applied": { "time_range": "trailing_30", "inventory_type": "combined" }
}
```

| Field | Description |
|-------|-------------|
| `data` | Endpoint-specific payload |
| `data_as_of` | ISO 8601 datetime of the most recent scrape snapshot that contributed to this response. Always surface this to end users. |
| `generated_at` | ISO 8601 datetime this response was produced |
| `filters_applied` | Echo of the filters actually used (omits defaulted-to-all parameters) |
