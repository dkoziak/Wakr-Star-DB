# Wakr Market Intelligence — API Contract
**Version:** 1.6.0-draft  
**Backend:** Python (FastAPI)  
**Consumer ORM:** Prisma (TypeScript/Node)  
**Transport:** REST over HTTPS  
**Payload format:** JSON (Prisma-compatible plain objects)  
**Auth:** OAuth 2.0 Bearer token — enforced in middleware, never a query parameter (see Authentication section)

---

## Authentication

All API endpoints require a valid token on every request. Authentication is handled entirely at the **transport layer** — it is not a query parameter and is never passed into the variadic filter map or the query parameter registry.

### Token Types

| Type | Use Case | Mechanism |
|------|----------|-----------|
| OAuth 2.0 Bearer Token | Human users authenticated via an identity provider (e.g. Auth0, Cognito) | `Authorization: Bearer <access_token>` header |
| Client Credentials Token | Server-to-server / automated consumers (e.g. the Prisma-based front-end backend) | OAuth 2.0 client credentials flow; same `Authorization: Bearer <token>` header |

Both token types use the same header and are validated by the same middleware. The token type is transparent to the API handler — by the time a request reaches a route handler, the caller is already authenticated.

### Enforcement

- All endpoints return `401 Unauthorized` if the `Authorization` header is absent or the token is invalid/expired.
- All endpoints return `403 Forbidden` if the token is valid but the caller lacks permission for the requested resource.
- Token validation is performed in **middleware**, before the request reaches the query dispatch layer. No route handler contains auth logic.
- Tokens are never logged, stored in query params, or included in response bodies.

### Client Credentials Flow (Prisma Consumer)

The analytics front-end backend authenticates using the OAuth 2.0 client credentials grant:

```
POST /oauth/token
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials
&client_id=<client_id>
&client_secret=<client_secret>
&scope=wakr:read
```

Response:
```json
{
  "access_token": "<token>",
  "token_type": "Bearer",
  "expires_in": 3600,
  "scope": "wakr:read"
}
```

The consumer is responsible for caching the token and refreshing before expiry. Token endpoints are outside this contract's scope and are managed by the identity provider.

### Error Responses for Auth Failures

```json
// 401 — missing or invalid token
{ "error": { "code": "UNAUTHORIZED", "message": "Valid Bearer token required." } }

// 403 — valid token, insufficient scope
{ "error": { "code": "FORBIDDEN", "message": "Token does not have the required scope: wakr:read." } }
```

---

## Design Principles

### Query Parameter Registry (Input Side)
All filter parameters are passed as a variadic parameter map (`filters: Record<string, string>`). The API handler dispatches each key to a registered WHERE-clause template via a config file. Rules:
- Config entries define SQL template fragments with **named bind parameters only** — no value interpolation ever.
- A startup validator parses every config entry against the known schema.
- The dispatch layer is thin and generic: look up config entry → bind value → append to WHERE.
- Parameter interactions requiring JOIN changes or conditional logic live in **code**, not config.
- Every config entry has a corresponding integration test.

### Output Transform Registry (Output Side)
Return values are produced by a two-tier output registry:

| Tier | Type | Driven by |
|------|------|-----------|
| 1 | Aggregations: `sum`, `avg`, `count`, `min`, `max` on raw columns | Config only |
| 2 | Derived metrics: ratios, percentages, MoM deltas, momentum classifications | Config declares formula + inputs; code executes a named operation function |

Adding a new output field of an existing operation type requires only a config entry. New operation types require one new function added to the operation library.

### Trailing Window Semantics
Trailing metrics (T7, T30, T90) are computed **at query time** relative to the caller's request date (`as_of_date`), not the scrape date. The mart layer (`mart_daily_snapshot`) stores pre-aggregated daily rows; the API handler sums/averages those rows over the requested window at runtime.

### Data Freshness
Every response envelope includes a `data_as_of` timestamp reflecting the most recent scrape snapshot date. Consumers must surface this to end users.

---

## Common Types

