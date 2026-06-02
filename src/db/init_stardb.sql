-- Wakr Star DB — schema bootstrap
-- Run once on first container startup; safe to re-run (all CREATE IF NOT EXISTS).

CREATE TABLE IF NOT EXISTS dim_date (
    date_key        INT PRIMARY KEY,
    calendar_date   DATE          NOT NULL,
    year            SMALLINT,
    quarter         SMALLINT,
    month           SMALLINT,
    week_of_year    SMALLINT,
    day_of_week     SMALLINT,
    season          VARCHAR(20),
    is_weekend      BOOLEAN
);

CREATE TABLE IF NOT EXISTS dim_geography (
    geo_key         SERIAL PRIMARY KEY,
    zip             VARCHAR(10),
    city            VARCHAR(100),
    county          VARCHAR(100),
    state           CHAR(2),
    state_name      VARCHAR(50),
    region          VARCHAR(50),
    dma             VARCHAR(100),
    lat             DECIMAL(9,6),
    lon             DECIMAL(9,6)
);

CREATE TABLE IF NOT EXISTS dim_manufacturer (
    manufacturer_key    SERIAL PRIMARY KEY,
    directus_brand_id   INT,
    manufacturer_name   VARCHAR(100),
    brand_tier_key      INT,
    is_wakr_partner     BOOLEAN,
    slug                VARCHAR(200),
    country_of_origin   VARCHAR(100),
    is_active           BOOLEAN
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_dim_manufacturer_directus_brand_id
    ON dim_manufacturer (directus_brand_id)
    WHERE directus_brand_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS dim_boat_model (
    boat_model_key      SERIAL PRIMARY KEY,
    directus_model_id   INT,
    manufacturer_key    INT REFERENCES dim_manufacturer (manufacturer_key),
    make                VARCHAR(100),
    model               VARCHAR(200),
    model_year          SMALLINT,
    boat_type           VARCHAR(50),
    hull_length_ft      DECIMAL(5,2),
    base_engine_hp      SMALLINT,
    base_tower_included BOOLEAN,
    base_ballast_lbs    INT,
    msrp                DECIMAL(10,2),
    is_active           BOOLEAN
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_dim_boat_model_directus_model_id
    ON dim_boat_model (directus_model_id)
    WHERE directus_model_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS mart_daily_snapshot (
    date_key                        INT,
    manufacturer_key                INT,
    boat_model_key                  INT,
    state                           CHAR(2),
    inventory_type                  VARCHAR(10),
    active_listings                 INT,
    avg_list_price                  NUMERIC(10,2),
    median_list_price               NUMERIC(10,2),
    avg_dom                         NUMERIC(6,2),
    dom_bucket_0_7                  INT,
    dom_bucket_8_15                 INT,
    dom_bucket_16_30                INT,
    dom_bucket_31_60                INT,
    dom_bucket_60_plus              INT,
    min_list_price                  NUMERIC(10,2),
    max_list_price                  NUMERIC(10,2),
    listing_count_band_under_60k    INT,
    listing_count_band_60_80k       INT,
    listing_count_band_80_100k      INT,
    listing_count_band_100_120k     INT,
    listing_count_band_120_140k     INT,
    listing_count_band_over_140k    INT,
    avg_dom_band_under_60k          NUMERIC(6,2),
    avg_dom_band_60_80k             NUMERIC(6,2),
    avg_dom_band_80_100k            NUMERIC(6,2),
    avg_dom_band_100_120k           NUMERIC(6,2),
    avg_dom_band_120_140k           NUMERIC(6,2),
    avg_dom_band_over_140k          NUMERIC(6,2),
    new_listings                    INT,
    removed_listings                INT,
    price_reduced_listings          INT,
    dom_status                      VARCHAR(20),
    sell_through_rate               NUMERIC(6,4),
    days_supply                     NUMERIC(8,2),
    is_partial_scrape_day           BOOLEAN,
    last_scrape_date                DATE
);

CREATE INDEX IF NOT EXISTS idx_mart_daily_snapshot_date_key
    ON mart_daily_snapshot (date_key);

CREATE TABLE IF NOT EXISTS fact_estimated_sale (
    estimated_sale_key  BIGSERIAL PRIMARY KEY,
    date_key            INT         NOT NULL,
    manufacturer_key    INT         NOT NULL,
    boat_model_key      INT,
    state               CHAR(2),
    inventory_type      VARCHAR(10) NOT NULL,
    estimated_sale_price NUMERIC(10,2),
    days_on_market      INT
);

CREATE TABLE IF NOT EXISTS mart_pricing_trends (
    month_key                           INT,
    manufacturer_key                    INT,
    boat_model_key                      INT,
    geo_key                             INT,
    avg_list_price                      NUMERIC(10,2),
    avg_list_price_vs_market_pct        NUMERIC(7,4),
    median_list_price                   NUMERIC(10,2),
    median_list_price_vs_market_pct     NUMERIC(7,4),
    mom_price_change_pct                NUMERIC(7,4),
    mom_price_change_pct_vs_market_pct  NUMERIC(7,4),
    top_selling_band_low                NUMERIC(10,2),
    top_selling_band_high               NUMERIC(10,2),
    top_selling_band_units              INT,
    top_selling_band_vs_market_pct      NUMERIC(7,4),
    price_band_label                    VARCHAR(30),
    pct_listings_with_price_cut         NUMERIC(6,4),
    discount_pressure_pct               NUMERIC(6,4),
    is_partial_month                    BOOLEAN
);

CREATE TABLE IF NOT EXISTS mart_regional_summary (
    month_key                       INT,
    state                           CHAR(2),
    manufacturer_key                INT,
    boat_model_key                  INT,
    avg_dom_vs_national_pct         NUMERIC(7,4),
    boats_sold_t30_vs_market_pct    NUMERIC(7,4),
    pct_market                      NUMERIC(6,4),
    avg_price_vs_market_pct         NUMERIC(7,4),
    yoy_supply_change_pct           NUMERIC(7,4),
    dom_status                      VARCHAR(20),
    sales_trend_direction           VARCHAR(10),
    fastest_market_state            CHAR(2),
    slowest_market_state            CHAR(2),
    is_partial_month                BOOLEAN
);
