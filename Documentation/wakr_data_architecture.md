# Wakr Data Lake — Data Architecture Reference

**Schema version:** v1.5.0 · Updated: 2026-04-02
**Pattern:** Star schema · Layers: Dimensions, Facts, Bridges, Marts

---

## Changelog

| Version | Date | Notes |
|---------|------|-------|
| v1.5.0 | 2026-04-02 | Floorplan financing analytics. Added `fact_floorplan_daily` (grain: floored unit × day; measures: `daily_carry_cost`, `cumulative_carry_cost`, `in_subsidy_window`, `curtailment_overdue_count`). Added `mart_floorplan_aging` (grain: manufacturer × aging bucket × month; metrics: `avg_days_on_floor`, `total_carry_cost_accrued`, `pct_past_subsidy_window`, `units_in_curtailment`, `curtailment_compliance_rate`). Added four floorplan columns to `mart_dealer_scorecard`: `total_floorplan_exposure`, `avg_carry_cost_per_unit_sold`, `curtailment_compliance_rate`, `out_of_trust_count`. Source data for all floorplan analytics lives in Layer 2 Central DB (`inventory_floorplan`, `floorplan_curtailment_events`, `dealer_floorplan_config`). |
| v1.4.0 | 2026-03-06 | Figma dashboard analytics audit. Added `dim_brand_tier` (price-based segment config table). Added `brand_tier_key` FK on `dim_manufacturer`. Added `state_name` to `dim_geography`. Added computed metric columns to all Phase-1 mart tables: `sell_through_rate`, `days_supply`, `mom_listing_change_pct` (`mart_inventory_summary`); `pct_listings_with_price_cut`, `discount_pressure_pct` (`mart_pricing_trends`); `dom_status`, `aging_risk_level` (`mart_time_on_market`); `demand_supply_ratio`, `momentum_status` [PENDING] (`mart_estimated_velocity`); `delta_week_units`, `market_share_pct` [PENDING] (`mart_dealer_scorecard`). `territory` on `dim_dealer` intentionally omitted — use `dim_geography.dma` as territory proxy. |
| v1.3.0 | 2026-03-05 | Added `dim_dealer_network` (multi-location dealer group rollup). Replaced single `manufacturer_key` FK on `dim_dealer` with `bridge_dealer_manufacturer` (many-to-many). Renamed configurable boat model fields to `base_*` to distinguish manufacturer spec from per-instance values. |
| v1.2.0 | 2026-03-04 | Initial JSON export. Split `dim_boat` into `dim_boat_model` (type template) and `dim_boat_instance` (physical unit). |

---

## Design Notes

- **Dealer locations vs. networks:** Each physical dealer location is a separate `dim_dealer` row. Roll up to dealer group via `dealer_network_key → dim_dealer_network`.
- **Multi-brand dealers:** Dealer-to-manufacturer affiliation is many-to-many via `bridge_dealer_manufacturer`. The `primary_manufacturer_key` on `dim_dealer` is a denormalized convenience FK for single-brand lookups only.
- **Boat model vs. instance fields:** `dim_boat_model.base_*` fields (`base_engine_hp`, `base_ballast_lbs`, `base_tower_included`) are the **factory-standard spec** for the model. Actual per-hull values are stored on `dim_boat_instance` and `bridge_listing_features`.
- **Dual grain FKs on facts:** All fact tables carry both `boat_key` (instance level) and `boat_model_key` (model level) to support aggregation at either grain without extra joins.
- **Source trust hierarchy:** `manufacturer_feed` > `dealer_feed` > `dtc_member` > `scrape`.
- **PII safety:** `dim_member` uses SHA-256 hashed IDs only — no PII in any fact table.
- **Partitioning:** `fact_listing_snapshot` is partitioned by `date_key` (month) + manufacturer prefix.
- **Price-based segmentation:** `dim_brand_tier` defines market segments (Entry/Mid/Premium) via `min_price`/`max_price` thresholds. Segment is resolved at query time by matching `listed_price` of new boats against these ranges.
- **Territory proxy:** `territory` on `dim_dealer` is intentionally not stored as a separate column — use `dim_geography.dma` (Nielsen DMA) as the dealer territory grouping.
- **Demand definition:** Demand = count of boats sold over the measurement period (`fact_estimated_sale`). No external signal required. `demand_supply_ratio = boats_sold_t30 / active_listings`.
- **Pending definitions:** `momentum_status` (Accelerating/Stable/Slowing) and `market_share_pct` require further user research before ETL implementation. Reserved placeholder columns exist in their respective marts.
- **Phase 2 tables** (`fact_member_activity`, `fact_marketplace_behavior`, `dim_competitor_brand`, `mart_member_usage`) are in development with early brand partners.

