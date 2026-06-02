# Wakr-Star-DB API Tests

Tests for the FastAPI analytics API that serves inventory, pricing, and regional market data from the Wakr Star DB.

The suite has two layers:

- **Mock tests** (`test_auth.py`, `test_inventory.py`, `test_pricing.py`, `test_regional.py`, `test_api_payloads.py`) — run in-process with no server or database.  The database layer is replaced with `AsyncMock` connections returning pre-canned row objects.
- **Live tests** (`test_live_payloads.py`) — hit a real Star DB via actual SQL queries.  Skipped automatically unless `RUN_LIVE_TESTS=1` is set.

---

## How the mocking works

| File | Purpose |
|---|---|
| `conftest.py` | Shared fixtures and DB mock helpers (`mock_result`, `mock_conn`, `get_conn_for`) |
| `mock_data.py` | Canned `SimpleNamespace` row objects used across all test modules |

**`mock_result(*rows)`** wraps one or more rows into a mock `CursorResult` that supports `fetchone()` and `fetchall()`.

**`mock_conn(*results)`** builds a mock `AsyncConnection` whose `execute()` returns each result in sequence — one per SQL query the endpoint fires.

**`get_conn_for(conn)`** returns a drop-in replacement for the `get_conn` database dependency.  Each test patches the relevant router's `get_conn` with this factory, then restores it after the `with` block.

---

## How to run

### Mock tests (no database required)

```bash
cd /Users/charlieberg/Docs/Wakr/Wakr-Star-DB/src

# Full mock suite
pytest

# One module
pytest tests/test_inventory.py -v

# One class or test
pytest tests/test_inventory.py::TestInventorySummary::test_active_listings -v

# With coverage
pytest --cov=routers --cov-report=term-missing

# API payload log (writes tests/payload_logs/api_payloads_<timestamp>.json)
pytest tests/test_api_payloads.py -v -s
```

No environment variables required — `conftest.py` sets `DEBUG=true` and a dummy `STARDB_URL` before the app is imported.

---

### Live tests (real Star DB)

Live tests call every endpoint with no mocking and log each response to `tests/payload_logs/live_api_payloads_<timestamp>.json`.

#### 1. Start the local database

```bash
cd ~/Docs/Wakr
docker compose -f docker-compose.local.yml up -d
```

#### 2. Seed test data

Run once (or any time you want a clean slate).  From `src/`:

```bash
STARDB_URL=postgresql+asyncpg://postgres:postgres@127.0.0.1:5433/wakr_stardb \
python -c "from tests.seed_test_db import seed_test_db; seed_test_db()"
```

This truncates all Star DB tables and inserts a representative dataset covering all six states, two manufacturers, three models, seven snapshot dates, and ~45 estimated-sale rows.

#### 3. Run the live tests

```bash
cd /Users/charlieberg/Docs/Wakr/Wakr-Star-DB/src

STARDB_URL=postgresql+asyncpg://postgres:postgres@127.0.0.1:5433/wakr_stardb \
RUN_LIVE_TESTS=1 \
pytest tests/test_live_payloads.py -v -s
```

The live tests are **skipped automatically** unless `RUN_LIVE_TESTS=1` is set, so they never run in CI or accidentally against a production database.

#### Environment variables

| Variable | Mock tests | Live tests |
|---|---|---|
| `STARDB_URL` | Not needed (dummy set by conftest) | Required — point at local Docker DB |
| `RUN_LIVE_TESTS` | Not used | Must be `1` to enable |
| `DEBUG` | Set to `true` by conftest | Set to `true` by conftest |

---

## Test files

### `test_auth.py`

**What it does:** Tests the JWT authentication and scope-checking logic in `auth.py`.

**What it covers:**

- `_has_required_scope` (pure function): verifies scope matching works for both string (`"wakr:read wakr:write"`) and list (`["wakr:read"]`) JWT claims, including missing and `None` scope values.
- `require_auth` (async FastAPI dependency): verifies that missing credentials return 401, wrong HTTP scheme returns 401, a valid token with the wrong scope returns 403, and a valid token with `wakr:read` scope returns the token string.  Tests run against the real `require_auth` code path with `jwt.decode` patched.

---

### `test_inventory.py`

**What it does:** Tests all three endpoints under `/api/v1/inventory` — `summary`, `trend`, and `velocity`.

**What it covers:**