```typescript
// Shared filter parameter map — variadic, extensible via config
type FilterParams = {
  time_range:      TimeRange;         // always required
  inventory_type?: InventoryType;     // default: "combined"
  make?:           string;            // manufacturer name or "all"
  model?:          string;            // boat model name or "all"
  state?:          string;            // 2-letter US state code or "all"
};

type TimeRange =
  | "trailing_7"
  | "trailing_30"
  | "trailing_90"
  | "last_month"
  | "last_quarter"
  | "ytd"
  | "l12m";

type InventoryType = "new" | "used" | "combined";

type MomentumLabel = "Accelerating" | "Stable" | "Slowing";

type DomVelocityLabel = "Fast" | "Healthy" | "Slow" | "Very Slow";
// Fast: <15d | Healthy: 15–22d | Slow: 23–30d | Very Slow: 30d+

type PriceBand =
  | "under_60k"
  | "60k_80k"
  | "80k_100k"
  | "100k_120k"
  | "120k_140k"
  | "over_140k";

// Standard response envelope wrapping all payloads
type ApiResponse<T> = {
  data:        T;
  data_as_of:  string;   // ISO 8601 datetime of most recent scrape snapshot
  generated_at: string;  // ISO 8601 datetime of this response
  filters_applied: FilterParams;
};
```

---

## Endpoints

---


---

### General

Endpoints that span all tabs or are not specific to a single page. Authentication is handled by the identity provider — see the **Authentication** section for token issuance details. Shared types (`FilterParams`, `ApiResponse<T>`, `TimeRange`, etc.) apply to all endpoints below.

*No dedicated General endpoint is defined in this version.*

---

### Inventory Tab

Endpoints serving the **Inventory** page: headline KPIs, DOM distribution, inventory trend chart, and the Inventory & Velocity table.

#### 1. `GET /api/v1/inventory/summary`

Returns headline KPI cards for the Inventory tab.

#### Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `time_range` | `TimeRange` | Yes | Trailing window or calendar period |
| `inventory_type` | `InventoryType` | No | Default: `combined` |
| `make` | `string` | No | Manufacturer name; omit or `"all"` for all makes |
| `model` | `string` | No | Boat model name; omit or `"all"` for all models |

#### Response Payload

```typescript
type InventorySummaryResponse = ApiResponse<{
  active_listings:      number;   // Tier 1: count of active listing rows
  boats_sold:           number;   // Tier 1: sum of estimated_sale events over the requested time_range window
  inventory_added:      number;   // Tier 1: sum of new_listings_today over window
  avg_days_on_market:   number;   // Tier 1: avg(avg_dom) weighted by active_listings
  pct_aging_past_30d:   number;   // Tier 2: (dom_bucket_31_60 + dom_bucket_60_plus) / active_listings * 100
  dom_distribution: {
    bucket_0_7:   number;         // Tier 1: sum(dom_bucket_0_7)
    bucket_8_15:  number;         // Tier 1: sum(dom_bucket_8_15)
    bucket_16_30: number;         // Tier 1: sum(dom_bucket_16_30)
    bucket_31_60: number;         // Tier 1: sum(dom_bucket_31_60)
    bucket_60_plus: number;       // Tier 1: sum(dom_bucket_60_plus)
  };
}>;
```

#### Example Request
```
GET /api/v1/inventory/summary?time_range=trailing_30&inventory_type=new&make=all
```

#### Example Response
```json
{
  "data": {
    "active_listings": 3201,
    "boats_sold": 148,
    "inventory_added": 820,
    "avg_days_on_market": 23,
    "pct_aging_past_30d": 13.0,
    "dom_distribution": {
      "bucket_0_7": 897,
      "bucket_8_15": 1082,
      "bucket_16_30": 762,
      "bucket_31_60": 748,
      "bucket_60_plus": 0
    }
  },
  "data_as_of": "2026-05-13T06:00:00Z",
  "generated_at": "2026-05-15T14:22:10Z",
  "filters_applied": {
    "time_range": "trailing_30",
    "inventory_type": "new",
    "make": "all"
  }
}
```

---

#### 2. `GET /api/v1/inventory/trend`

Returns the time-series of active listing counts for the Total Inventory Trend chart.

#### Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `time_range` | `TimeRange` | Yes | Defines the lookback window for the series |
| `inventory_type` | `InventoryType` | No | Default: `combined` |
| `make` | `string` | No | Manufacturer name or `"all"` |
| `model` | `string` | No | Boat model name or `"all"` |

#### Response Payload

```typescript
type InventoryTrendResponse = ApiResponse<{
  series: Array<{
    snapshot_date:   string;   // ISO 8601 date (YYYY-MM-DD)
    active_listings: number;   // Tier 1: count of active listings on that snapshot date
  }>;
}>;
```

#### Notes
- Each element in `series` corresponds to one scrape snapshot date within the requested window.
- Consumer renders as a continuous line chart, interpolating between scrape dates.

#### Example Request
```
GET /api/v1/inventory/trend?time_range=l12m&inventory_type=combined&make=all
```

---

#### 3. `GET /api/v1/inventory/velocity`

Returns the Inventory & Velocity table: per model-year row with DOM, active units, boats sold, and momentum classification.

#### Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `time_range` | `TimeRange` | Yes | Window for sold and DOM calculations |
| `inventory_type` | `InventoryType` | No | Default: `combined` |
| `make` | `string` | No | Manufacturer name or `"all"` |
| `state` | `string` | No | 2-letter state code or `"all"` |

#### Response Payload

```typescript
type InventoryVelocityResponse = ApiResponse<{
  rows: Array<{
    model_year:           string;          // e.g. "2026 Supra SL450"
    manufacturer:         string;
    model:                string;
    year:                 number;
    avg_days_on_market:   number;          // Tier 1: avg(avg_dom)
    dom_velocity_label:   DomVelocityLabel; // Tier 2: classify avg_dom into velocity bucket
    active_units:         number;          // Tier 1: sum(active_listings)
    boats_sold:           number;          // Tier 1: sum of estimated sales over the requested time_range window
    momentum:             MomentumLabel;   // Tier 2: derived from DOM trend vs prior period
  }>;
}>;
```

#### Momentum Derivation (Tier 2 operation: `momentum_classify`)
Compares `avg_days_on_market` for the current window against the prior equivalent window:
- DOM decreased >10%: `"Accelerating"`
- DOM within ±10%: `"Stable"`  
- DOM increased >10%: `"Slowing"`

---


---

### Pricing Tab

Endpoints serving the **Pricing** page: headline price KPIs, avg days on market by price tier, listings by price tier, and the Model Price Efficiency table.

#### 1. `GET /api/v1/pricing/summary`

Returns headline KPI cards for the Pricing tab.

#### Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `time_range` | `TimeRange` | Yes | Window for price averaging |
| `inventory_type` | `InventoryType` | No | Default: `combined` |
| `make` | `string` | No | Manufacturer name or `"all"` |
| `model` | `string` | No | Boat model or `"all"` |

#### Response Payload

```typescript
type PricingSummaryResponse = ApiResponse<{
  avg_list_price:           number;   // Tier 1: avg(avg_list_price) weighted by active_listings
  median_list_price:        number;   // Tier 1: weighted median of median_list_price rows
  mom_price_change_pct:     number;   // Tier 2: (current_month_avg - prior_month_avg) / prior_month_avg * 100
  top_selling_band: {
    band:        PriceBand;           // Tier 2: price band with highest boats_sold in window
    band_label:  string;              // e.g. "$140–160k"
    units_sold:  number;              // Tier 1: sum of boats_sold for winning band
  };
}>;
```

#### Notes
- `mom_price_change_pct` compares the most recently completed calendar month to the one before it, regardless of the `time_range` filter. This is always calendar-month-to-calendar-month.
- `top_selling_band` requires the API to group estimated sales by price band and select the mode — a Tier 2 `top_band` operation.

---

#### 2. `GET /api/v1/pricing/dom-by-price-tier`

Returns the Avg Days on Market by Price Tier bar chart data.

#### Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `time_range` | `TimeRange` | Yes | Averaging window |
| `inventory_type` | `InventoryType` | No | Default: `combined` |
| `make` | `string` | No | Manufacturer name or `"all"` |
| `model` | `string` | No | Boat model or `"all"` |

#### Response Payload