---

## Dimensions

### dim_date — SCD Type 0
Standard date spine. Shared across all fact tables.

| Column | Type | Notes |
|--------|------|-------|
| date_key | INT (PK) | |
| calendar_date | DATE | |
| year / quarter / month | SMALLINT | |
| week_of_year | SMALLINT | |
| day_of_week | SMALLINT | |
| season | VARCHAR(20) | |
| is_weekend | BOOLEAN | |

---

### dim_geography — SCD Type 1
Geographic hierarchy for regional analytics and location filtering.

| Column | Type | Notes |
|--------|------|-------|
| geo_key | INT (PK) | |
| zip | VARCHAR(10) | |
| city | VARCHAR(100) | |
| county | VARCHAR(100) | |
| state | CHAR(2) | Two-letter abbreviation |
| state_name | VARCHAR(50) | Full state name, e.g. "Florida" — required for Regional tab State column display |
| region | VARCHAR(50) | e.g. Southeast, Mountain West |
| dma | VARCHAR(100) | Nielsen DMA for media alignment; also serves as dealer territory proxy |
| lat / lon | DECIMAL(9,6) | |

---

### dim_brand_tier — SCD Type 1 *(NEW in v1.4.0)*
Structured configuration table defining price-based boat market segments. Each row defines a named tier with a price floor and optional ceiling. Segment for any given listing is resolved by matching `listed_price` (new boat) against `min_price`/`max_price` ranges at query time. Powers the **Segment Momentum** view on the Overview tab.

| Column | Type | Notes |
|--------|------|-------|
| brand_tier_key | INT (PK) | |
| tier_name | VARCHAR(50) | Entry \| Mid \| Premium |
| min_price | DECIMAL(10,2) | Minimum new-boat list price (inclusive) |
| max_price | DECIMAL(10,2) NULL | Maximum price (exclusive). NULL = no upper bound (top tier). |
| display_order | SMALLINT | Sort order for dashboard display (1 = lowest tier) |

---

### dim_dealer_network — SCD Type 1 *(NEW in v1.3.0)*
Dealer groups and multi-location networks. Provides group-level rollup for analytics.

| Column | Type | Notes |
|--------|------|-------|
| dealer_network_key | INT (PK) | |
| network_name | VARCHAR(200) | e.g. "Lake Powell Marine Group" |
| parent_company | VARCHAR(200) NULL | Corporate parent if applicable |
| network_type | VARCHAR(50) | Franchise \| Independent \| Corporate Chain |
| is_wakr_partner | BOOLEAN | |
| network_join_date | DATE NULL | |

---

### dim_dealer — SCD Type 2
Individual dealer locations. Each physical location is a separate row. Dealers may represent multiple manufacturers; all brand affiliations tracked via `bridge_dealer_manufacturer`. Use `dim_geography.dma` as the territory grouping for this dealer.

| Column | Type | Notes |
|--------|------|-------|
| dealer_key | INT (PK) | |
| dealer_id_external | VARCHAR(100) | Source system ID |
| dealer_name | VARCHAR(200) | |
| address / city / state / zip | VARCHAR | |
| geo_key | INT (FK→dim_geography) | |
| dealer_network_key | INT (FK→dim_dealer_network) NULL | Null for independent single-location dealers |
| primary_manufacturer_key | INT (FK→dim_manufacturer) NULL | Denormalized primary brand; full list in bridge_dealer_manufacturer |
| is_authorized | BOOLEAN | |
| is_wakr_partner | BOOLEAN | Enrolled in Dealer Listings product |
| network_join_date | DATE | |

---