**`/summary`** (12 tests)
- Response envelope fields (`data`, `data_as_of`, `generated_at`, `filters_applied`)
- Correct values for `active_listings`, `boats_sold`, `inventory_added`, `avg_days_on_market`
- `pct_aging_past_30d` calculation: `(bucket_31_60 + bucket_60_plus) / active_listings * 100`
- All five DOM distribution bucket values
- `filters_applied` echo — time_range and inventory_type are reflected back
- `data_as_of` is a full ISO datetime ending in `Z`
- `as_of_date` query param is accepted (overrides the time window end)
- Missing `time_range` → 400 with `MISSING_PARAM` code
- Invalid `time_range` value → 400 with `INVALID_PARAM` code
- Missing auth header → 401 with `UNAUTHORIZED` code
- Empty DB result → 404 with `NO_DATA` code

**`/trend`** (5 tests)
- Series array contains one entry per snapshot date
- Each point has `snapshot_date` (YYYY-MM-DD) and `active_listings`
- Dates are valid ISO format
- `as_of_date` param accepted
- Empty result → 404

**`/velocity`** (10 tests)
- Row count and field presence
- Momentum labels: Fi23 (DOM improved 14.2 vs prior 17.0) → `Accelerating`; Ri245 (DOM worsened 28.5 vs 25.0) → `Slowing`
- DOM velocity label: Fi23 at 14.2 days → `Fast` (threshold < 15)
- Rows sorted by `avg_days_on_market` ascending
- `model_year` label format: `"{year} {manufacturer} {model}"`
- `as_of_date` param accepted
- Empty result → 404

---

### `test_pricing.py`

**What it does:** Tests all four endpoints under `/api/v1/pricing` — `summary`, `dom-by-price-tier`, `listings-by-price-tier`, and `model-efficiency`.

**What it covers:**

**`/summary`** (11 tests)
- `avg_list_price` and `median_list_price` values
- `mom_price_change_pct`: raw DB value `-0.041` is multiplied by 100 to produce `-4.1`
- `top_selling_band` object: correct band key (`over_140k`), label (`Over $140k`), and unit count
- Full response envelope fields
- `data_as_of` is a full ISO datetime
- Missing `time_range` → 400
- No auth → 401
- `as_of_date` param accepted
- No `mart_pricing_trends` row → 422 with `INSUFFICIENT_DATA` code

**`/dom-by-price-tier`** (7 tests)
- Always exactly six bands in fixed order (`under_60k` through `over_140k`)
- Each band has `band`, `band_label`, `avg_days_on_market`, and `velocity_label`
- Zero-listing band → `avg_days_on_market` of 0.0
- Velocity labels are one of: `Fast`, `Healthy`, `Slow`, `Very Slow`
- Weighted DOM calculation: `sum(dom * count) / sum(count)`

**`/listings-by-price-tier`** (4 tests)
- Always six bands; listing counts match the mock data
- `band_label` is never an empty string

**`/model-efficiency`** (6 tests)
- Rows ranked by DOM ascending (Ri235 at 12.4 → rank 1, Ri245 at 21.7 → rank 2)
- All required row fields present
- `price_band_label` formatted from `price_band_low`/`price_band_high`: `"$68k–$91k"`
- Empty result → 404

---

### `test_regional.py`

**What it does:** Tests all three endpoints under `/api/v1/regional` — `summary`, `state-overview`, and `market-leaders`.

**What it covers:**

**`/summary`** (11 tests)
- Weighted national average DOM: `sum(avg_dom * active_listings) / sum(active_listings)`
- Fastest market identified by lowest avg DOM → TX (14.9)
- Slowest market identified by highest avg DOM → CA (26.1)
- `pct_vs_national` for fastest market is positive (TX is faster than national average)
- Top growth state by YoY supply change → TX (9.1%)
- Sales trends: TX=Rising and CA=Falling → `states_rising=1`, `states_falling=1`
- State names resolved from `US_STATE_NAMES` lookup (e.g. `"TX"` → `"Texas"`)
- No auth → 401
- `as_of_date` param accepted
- Empty result → 404

**`/state-overview`** (9 tests)
- `national_total_boats_sold` sums boats_sold across all states (FL+TX+CA = 598)
- Rows sorted by `boats_sold` descending
- `pct_market` values sum to 100%
- All required row fields present
- DOM velocity labels are valid (`Fast`, `Healthy`, `Slow`, `Very Slow`)
- TX at 14.9 avg DOM → `dom_velocity_label: "Fast"`
- State names resolved (FL→Florida, TX→Texas, CA→California)
- Empty result → 404

**`/market-leaders`** (12 tests)
- Top and bottom state counts respect the `top_n` parameter
- Default `top_n=5` returns 5 states in each list
- Top states sorted by `boats_sold` descending; FL is #1 with 226 sales
- Bottom states start with AK (2 sales)
- No overlap between top and bottom state sets
- Row fields present: `rank`, `state`, `state_name`, `boats_sold`, `listings`
- State names resolved
- `as_of_date` param accepted
- Empty result → 404