```typescript
type DomByPriceTierResponse = ApiResponse<{
  bands: Array<{
    band:               PriceBand;
    band_label:         string;          // display string e.g. "$80–100k"
    avg_days_on_market: number;          // Tier 1: avg(avg_dom) for listings in this price band
    velocity_label:     DomVelocityLabel; // Tier 2: classify avg_dom
  }>;
}>;
```

#### Notes
- Six bands always returned, even if a band has zero listings (return `avg_days_on_market: 0`).
- Price band assignment is derived from `avg_list_price` at the source row level before aggregation.

---

#### 3. `GET /api/v1/pricing/listings-by-price-tier`

Returns the Listings by Price Tier horizontal bar chart data.

#### Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `time_range` | `TimeRange` | Yes | Active window |
| `inventory_type` | `InventoryType` | No | Default: `combined` |
| `make` | `string` | No | Manufacturer name or `"all"` |
| `model` | `string` | No | Boat model or `"all"` |

#### Response Payload

```typescript
type ListingsByPriceTierResponse = ApiResponse<{
  bands: Array<{
    band:       PriceBand;
    band_label: string;
    listings:   number;     // Tier 1: sum(active_listings) for rows in this price band
  }>;
}>;
```

---

#### 4. `GET /api/v1/pricing/model-efficiency`

Returns the Model Price Efficiency table: per model-year rows with price, band, DOM, and listing count.

#### Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `time_range` | `TimeRange` | Yes | Window for averaging |
| `inventory_type` | `InventoryType` | No | Default: `combined` |
| `make` | `string` | No | Manufacturer name or `"all"` |
| `model` | `string` | No | Boat model or `"all"` (free-text search on consumer side) |

#### Response Payload

```typescript
type ModelEfficiencyResponse = ApiResponse<{
  rows: Array<{
    rank:                 number;
    model_year:           string;        // e.g. "2021 Centurion Ri235"
    manufacturer:         string;
    model:                string;
    year:                 number;
    avg_list_price:       number;        // Tier 1: avg(avg_list_price)
    price_band_low:       number;        // Tier 2: 10th percentile of list prices in window
    price_band_high:      number;        // Tier 2: 90th percentile of list prices in window
    price_band_label:     string;        // e.g. "$73k–$85k"
    avg_days_on_market:   number;        // Tier 1: avg(avg_dom)
    dom_velocity_label:   DomVelocityLabel;
    listings:             number;        // Tier 1: sum(active_listings)
  }>;
}>;
```

#### Notes
- Ranked by `avg_days_on_market` ascending (fastest movers first).
- `price_band_low` / `price_band_high` are Tier 2 derived via `percentile_range` operation against listing price distributions, not the fixed price tier bands.
- Consumer implements free-text search client-side against `model_year` field.

---


---

### Regional Tab

Endpoints serving the **Regional** page: headline market KPIs, state market map data, state overview table, and market leaders leaderboard.

#### 1. `GET /api/v1/regional/summary`

Returns headline KPI cards for the Regional tab.

#### Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `time_range` | `TimeRange` | Yes | Window for all metrics |
| `inventory_type` | `InventoryType` | No | Default: `combined` |
| `make` | `string` | No | Manufacturer name or `"all"` |
| `model` | `string` | No | Boat model name or `"all"` |
| `state` | `string` | No | 2-letter state code or `"all"` |

#### Response Payload

```typescript
type RegionalSummaryResponse = ApiResponse<{
  national_avg_dom:     number;     // Tier 1: avg(avg_dom) across all states

  fastest_market: {
    state:              string;     // 2-letter code
    state_name:         string;
    avg_dom:            number;
    pct_vs_national:    number;     // Tier 2: (national_avg_dom - state_dom) / national_avg_dom * 100 (positive = faster)
  };

  slowest_market: {
    state:              string;
    state_name:         string;
    avg_dom:            number;
    pct_vs_national:    number;     // Tier 2: (state_dom - national_avg_dom) / national_avg_dom * 100 (positive = slower)
  };

  top_growth_state: {
    state:              string;
    state_name:         string;
    yoy_supply_change_pct: number;  // Tier 2: (current_active - prior_year_active) / prior_year_active * 100
  };

  sales_trends: {
    states_rising:      number;     // Tier 2: count of states where boats_sold > prior period
    states_falling:     number;     // Tier 2: count of states where boats_sold < prior period
  };
}>;
```