### dim_manufacturer — SCD Type 1
Boat manufacturers / brands. Root of the boat type hierarchy.

| Column | Type | Notes |
|--------|------|-------|
| manufacturer_key | INT (PK) | |
| manufacturer_name | VARCHAR(100) | |
| brand_tier_key | INT (FK→dim_brand_tier) NULL | Segment tier for this manufacturer's primary product line *(replaces legacy `brand_tier` VARCHAR — v1.4.0)* |
| is_wakr_partner | BOOLEAN | |

---

### dim_source — SCD Type 0
Data provenance tracking. Enables source trust hierarchy filtering.

| Column | Type | Notes |
|--------|------|-------|
| source_key | INT (PK) | |
| source_name | VARCHAR(100) | e.g. BoatTrader, Dealer Feed, Manufacturer |
| source_type | VARCHAR(50) | Scrape \| API \| Manual \| Member |
| scrape_domain | VARCHAR(200) | |
| reliability_tier | VARCHAR(20) | High \| Medium \| Low |

---

### dim_member — SCD Type 2
DTC members registered on wakr.co. PII-safe — hashed IDs only.

| Column | Type | Notes |
|--------|------|-------|
| member_key | INT (PK) | |
| member_id_hashed | VARCHAR(64) | SHA-256 hash — no PII |
| geo_key | INT (FK→dim_geography) | |
| join_date | DATE | |
| skill_level | VARCHAR(50) | Beginner \| Intermediate \| Advanced |
| membership_tier | VARCHAR(50) | |

---

### dim_lake — SCD Type 1
Lakes and waterways where towboats are used. Unique to the watersports market — supports usage-pattern analytics.

| Column | Type | Notes |
|--------|------|-------|
| lake_key | INT (PK) | |
| lake_name | VARCHAR(200) | |
| state | CHAR(2) | |
| geo_key | INT (FK→dim_geography) | |
| surface_acres | INT | |
| lake_type | VARCHAR(50) | Reservoir \| Natural \| Private |

---

### dim_boat_model — SCD Type 1
The **type/template** dimension — one row per make/model/year. Represents the manufacturer's base product specification.  
`base_*` fields are factory-standard values for the model. Do not confuse with per-instance values (→ `dim_boat_instance`, `bridge_listing_features`).

| Column | Type | Notes |
|--------|------|-------|
| boat_model_key | INT (PK) | |
| manufacturer_key | INT (FK→dim_manufacturer) | |
| make / model | VARCHAR | |
| model_year | SMALLINT | |
| boat_type | VARCHAR(50) | Ski \| Wake \| Surf \| Crossover |
| hull_length_ft | DECIMAL(5,2) | **Model-defining** (from manufacturer) |
| engine_type | VARCHAR(100) | **Model-defining** engine family/series |
| base_engine_hp | SMALLINT | Factory standard HP — upgrades tracked on instance |
| base_tower_included | BOOLEAN | Standard tower presence — actual tracked on instance |
| base_ballast_lbs | INT | Factory standard ballast — actual tracked on instance |
| msrp | DECIMAL(10,2) | From manufacturer feed when available |

---

### dim_boat_instance — SCD Type 2
The **physical unit** dimension — one row per actual boat (VIN or surrogate). Many instances per model. Stores actual as-delivered/as-listed configuration.

| Column | Type | Notes |
|--------|------|-------|
| boat_key | INT (PK) | |
| boat_model_key | INT (FK→dim_boat_model) | |
| vin | VARCHAR(50) NULL | Nullable — deduplication uses make+model+year+hours+price-tolerance |
| is_new | BOOLEAN | |
| manufacture_date | DATE NULL | |
| current_hours | INT NULL | Updated as new listing data arrives |
| condition | VARCHAR(20) | Excellent \| Good \| Fair |
| color | VARCHAR(100) NULL | |
| actual_engine_hp | SMALLINT NULL | Null = assume base model spec |
| has_tower | BOOLEAN NULL | Actual presence; null = unknown |
| actual_ballast_lbs | INT NULL | Null = assume base model spec |
| dealer_key | INT (FK→dim_dealer) NULL | Last known dealer association |

---