---

### `test_api_payloads.py`

**What it does:** Calls every endpoint once with baseline (no-filter) parameters, validates the complete response envelope and every required payload field, and writes the full responses to a timestamped JSON log file.  Also tests filter combinations for selected endpoints.

**What it covers:**

**Baseline tests** (one class per endpoint, 10 total)

Each baseline test asserts:
- All four envelope fields are present: `data`, `data_as_of`, `generated_at`, `filters_applied`
- `data_as_of` is a full ISO datetime ending in `Z`
- All required `data` fields and nested fields are present
- Key numeric values match the mock data exactly

Endpoints covered: `inventory/summary`, `inventory/trend`, `inventory/velocity`, `pricing/summary`, `pricing/dom-by-price-tier`, `pricing/listings-by-price-tier`, `pricing/model-efficiency`, `regional/summary`, `regional/state-overview`, `regional/market-leaders`

**Filter tests** (`TestInventorySummaryFilters`, `TestPricingSummaryFilters`, `TestRegionalSummaryFilters`)

| Test | Filter | DB queries | What's verified |
|---|---|---|---|
| `test_inventory_type_new` | `inventory_type=new` | 3 (no key-res) | `filters_applied.inventory_type == "new"` |
| `test_make_filter` | `make=centurion` | 4 (1 key-res + 3 data) | `filters_applied.make == "centurion"` |
| `test_make_and_model_filter` | `make=centurion&model=fi23` | 5 (2 key-res + 3 data) | Both make and model echoed |
| `test_unknown_make_returns_400` | `make=unknown_brand` | 1 (returns None) | 400, `error.code == "INVALID_PARAM"`, `field == "make"` |
| `test_unknown_model_returns_400` | `make=centurion&model=unknown` | 2 (make found, model empty) | 400, `field == "model"` |
| `test_inventory_type_used` (pricing) | `inventory_type=used` | 2 | `filters_applied.inventory_type == "used"` |
| `test_make_filter` (pricing) | `make=centurion` | 3 | `filters_applied.make == "centurion"` |
| `test_state_filter` (regional) | `state=TX` | 2 (no key-res) | `filters_applied.state == "TX"` |
| `test_inventory_type_new` (regional) | `inventory_type=new` | 2 | `filters_applied.inventory_type == "new"` |
| `test_make_filter` (regional) | `make=centurion` | 3 | `filters_applied.make == "centurion"` |

**Payload log**

Every test records its response to a session-scoped list.  At teardown, the full log is written to `tests/payload_logs/api_payloads_<YYYYMMDD_HHMMSS>.json`.  The log path is printed at the end of the test run.

---

### `test_live_payloads.py`

**What it does:** Calls every endpoint once against a real Star DB (no mocking), asserts response shape and status, and writes all responses to `tests/payload_logs/live_api_payloads_<timestamp>.json`.

**What it covers:** One test class per endpoint — 10 tests total.  Assertions check structure only (field presence, correct types, non-empty collections), not specific values, so the tests pass regardless of what data is in the database.

| Endpoint | Assertions |
|---|---|
| `GET /inventory/summary` | Envelope present; all data fields and DOM buckets present; `active_listings > 0` |
| `GET /inventory/trend` | Series is a non-empty list; each point has `snapshot_date` (YYYY-MM-DD) and `active_listings` |
| `GET /inventory/velocity` | Rows present; each row has momentum, DOM label, and model-year fields |
| `GET /pricing/summary` | Prices and MoM pct present; `top_selling_band` has band, label, and unit count |
| `GET /pricing/dom-by-price-tier` | Always exactly 6 bands; each has band key, label, avg DOM, and velocity label |
| `GET /pricing/listings-by-price-tier` | Always exactly 6 bands; each has band key and listing count |
| `GET /pricing/model-efficiency` | Rows present; each has rank, price, DOM, velocity label, and listing count |
| `GET /regional/summary` | National avg DOM, fastest/slowest markets, top growth state, and trend counts present |
| `GET /regional/state-overview` | `national_total_boats_sold` present; rows have state, name, listings, DOM, boats_sold, pct_market |
| `GET /regional/market-leaders` | `top_n=3` returns exactly 3 top and 3 bottom states; each row has rank, state, boats_sold, listings |

**Seed helper:** `seed_test_db.py` provides `seed_test_db()` which truncates all tables and inserts data covering all six states, two manufacturers, three models, seven snapshot date_keys (spanning l12m), two completed calendar months in `mart_pricing_trends`, and ~45 rows in `fact_estimated_sale`.
