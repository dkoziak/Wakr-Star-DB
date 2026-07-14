"""
Seed the Star DB with test data sufficient to exercise every API endpoint.

Usage (from src/):
    python -c "from tests.seed_test_db import seed_test_db; seed_test_db()"

Connects via the STARDB_URL environment variable, replacing the asyncpg
driver with a plain postgresql:// URL that psycopg2 accepts.  Truncates
all Star DB tables with RESTART IDENTITY and inserts a consistent,
representative dataset.

Run this once before executing tests/test_live_payloads.py.
"""

import os
import re
from datetime import date, timedelta

import psycopg2
import psycopg2.extras


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _psycopg2_url(url: str) -> str:
    """Strip the SQLAlchemy driver name (e.g. +asyncpg) so psycopg2 accepts the URL."""
    return re.sub(r"postgresql\+\w+://", "postgresql://", url)


def _month_key(d: date) -> int:
    return int(d.strftime("%Y%m"))


def _date_key(d: date) -> int:
    return int(d.strftime("%Y%m%d"))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def seed_test_db(url: str | None = None) -> None:
    dsn = _psycopg2_url(url or os.environ["STARDB_URL"])
    conn = psycopg2.connect(dsn)
    conn.autocommit = False
    cur = conn.cursor()

    today = date.today()

    # ── Date keys scattered across l12m window ────────────────────────────────
    snapshot_dates = [
        today,
        today - timedelta(days=14),
        today - timedelta(days=30),
        today - timedelta(days=90),
        today - timedelta(days=180),
        today - timedelta(days=270),
        today - timedelta(days=364),
    ]
    snapshot_keys = [_date_key(d) for d in snapshot_dates]

    # ── Month keys: two completed calendar months ─────────────────────────────
    first_of_this_month = today.replace(day=1)
    last_month_end  = first_of_this_month - timedelta(days=1)
    prev_month_end  = last_month_end.replace(day=1) - timedelta(days=1)
    completed_month_keys = [_month_key(prev_month_end), _month_key(last_month_end)]

    # ── Truncate ──────────────────────────────────────────────────────────────
    cur.execute("""
        TRUNCATE
            fact_estimated_sale,
            mart_pricing_trends,
            mart_regional_summary,
            mart_daily_snapshot,
            dim_boat_model,
            dim_manufacturer,
            dim_geography,
            dim_date
        RESTART IDENTITY CASCADE
    """)

    # ── dim_manufacturer ──────────────────────────────────────────────────────
    cur.execute("""
        INSERT INTO dim_manufacturer
            (directus_brand_id, manufacturer_name, is_wakr_partner, is_active)
        VALUES
            (1, 'Centurion', false, true),
            (2, 'Malibu',    true,  true)
    """)

    # ── dim_boat_model ────────────────────────────────────────────────────────
    cur.execute("""
        INSERT INTO dim_boat_model
            (directus_model_id, manufacturer_key, make, model, model_year, is_active)
        VALUES
            (101, 1, 'Centurion', 'Fi23',   2026, true),
            (102, 1, 'Centurion', 'Ri245',  2025, true),
            (201, 2, 'Malibu',   '25 LSV',  2024, true)
    """)

    # ── dim_geography (state-level rows; zip IS NULL) ─────────────────────────
    cur.execute("""
        INSERT INTO dim_geography (state, state_name, region)
        VALUES
            ('FL', 'Florida',      'Southeast'),
            ('TX', 'Texas',        'South Central'),
            ('CA', 'California',   'West'),
            ('AK', 'Alaska',       'Pacific'),
            ('VT', 'Vermont',      'Northeast'),
            ('ND', 'North Dakota', 'Midwest')
    """)

    # ── mart_daily_snapshot ───────────────────────────────────────────────────
    # One row per (date_key × manufacturer_key × boat_model_key × listing_year × state × inventory_type).
    # Rows must have non-null boat_model_key and state to be visible to STOCK queries.
    #
    # Columns: al=active_listings, dom=avg_dom, price=avg_list_price,
    #          b0-b4=dom buckets, new_lst=new_listings
    STATE_PARAMS = [
        # state,  al,  dom,   price,   b0,  b1,  b2,  b3, b4, new_lst
        ('FL',   100, 14.2, 125_000,  40,  30,  20,  10,  0,  20),
        ('TX',    80, 16.0, 120_000,  32,  24,  14,   8,  2,  15),
        ('CA',    60, 26.1, 115_000,  18,  15,  15,  10,  2,  10),
        ('AK',     5, 28.0,  95_000,   1,   1,   2,   1,  0,   1),
        ('VT',     7, 31.0,  90_000,   1,   1,   2,   2,  1,   2),
        ('ND',     8, 29.5,  88_000,   2,   2,   2,   2,  0,   1),
    ]
    MODELS = [(1, 1, 'New', 2026), (1, 2, 'Used', 2025), (2, 3, 'New', 2024)]

    mds_rows = []
    for dk in snapshot_keys:
        scrape_date = date(dk // 10000, (dk // 100) % 100, dk % 100)
        for state, al, avg_dom, avg_price, b0, b1, b2, b3, b4, new_lst in STATE_PARAMS:
            for mkey, bkey, inv_type, listing_year in MODELS:
                mds_rows.append((
                    dk, mkey, bkey, listing_year, state, inv_type,
                    al, avg_price, round(avg_price * 0.96),
                    avg_dom, b0, b1, b2, b3, b4,
                    round(avg_price * 0.8), round(avg_price * 1.2),
                    0, 0, round(al * 0.3), round(al * 0.4), round(al * 0.2), round(al * 0.1),
                    None, None, None, None, None, None,
                    new_lst, max(1, new_lst // 2), 0,
                    'fast' if avg_dom < 20 else 'moderate',
                    None, None,
                    False, scrape_date,
                ))

    cur.executemany("""
        INSERT INTO mart_daily_snapshot (
            date_key, manufacturer_key, boat_model_key, listing_year, state, inventory_type,
            active_listings, avg_list_price, median_list_price, avg_dom,
            dom_bucket_0_7, dom_bucket_8_15, dom_bucket_16_30,
            dom_bucket_31_60, dom_bucket_60_plus,
            min_list_price, max_list_price,
            listing_count_band_under_60k, listing_count_band_60_80k,
            listing_count_band_80_100k,  listing_count_band_100_120k,
            listing_count_band_120_140k, listing_count_band_over_140k,
            avg_dom_band_under_60k, avg_dom_band_60_80k, avg_dom_band_80_100k,
            avg_dom_band_100_120k,  avg_dom_band_120_140k, avg_dom_band_over_140k,
            new_listings, removed_listings, price_reduced_listings,
            dom_status, sell_through_rate, days_supply,
            is_partial_scrape_day, last_scrape_date
        ) VALUES (
            %s,%s,%s,%s,%s,%s, %s,%s,%s,%s, %s,%s,%s,%s,%s,
            %s,%s, %s,%s,%s,%s,%s,%s,
            %s,%s,%s,%s,%s,%s,
            %s,%s,%s, %s,%s,%s, %s,%s
        )
    """, mds_rows)

    # ── mart_pricing_trends ───────────────────────────────────────────────────
    # geo_key=1 = FL (first geography row inserted, so SERIAL key = 1).
    # Two completed months required for MoM comparisons.
    # is_partial_month=False marks these as completed (used by pricing_summary).
    mpt_rows = []
    for mk in completed_month_keys:
        for mkey, bkey in [(1, 1), (1, 2), (2, 3)]:
            mpt_rows.append((
                mk, mkey, bkey, 1,
                125_000, 0.05,
                130_000, 0.03,
                -0.041, None,
                140_000, None,          # top band = over_140k (no upper bound)
                134, 0.42,
                'over_140k', None, None,
                False,
            ))

    cur.executemany("""
        INSERT INTO mart_pricing_trends (
            month_key, manufacturer_key, boat_model_key, geo_key,
            avg_list_price, avg_list_price_vs_market_pct,
            median_list_price, median_list_price_vs_market_pct,
            mom_price_change_pct, mom_price_change_pct_vs_market_pct,
            top_selling_band_low, top_selling_band_high,
            top_selling_band_units, top_selling_band_vs_market_pct,
            price_band_label, pct_listings_with_price_cut, discount_pressure_pct,
            is_partial_month
        ) VALUES (%s,%s,%s,%s, %s,%s,%s,%s,%s,%s, %s,%s,%s,%s, %s,%s,%s,%s)
    """, mpt_rows)

    # ── mart_regional_summary ─────────────────────────────────────────────────
    TREND = {
        'FL': ('Rising',  0.091),
        'TX': ('Rising',  0.045),
        'CA': ('Falling', -0.015),
        'AK': ('Stable',  0.0),
        'VT': ('Stable',  0.01),
        'ND': ('Falling', -0.02),
    }
    mrs_rows = []
    for mk in completed_month_keys:
        for state, (direction, yoy) in TREND.items():
            for mkey, bkey in [(1, 1), (1, 2), (2, 3)]:
                mrs_rows.append((
                    mk, state, mkey, bkey,
                    None, None, None, None,
                    yoy, None, direction, None, None, False,
                ))

    cur.executemany("""
        INSERT INTO mart_regional_summary (
            month_key, state, manufacturer_key, boat_model_key,
            avg_dom_vs_national_pct, boats_sold_t30_vs_market_pct,
            pct_market, avg_price_vs_market_pct, yoy_supply_change_pct,
            dom_status, sales_trend_direction,
            fastest_market_state, slowest_market_state, is_partial_month
        ) VALUES (%s,%s,%s,%s, %s,%s,%s,%s,%s, %s,%s,%s,%s,%s)
    """, mrs_rows)

    # ── fact_estimated_sale ───────────────────────────────────────────────────
    # Spread sales across the first 3 snapshot dates and 6 states.
    SALES_PER_STATE = [('FL', 5), ('TX', 4), ('CA', 3), ('AK', 1), ('VT', 1), ('ND', 1)]
    fes_rows = []
    for dk in snapshot_keys[:3]:
        for state, n in SALES_PER_STATE:
            for i in range(n):
                fes_rows.append((
                    dk, 1, 1, 2026, state, 'New',
                    115_000 + i * 1_000, 30 + i,
                ))

    cur.executemany("""
        INSERT INTO fact_estimated_sale (
            date_key, manufacturer_key, boat_model_key, listing_year,
            state, inventory_type, estimated_sale_price, days_on_market
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
    """, fes_rows)

    conn.commit()
    cur.close()
    conn.close()
    print(
        f"Seed complete: {len(mds_rows)} snapshot rows, "
        f"{len(mpt_rows)} pricing-trend rows, "
        f"{len(fes_rows)} sale rows."
    )


if __name__ == "__main__":
    seed_test_db()