### dim_competitor_brand — SCD Type 1 *(Phase 2)*
Competitor brands for competitive overlay analytics.

---

## Facts

### fact_listing_snapshot ⭐ — Phase 1
**Grain:** one row per listing per day  
**Partitioning:** date_key (month) + manufacturer prefix on boat_model_key

Core fact table. Backbone of pricing, time-on-market, and inventory level analytics.

**Foreign keys:** date_key, boat_key, boat_model_key, dealer_key (nullable), geo_key, source_key  
**Key measures:** listed_price, original_list_price, price_change_amount, days_on_market, is_new_listing, is_removed, mileage_hours

---

### fact_estimated_sale — Phase 1
**Grain:** one row per inferred sale event

A listing removed after active status is treated as a likely sale. `confidence_score` allows downstream analytics to discount low-confidence records.

**Foreign keys:** date_key, boat_key, boat_model_key, dealer_key (nullable), geo_key, source_key  
**Key measures:** final_listed_price, days_on_market, confidence_score, sale_type

---

### fact_listing_engagement — Phase 1
**Grain:** one row per listing per day (Wakr-hosted listings only)

Powers Dealer Performance Indicators, Model-Level Impressions, and Lead Activity Tracking.

**Foreign keys:** date_key, boat_key, boat_model_key, dealer_key  
**Key measures:** impressions, clicks, leads_generated, click_through_rate

---

### fact_floorplan_daily — Phase 1
**Grain:** one row per floored unit per day
**Source:** Layer 2 `inventory_floorplan` + `floorplan_curtailment_events` + `dealer_floorplan_config`

Daily snapshot of every active floorplan unit. Enables carry-cost analytics, manufacturer subsidy window analysis, and curtailment health scoring at both dealer and OEM grain.

**Foreign keys:** date_key, boat_key, boat_model_key, dealer_key, dealer_network_key
**Key measures:** days_on_floor, daily_carry_cost, cumulative_carry_cost, in_subsidy_window (BOOLEAN), floorplan_status, curtailment_overdue_count

**Carry cost formula:** `floored_amount * effective_rate / 365`; `daily_carry_cost = 0` while `in_subsidy_window = TRUE`

---

### fact_member_activity — Phase 2
**Grain:** one row per member activity event

Activity from wakr.co DTC members — boat ownership, lake visits, lessons, dealer touchpoints.

**Foreign keys:** date_key, member_key, boat_key (nullable), boat_model_key, dealer_key (nullable), lake_key (nullable)  
**Key measures:** activity_type, is_owner

---

### fact_marketplace_behavior — Phase 2
**Grain:** one row per marketplace event (anonymous sessions OK)

Browsing, comparison, and purchase events. Enables demand shift detection before inventory data reflects it.

**Foreign keys:** date_key, member_key (nullable), boat_model_key, geo_key  
**Key measures:** event_type (View \| Compare \| Save \| Mention \| Purchase), session_id

---

## Bridges

### bridge_dealer_manufacturer *(NEW in v1.3.0)*
Many-to-many affiliation between dealer locations and manufacturers. A dealer may be authorized for multiple brands. The `is_primary` flag identifies the dealer's dominant brand.

| Column | Type | Notes |
|--------|------|-------|
| dealer_key | INT (FK→dim_dealer) | |
| manufacturer_key | INT (FK→dim_manufacturer) | |
| is_primary | BOOLEAN | Dominant brand for this location |
| is_authorized | BOOLEAN | Manufacturer-confirmed authorization |
| authorization_type | VARCHAR(50) | Full \| Limited \| Service-Only |
| effective_date | DATE | |
| expiry_date | DATE NULL | |

---

### bridge_listing_features
Multi-valued listing features extracted from scrape text (tower type, ballast, electronics, etc.). One listing → many feature rows. Used for comparable listing matching in the Trade-In & Valuation Application.

| Column | Type | Notes |
|--------|------|-------|
| listing_id | VARCHAR(200) | |
| boat_model_key | INT (FK→dim_boat_model) | |
| feature_category | VARCHAR(100) | e.g. tower, ballast, electronics, upholstery |
| feature_value | VARCHAR(200) | |

---

