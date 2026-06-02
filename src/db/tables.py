"""
SQLAlchemy Core table definitions for the Wakr Data Lake.
Only the tables queried by the API layer are defined here.
"""

from sqlalchemy import (
    BigInteger,
    Boolean,
    CHAR,
    Column,
    Date,
    Integer,
    MetaData,
    Numeric,
    SmallInteger,
    String,
    Table,
    Text,
)

metadata = MetaData()

# ---------------------------------------------------------------------------
# Dimensions
# ---------------------------------------------------------------------------

dim_manufacturer = Table(
    "dim_manufacturer",
    metadata,
    Column("manufacturer_key", Integer, primary_key=True),
    Column("l2_gear_brand_id", Integer, nullable=True),
    Column("manufacturer_name", String(100)),
    Column("is_wakr_partner", Boolean),
    Column("slug", String(200), nullable=True),
    Column("country_of_origin", String(100), nullable=True),
    Column("is_active", Boolean),
    Column("brand_tier_key", Integer, nullable=True),
)

dim_boat_model = Table(
    "dim_boat_model",
    metadata,
    Column("boat_model_key", Integer, primary_key=True),
    Column("l2_boats_model_id", Integer, nullable=True),
    Column("manufacturer_key", Integer),
    Column("make", String(100)),
    Column("model", String(200)),
    Column("model_year", SmallInteger),
    Column("boat_type", String(50)),
    Column("hull_length_ft", Numeric(5, 2)),
    Column("base_engine_hp", SmallInteger),
    Column("base_tower_included", Boolean),
    Column("base_ballast_lbs", Integer),
    Column("msrp", Numeric(10, 2)),
    Column("is_active", Boolean),
)

dim_geography = Table(
    "dim_geography",
    metadata,
    Column("geo_key", Integer, primary_key=True),
    Column("zip", String(10)),
    Column("city", String(100)),
    Column("county", String(100)),
    Column("state", CHAR(2)),
    Column("state_name", String(50)),
    Column("region", String(50)),
    Column("dma", String(100)),
    Column("lat", Numeric(9, 6)),
    Column("lon", Numeric(9, 6)),
)

dim_date = Table(
    "dim_date",
    metadata,
    Column("date_key", Integer, primary_key=True),
    Column("calendar_date", Date),
    Column("year", SmallInteger),
    Column("quarter", SmallInteger),
    Column("month", SmallInteger),
    Column("week_of_year", SmallInteger),
    Column("day_of_week", SmallInteger),
    Column("season", String(20)),
    Column("is_weekend", Boolean),
)

# ---------------------------------------------------------------------------
# mart_daily_snapshot  — central analytics workhorse
# Grain: manufacturer_key / boat_model_key / state / inventory_type / date_key
# STOCK columns: do NOT SUM across days — use latest row or AVG
# FLOW  columns: safe to SUM across any window
# ---------------------------------------------------------------------------

mart_daily_snapshot = Table(
    "mart_daily_snapshot",
    metadata,
    Column("date_key", Integer),
    Column("manufacturer_key", Integer),
    Column("boat_model_key", Integer, nullable=True),   # NULL = make-level rollup row
    Column("state", CHAR(2), nullable=True),            # NULL = all-states rollup row
    Column("inventory_type", String(10)),               # 'New' | 'Used'
    # --- STOCK ---
    Column("active_listings", Integer),
    Column("avg_list_price", Numeric(10, 2)),
    Column("median_list_price", Numeric(10, 2)),
    Column("avg_dom", Numeric(6, 2)),
    Column("dom_bucket_0_7", Integer),
    Column("dom_bucket_8_15", Integer),
    Column("dom_bucket_16_30", Integer),
    Column("dom_bucket_31_60", Integer),
    Column("dom_bucket_60_plus", Integer),
    Column("min_list_price", Numeric(10, 2)),
    Column("max_list_price", Numeric(10, 2)),
    Column("listing_count_band_under_60k", Integer),
    Column("listing_count_band_60_80k", Integer),
    Column("listing_count_band_80_100k", Integer),
    Column("listing_count_band_100_120k", Integer),
    Column("listing_count_band_120_140k", Integer),
    Column("listing_count_band_over_140k", Integer),
    Column("avg_dom_band_under_60k", Numeric(6, 2)),
    Column("avg_dom_band_60_80k", Numeric(6, 2)),
    Column("avg_dom_band_80_100k", Numeric(6, 2)),
    Column("avg_dom_band_100_120k", Numeric(6, 2)),
    Column("avg_dom_band_120_140k", Numeric(6, 2)),
    Column("avg_dom_band_over_140k", Numeric(6, 2)),
    # --- FLOW ---
    Column("new_listings", Integer),
    Column("removed_listings", Integer),
    Column("price_reduced_listings", Integer),
    # --- DERIVED (pre-classified at mart refresh) ---
    Column("dom_status", String(20)),
    Column("sell_through_rate", Numeric(6, 4)),
    Column("days_supply", Numeric(8, 2)),
    Column("is_partial_scrape_day", Boolean),
    Column("last_scrape_date", Date),
)

