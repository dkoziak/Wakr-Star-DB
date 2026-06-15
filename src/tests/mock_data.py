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

# ---------------------------------------------------------------------------
# Pagination test data — 5 rows per paginated endpoint for meaningful
# limit/offset combinations.  Sorted values are noted so test assertions
# can be written against a known order without re-running sort logic.
# ---------------------------------------------------------------------------

# Velocity: 5 rows; after sort by avg_dom asc the order is:
#   [0] Fi23 14.2  [1] Ri245 28.5  [2] SL450 35.1  [3] 230Surf 47.8  [4] G23 65.3
VELOCITY_CURRENT_MANY = [
    Row(manufacturer_key=1, boat_model_key=10, avg_dom=14.2, active_units=42,
        last_scrape_date=SCRAPE_DATE, make="Centurion", model="Fi23",    model_year=2026, manufacturer_name="Centurion"),
    Row(manufacturer_key=1, boat_model_key=11, avg_dom=28.5, active_units=19,
        last_scrape_date=SCRAPE_DATE, make="Centurion", model="Ri245",   model_year=2025, manufacturer_name="Centurion"),
    Row(manufacturer_key=2, boat_model_key=20, avg_dom=35.1, active_units=31,
        last_scrape_date=SCRAPE_DATE, make="Supra",     model="SL450",   model_year=2024, manufacturer_name="Supra"),
    Row(manufacturer_key=3, boat_model_key=30, avg_dom=47.8, active_units=14,
        last_scrape_date=SCRAPE_DATE, make="Malibu",    model="230 Surf",model_year=2023, manufacturer_name="Malibu"),
    Row(manufacturer_key=4, boat_model_key=40, avg_dom=65.3, active_units=8,
        last_scrape_date=SCRAPE_DATE, make="Nautique",  model="G23",     model_year=2022, manufacturer_name="Nautique"),
]

VELOCITY_FLOW_MANY = [
    Row(manufacturer_key=1, boat_model_key=10, boats_sold=18),
    Row(manufacturer_key=1, boat_model_key=11, boats_sold=7),
    Row(manufacturer_key=2, boat_model_key=20, boats_sold=12),
    Row(manufacturer_key=3, boat_model_key=30, boats_sold=5),
    Row(manufacturer_key=4, boat_model_key=40, boats_sold=2),
]

VELOCITY_PRIOR_MANY = [
    Row(manufacturer_key=1, boat_model_key=10, avg_dom=17.0),
    Row(manufacturer_key=1, boat_model_key=11, avg_dom=25.0),
    Row(manufacturer_key=2, boat_model_key=20, avg_dom=33.0),
    Row(manufacturer_key=3, boat_model_key=30, avg_dom=50.0),
    Row(manufacturer_key=4, boat_model_key=40, avg_dom=60.0),
]

# Model efficiency: 5 rows; after sort by avg_dom asc the order is:
#   rank1 Ri235 12.4  rank2 Ri245 21.7  rank3 SL450 31.2  rank4 230Surf 43.8  rank5 G23 58.1
MODEL_EFF_ROWS_MANY = [
    Row(manufacturer_key=1, boat_model_key=10, avg_list_price=79500.0,
        price_band_low=68000.0,  price_band_high=91000.0,  avg_dom=12.4, listings=38,
        last_scrape_date=SCRAPE_DATE, make="Centurion", model="Ri235",    model_year=2021, manufacturer_name="Centurion"),
    Row(manufacturer_key=1, boat_model_key=11, avg_list_price=119800.0,
        price_band_low=108000.0, price_band_high=132000.0, avg_dom=21.7, listings=55,
        last_scrape_date=SCRAPE_DATE, make="Centurion", model="Ri245",    model_year=2024, manufacturer_name="Centurion"),
    Row(manufacturer_key=2, boat_model_key=20, avg_list_price=95000.0,
        price_band_low=85000.0,  price_band_high=105000.0, avg_dom=31.2, listings=27,
        last_scrape_date=SCRAPE_DATE, make="Supra",     model="SL450",    model_year=2023, manufacturer_name="Supra"),
    Row(manufacturer_key=3, boat_model_key=30, avg_list_price=88000.0,
        price_band_low=78000.0,  price_band_high=98000.0,  avg_dom=43.8, listings=16,
        last_scrape_date=SCRAPE_DATE, make="Malibu",    model="230 Surf", model_year=2022, manufacturer_name="Malibu"),
    Row(manufacturer_key=4, boat_model_key=40, avg_list_price=142000.0,
        price_band_low=130000.0, price_band_high=155000.0, avg_dom=58.1, listings=9,
        last_scrape_date=SCRAPE_DATE, make="Nautique",  model="G23",      model_year=2024, manufacturer_name="Nautique"),
]

# State overview: 5 states; after sort by boats_sold desc the order is:
#   [0] FL 226  [1] TX 198  [2] CA 174  [3] WA 95  [4] TN 67
#   national_total_boats_sold = 760
STATE_STOCK_MANY = [
    Row(state="FL", listings=487, avg_dom=21.3, avg_list_price=128400.0, last_scrape_date=SCRAPE_DATE),
    Row(state="TX", listings=412, avg_dom=14.9, avg_list_price=119800.0, last_scrape_date=SCRAPE_DATE),
    Row(state="CA", listings=389, avg_dom=26.1, avg_list_price=134200.0, last_scrape_date=SCRAPE_DATE),
    Row(state="WA", listings=187, avg_dom=18.4, avg_list_price=121000.0, last_scrape_date=SCRAPE_DATE),
    Row(state="TN", listings=143, avg_dom=23.7, avg_list_price=115400.0, last_scrape_date=SCRAPE_DATE),
]

STATE_FLOW_MANY = [
    Row(state="FL", boats_sold=226),
    Row(state="TX", boats_sold=198),
    Row(state="CA", boats_sold=174),
    Row(state="WA", boats_sold=95),
    Row(state="TN", boats_sold=67),
]