## Marts (Physical Pre-Aggregated Tables)

All marts are implemented as **physical tables** populated by scheduled ETL/dbt jobs — not views. All marts support grouping by `dealer_key` (location) or `dealer_network_key` (group) for dealer analytics.

> Fields marked **[PENDING]** require user-approved definition before ETL implementation.

| Mart | Grain | Source Facts | Phase | Computed Columns |
|------|-------|-------------|-------|-----------------|
| mart_inventory_summary | make/model/region/week | snapshot + est_sale | 1 | `sell_through_rate`, `mom_listing_change_pct`, `days_supply` |
| mart_pricing_trends | make/model/region/month | fact_listing_snapshot | 1 | `pct_listings_with_price_cut`, `discount_pressure_pct` |
| mart_time_on_market | make/model/region/month | fact_listing_snapshot | 1 | `dom_status`, `aging_risk_level` |
| mart_dealer_scorecard | dealer/month | snapshot + engagement + est_sale + floorplan_daily | 1 | `delta_week_units`, `market_share_pct` [PENDING], `total_floorplan_exposure`, `avg_carry_cost_per_unit_sold`, `curtailment_compliance_rate`, `out_of_trust_count` |
| mart_estimated_velocity | make/model/region/month | est_sale + snapshot | 1 | `demand_supply_ratio`, `momentum_status` [PENDING] |
| mart_floorplan_aging | manufacturer/aging_bucket/month | fact_floorplan_daily | 1 | `avg_days_on_floor`, `total_carry_cost_accrued`, `pct_past_subsidy_window`, `units_in_curtailment`, `curtailment_compliance_rate` |
| mart_member_usage | lake/model/month | fact_member_activity | 2 | — |

### Computed Column Definitions

| Column | Mart | Formula / Logic |
|--------|------|-----------------|
| `sell_through_rate` | mart_inventory_summary | `units_sold / active_listings` for the period |
| `mom_listing_change_pct` | mart_inventory_summary | MoM % change in active listing count |
| `days_supply` | mart_inventory_summary | `active_listings / (boats_sold_t30 / 30.0)` |
| `pct_listings_with_price_cut` | mart_pricing_trends | Fraction of active listings where `price_change_amount < 0` |
| `discount_pressure_pct` | mart_pricing_trends | `avg((original_list_price - listed_price) / original_list_price)` for listings with price cuts |
| `dom_status` | mart_time_on_market | Fast (<15d) \| Healthy (15–22d) \| Slow (23–30d) \| Very Slow (30d+) |
| `aging_risk_level` | mart_time_on_market | Elevated \| Moderate \| Low — based on avg_dom vs configurable thresholds |
| `demand_supply_ratio` | mart_estimated_velocity | `boats_sold_t30 / active_listings` |
| `momentum_status` | mart_estimated_velocity | **[PENDING]** Accelerating \| Stable \| Slowing — definition TBD by user |
| `delta_week_units` | mart_dealer_scorecard | WoW change in units sold per dealer (requires weekly sub-aggregation) |
| `market_share_pct` | mart_dealer_scorecard | **[PENDING]** Dealer network share of total market listings per state — methodology TBD |
| `total_floorplan_exposure` | mart_dealer_scorecard | Sum of `floored_amount` for all active floorplan units at month end |
| `avg_carry_cost_per_unit_sold` | mart_dealer_scorecard | Total cumulative carry cost on sold units ÷ units sold that month |
| `curtailment_compliance_rate` | mart_dealer_scorecard / mart_floorplan_aging | `paid` curtailment events ÷ total due events for the period |
| `out_of_trust_count` | mart_dealer_scorecard | Count of units in `out_of_trust` status at month end |
| `avg_days_on_floor` | mart_floorplan_aging | Average `days_on_floor` across units in each aging bucket |
| `total_carry_cost_accrued` | mart_floorplan_aging | Sum of `cumulative_carry_cost` across all units in bucket |
| `pct_past_subsidy_window` | mart_floorplan_aging | Fraction of active units where `in_subsidy_window = FALSE` |
| `units_in_curtailment` | mart_floorplan_aging | Count of units with at least one `overdue` curtailment event |