---

#### 2. `GET /api/v1/regional/state-overview`

Returns the State Market Overview table and map data — one row per state.

#### Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `time_range` | `TimeRange` | Yes | Window for all metrics |
| `inventory_type` | `InventoryType` | No | Default: `combined` |
| `make` | `string` | No | Manufacturer name or `"all"` |
| `model` | `string` | No | Boat model name or `"all"` |

#### Response Payload

```typescript
type RegionalStateOverviewResponse = ApiResponse<{
  national_total_boats_sold: number;    // Tier 1: sum across all states — used for pct_market
  rows: Array<{
    state:              string;         // 2-letter code
    state_name:         string;
    listings:           number;         // Tier 1: sum(active_listings)
    avg_days_on_market: number;         // Tier 1: avg(avg_dom)
    dom_velocity_label: DomVelocityLabel;
    boats_sold:         number;         // Tier 1: sum of estimated sales over the requested time_range window
    pct_market:         number;         // Tier 2: state boats_sold / national_total * 100
    avg_list_price:     number;         // Tier 1: avg(avg_list_price)
  }>;
}>;
```

#### Notes
- All states with data in the window are returned, sorted by `boats_sold` descending by default.
- Consumer renders both the choropleth map (using `avg_dom` or `avg_list_price` per selected metric) and the sortable table from this single payload.
- `dom_velocity_label` color-codes the DOM value in the table (green / yellow / orange / red).

---

#### 3. `GET /api/v1/regional/market-leaders`

Returns the State Market Leaders leaderboard — top and bottom states by boats sold.

#### Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `time_range` | `TimeRange` | Yes | Window for sales count |
| `inventory_type` | `InventoryType` | No | Default: `combined` |
| `make` | `string` | No | Manufacturer name or `"all"` |
| `model` | `string` | No | Boat model name or `"all"` |
| `top_n` | `number` | No | Number of top/bottom states to return. Default: `5` |

#### Response Payload

```typescript
type RegionalMarketLeadersResponse = ApiResponse<{
  top_states: Array<{
    rank:           number;
    state:          string;
    state_name:     string;
    boats_sold:     number;     // Tier 1: sum of estimated sales
    listings:       number;     // Tier 1: sum(active_listings)
  }>;
  bottom_states: Array<{
    rank:           number;
    state:          string;
    state_name:     string;
    boats_sold:     number;
    listings:       number;
  }>;
}>;
```

---

## Error Responses

All error responses use the following envelope:

```typescript
type ApiError = {
  error: {
    code:    string;   // machine-readable e.g. "INVALID_PARAM", "NO_DATA", "INTERNAL"
    message: string;   // human-readable description
    field?:  string;   // offending parameter name, if applicable
  };
};
```

| HTTP Status | Code | Condition |
|-------------|------|-----------|
| 400 | `INVALID_PARAM` | Unknown filter key, invalid enum value, malformed date |
| 400 | `MISSING_PARAM` | Required parameter absent |
| 404 | `NO_DATA` | Valid filters but zero rows in requested window |
| 422 | `INSUFFICIENT_DATA` | Window too narrow for derived metrics (e.g. MoM needs 2 complete months) |
| 500 | `INTERNAL` | Unhandled server error |

---

## Config Registry Reference

### Input Registry (WHERE clause fragments)

```yaml
# query_param_registry.yaml
parameters:
  time_range:
    type: date_range
    sql_fragment: "date_key BETWEEN :date_from AND :date_to"
    binder: resolve_time_range   # code function that converts TimeRange enum to date pair
    required: true

  inventory_type:
    type: enum
    sql_fragment: "inventory_type = :inventory_type"
    values: [new, used, combined]
    omit_when: combined          # omit WHERE clause entirely when value is "combined"

  make:
    type: string
    sql_fragment: "manufacturer_key = :manufacturer_key"
    binder: resolve_make_to_key  # code function: name → dimension key lookup
    omit_when: "all"

  model:
    type: string
    sql_fragment: "boat_model_key = :boat_model_key"
    binder: resolve_model_to_key
    omit_when: "all"

  state:
    type: string
    sql_fragment: "state = :state"
    omit_when: "all"

  top_n:
    type: integer
    sql_fragment: "LIMIT :top_n"
    default: 5
```