# ---------------------------------------------------------------------------
# mart_pricing_trends  — monthly grain; MoM metrics and top-selling band
# ---------------------------------------------------------------------------

mart_pricing_trends = Table(
    "mart_pricing_trends",
    metadata,
    Column("month_key", Integer),
    Column("manufacturer_key", Integer),
    Column("boat_model_key", Integer),
    Column("geo_key", Integer),
    Column("avg_list_price", Numeric(10, 2)),
    Column("avg_list_price_vs_market_pct", Numeric(7, 4)),
    Column("median_list_price", Numeric(10, 2)),
    Column("median_list_price_vs_market_pct", Numeric(7, 4)),
    Column("mom_price_change_pct", Numeric(7, 4)),
    Column("mom_price_change_pct_vs_market_pct", Numeric(7, 4)),
    Column("top_selling_band_low", Numeric(10, 2)),
    Column("top_selling_band_high", Numeric(10, 2)),
    Column("top_selling_band_units", Integer),
    Column("top_selling_band_vs_market_pct", Numeric(7, 4)),
    Column("price_band_label", String(30)),
    Column("pct_listings_with_price_cut", Numeric(6, 4)),
    Column("discount_pressure_pct", Numeric(6, 4)),
    Column("is_partial_month", Boolean),
)

# ---------------------------------------------------------------------------
# fact_estimated_sale  — one row per inferred sale event
# Grain: one sale per listing (boat_instance) when the listing disappears
# ---------------------------------------------------------------------------

fact_estimated_sale = Table(
    "fact_estimated_sale",
    metadata,
    Column("estimated_sale_key", BigInteger, primary_key=True),
    Column("date_key", Integer, nullable=False),          # YYYYMMDD of inferred sale
    Column("manufacturer_key", Integer, nullable=False),
    Column("boat_model_key", Integer, nullable=True),
    Column("state", CHAR(2), nullable=True),
    Column("inventory_type", String(10), nullable=False), # 'New' | 'Used'
    Column("estimated_sale_price", Numeric(10, 2), nullable=True),
    Column("days_on_market", Integer, nullable=True),
)

# ---------------------------------------------------------------------------
# mart_regional_summary  — monthly grain; YoY, sales trend direction
# ---------------------------------------------------------------------------

mart_regional_summary = Table(
    "mart_regional_summary",
    metadata,
    Column("month_key", Integer),
    Column("state", CHAR(2)),
    Column("manufacturer_key", Integer),
    Column("boat_model_key", Integer),
    Column("avg_dom_vs_national_pct", Numeric(7, 4)),
    Column("boats_sold_t30_vs_market_pct", Numeric(7, 4)),
    Column("pct_market", Numeric(6, 4)),
    Column("avg_price_vs_market_pct", Numeric(7, 4)),
    Column("yoy_supply_change_pct", Numeric(7, 4)),
    Column("dom_status", String(20)),
    Column("sales_trend_direction", String(10)),
    Column("fastest_market_state", CHAR(2)),
    Column("slowest_market_state", CHAR(2)),
    Column("is_partial_month", Boolean),
)
