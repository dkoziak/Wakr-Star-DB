"""
Canned mock rows for every endpoint.

Uses types.SimpleNamespace so attributes are accessed by name, matching
how SQLAlchemy Core row objects work in the application code.
"""

from datetime import date
from types import SimpleNamespace as Row

SCRAPE_DATE = date(2026, 5, 13)

# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------

INV_STOCK = Row(
    active_listings=3201,
    avg_dom=23.0,
    b0=897,
    b1=1082,
    b2=762,
    b3=748,
    b4=0,
    last_scrape_date=SCRAPE_DATE,
)

# FLOW query: mart_daily_snapshot new_listings (inventory added)
INV_FLOW = Row(inventory_added=820)

# SALES query: fact_estimated_sale count
INV_BOATS_SOLD = Row(boats_sold=148)

TREND_ROWS = [
    Row(date_key=20260430, active_listings=3050, last_scrape_date=SCRAPE_DATE),
    Row(date_key=20260507, active_listings=3120, last_scrape_date=SCRAPE_DATE),
    Row(date_key=20260513, active_listings=3201, last_scrape_date=SCRAPE_DATE),
]

VELOCITY_CURRENT = [
    Row(
        manufacturer_key=1,
        boat_model_key=10,
        avg_dom=14.2,
        active_units=42,
        last_scrape_date=SCRAPE_DATE,
        make="Centurion",
        model="Fi23",
        model_year=2026,
        manufacturer_name="Centurion",
    ),
    Row(
        manufacturer_key=1,
        boat_model_key=11,
        avg_dom=28.5,
        active_units=19,
        last_scrape_date=SCRAPE_DATE,
        make="Centurion",
        model="Ri245",
        model_year=2025,
        manufacturer_name="Centurion",
    ),
]

# fact_estimated_sale count per model
VELOCITY_FLOW = [
    Row(manufacturer_key=1, boat_model_key=10, boats_sold=18),
    Row(manufacturer_key=1, boat_model_key=11, boats_sold=7),
]

VELOCITY_PRIOR = [
    Row(manufacturer_key=1, boat_model_key=10, avg_dom=17.0),   # improved → Accelerating
    Row(manufacturer_key=1, boat_model_key=11, avg_dom=25.0),   # worsened → Slowing
]

# ---------------------------------------------------------------------------
# Pricing
# ---------------------------------------------------------------------------

PRICE_STOCK = Row(
    avg_list_price=142500.0,
    median_list_price=136000.0,
    last_scrape_date=SCRAPE_DATE,
)

MPT_ROW = Row(
    mom_price_change_pct=-0.041,
    top_selling_band_low=140000.0,
    top_selling_band_high=None,
    top_selling_band_units=134,
)

DOM_BY_BAND = Row(
    dom_under_60k_w=0.0,    cnt_under_60k=0,
    dom_60_80k_w=6594.0,    cnt_60_80k=210,
    dom_80_100k_w=13682.0,  cnt_80_100k=618,
    dom_100_120k_w=17644.0, cnt_100_120k=891,
    dom_120_140k_w=12851.0, cnt_120_140k=743,
    dom_over_140k_w=17959.0,cnt_over_140k=733,
    last_scrape_date=SCRAPE_DATE,
)

LISTINGS_BY_BAND = Row(
    under_60k=12,
    b60_80k=204,
    b80_100k=618,
    b100_120k=891,
    b120_140k=743,
    over_140k=733,
    last_scrape_date=SCRAPE_DATE,
)

MODEL_EFF_ROWS = [
    Row(
        manufacturer_key=1, boat_model_key=10,
        avg_list_price=79500.0,
        price_band_low=68000.0, price_band_high=91000.0,
        avg_dom=12.4,
        listings=38,
        last_scrape_date=SCRAPE_DATE,
        make="Centurion", model="Ri235", model_year=2021,
        manufacturer_name="Centurion",
    ),
    Row(
        manufacturer_key=1, boat_model_key=11,
        avg_list_price=119800.0,
        price_band_low=108000.0, price_band_high=132000.0,
        avg_dom=21.7,
        listings=55,
        last_scrape_date=SCRAPE_DATE,
        make="Centurion", model="Ri245", model_year=2024,
        manufacturer_name="Centurion",
    ),
]

# ---------------------------------------------------------------------------
# Regional
# ---------------------------------------------------------------------------

STATE_ROWS = [
    Row(state="FL", avg_dom=21.3, active_listings=487, last_scrape_date=SCRAPE_DATE),
    Row(state="TX", avg_dom=14.9, active_listings=412, last_scrape_date=SCRAPE_DATE),
    Row(state="CA", avg_dom=26.1, active_listings=389, last_scrape_date=SCRAPE_DATE),
]

TREND_REGIONAL = [
    Row(state="TX", yoy_supply_change_pct=0.091, sales_trend_direction="Rising"),
    Row(state="FL", yoy_supply_change_pct=0.032, sales_trend_direction="Stable"),
    Row(state="CA", yoy_supply_change_pct=-0.015, sales_trend_direction="Falling"),
]

STATE_STOCK_ROWS = [
    Row(state="FL", listings=487, avg_dom=21.3, avg_list_price=128400.0, last_scrape_date=SCRAPE_DATE),
    Row(state="TX", listings=412, avg_dom=14.9, avg_list_price=119800.0, last_scrape_date=SCRAPE_DATE),
    Row(state="CA", listings=389, avg_dom=26.1, avg_list_price=134200.0, last_scrape_date=SCRAPE_DATE),
]

# fact_estimated_sale count per state
STATE_FLOW_ROWS = [
    Row(state="FL", boats_sold=226),
    Row(state="TX", boats_sold=198),
    Row(state="CA", boats_sold=174),
]

LEADER_FLOW_ROWS = [
    Row(state="FL", boats_sold=226),
    Row(state="TX", boats_sold=198),
    Row(state="CA", boats_sold=174),
    Row(state="AK", boats_sold=2),
    Row(state="VT", boats_sold=4),
    Row(state="ND", boats_sold=5),
]

LEADER_LISTING_ROWS = [
    Row(state="FL", listings=487, last_scrape_date=SCRAPE_DATE),
    Row(state="TX", listings=412, last_scrape_date=SCRAPE_DATE),
    Row(state="CA", listings=389, last_scrape_date=SCRAPE_DATE),
    Row(state="AK", listings=7,   last_scrape_date=SCRAPE_DATE),
    Row(state="VT", listings=12,  last_scrape_date=SCRAPE_DATE),
    Row(state="ND", listings=14,  last_scrape_date=SCRAPE_DATE),
]