### Output Registry — Tier 1 (Aggregations)

```yaml
# output_registry.yaml — tier 1
aggregations:
  active_listings:
    operation: sum
    source_column: active_listings

  boats_sold:
    operation: sum
    source_column: estimated_sales   # from fact_estimated_sale join; window defined by time_range parameter

  inventory_added:
    operation: sum
    source_column: new_listings_today

  avg_days_on_market:
    operation: weighted_avg
    value_column: avg_dom
    weight_column: active_listings

  avg_list_price:
    operation: weighted_avg
    value_column: avg_list_price
    weight_column: active_listings

  median_list_price:
    operation: weighted_median
    value_column: median_list_price
    weight_column: active_listings

  dom_bucket_0_7:
    operation: sum
    source_column: dom_bucket_0_7

  dom_bucket_8_15:
    operation: sum
    source_column: dom_bucket_8_15

  dom_bucket_16_30:
    operation: sum
    source_column: dom_bucket_16_30

  dom_bucket_31_60:
    operation: sum
    source_column: dom_bucket_31_60

  dom_bucket_60_plus:
    operation: sum
    source_column: dom_bucket_60_plus

  listings_by_band:
    operation: sum_group
    source_column: active_listings
    group_by: price_band            # derived column from avg_list_price bucketing
```

### Output Registry — Tier 2 (Derived Metrics)

```yaml
# output_registry.yaml — tier 2
derived:
  pct_aging_past_30d:
    operation: ratio_pct
    numerator:   [dom_bucket_31_60, dom_bucket_60_plus]   # summed
    denominator: active_listings

  mom_price_change_pct:
    operation: mom_delta_pct
    source_field: avg_list_price
    # always uses completed calendar months regardless of time_range filter

  pct_vs_national:
    operation: pct_vs_reference
    subject_field: avg_days_on_market
    reference: national_avg_dom
    direction: lower_is_faster

  pct_market:
    operation: ratio_pct
    numerator:   boats_sold        # for this state; window-scoped by time_range
    denominator: national_total_boats_sold

  yoy_supply_change_pct:
    operation: yoy_delta_pct
    source_field: active_listings

  momentum:
    operation: momentum_classify
    source_field: avg_days_on_market
    prior_window: same_duration_prior_period
    thresholds:
      accelerating: -0.10   # DOM decreased >10%
      slowing:      +0.10   # DOM increased >10%

  dom_velocity_label:
    operation: threshold_classify
    source_field: avg_days_on_market
    buckets:
      Fast:      [0, 15]
      Healthy:   [15, 22]
      Slow:      [22, 30]
      Very_Slow: [30, null]

  top_selling_band:
    operation: top_group
    source_field: boats_sold
    group_by: price_band

  price_band_range:
    operation: percentile_range
    source_field: avg_list_price
    low_pct:  10
    high_pct: 90
```

---

## Versioning & Changelog

| Version | Date | Notes |
|---------|------|-------|
| 1.0.0-draft | 2026-05-15 | Initial contract — Inventory, Pricing, Regional tabs |
| 1.1.0-draft | 2026-05-15 | Auth moved to dedicated middleware section; explicitly excluded from variadic parameter registry |
| 1.2.0-draft | 2026-05-15 | Renamed `boats_sold_t30`
| 1.3.0-draft | 2026-05-15 | Added tab subheaders
| 1.4.0-draft | 2026-05-15 | Added `model` parameter to `GET /api/v1/regional/summary` |
| 1.5.0-draft | 2026-05-15 | Added `model` parameter to `GET /api/v1/regional/state-overview` |
| 1.6.0-draft | 2026-05-15 | Added `model` parameter to `GET /api/v1/regional/market-leaders` | (General, Inventory Tab, Pricing Tab, Regional Tab); endpoints grouped and renumbered within each tab section | → `boats_sold` across all endpoints and registry entries; value is always scoped to the caller-supplied `time_range` parameter |

*Dealers tab endpoints not included in this version — pending UX specification.*
