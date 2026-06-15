from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, select

from auth import require_auth
from db.engine import get_conn
from db.tables import dim_boat_model, dim_manufacturer, mart_daily_snapshot as mds
from db.tables import mart_pricing_trends as mpt
from models.common import (
    ApiResponse,
    PRICE_BAND_DEFS,
    PRICE_BAND_LABELS,
    FilterParams,
    InventoryType,
    PriceBand,
    TimeRange,
    error_detail,
    make_envelope,
)
from models.responses import (
    DomByPriceTierData,
    DomByPriceTierRow,
    ListingsByPriceTierData,
    ListingsByPriceTierRow,
    ModelEfficiencyData,
    ModelEfficiencyRow,
    PricingSummaryData,
    TopSellingBand,
)
from query.params import (
    classify_dom_velocity,
    common_dim_filters,
    latest_date_subquery,
    resolve_filter_keys,
    safe_float,
    safe_int,
)
from query.time_range import resolve_time_range

router = APIRouter(prefix="/api/v1/pricing", tags=["Pricing"])


def _band_from_price(low: Optional[float], high: Optional[float]) -> PriceBand:
    """Map a (low, high) dollar range back to the nearest PriceBand enum."""
    for band, _suffix, b_low, b_high in PRICE_BAND_DEFS:
        if b_low == low and b_high == high:
            return band
    # Fallback: classify by midpoint
    mid = ((low or 0) + (high or 999_999)) / 2
    for band, _suffix, b_low, b_high in reversed(PRICE_BAND_DEFS):
        if b_low is None or mid >= b_low:
            return band
    return PriceBand.over_140k


def _price_band_label(low: Optional[float], high: Optional[float]) -> str:
    if low is None:
        return f"Under ${int((high or 0) / 1000)}k"
    if high is None:
        return f"Over ${int(low / 1000)}k"
    return f"${int(low / 1000)}k–${int(high / 1000)}k"


# ---------------------------------------------------------------------------
# GET /api/v1/pricing/summary
# ---------------------------------------------------------------------------

@router.get("/summary", response_model=ApiResponse[PricingSummaryData])
async def pricing_summary(
    time_range: TimeRange = Query(...),
    inventory_type: InventoryType = Query(default=InventoryType.combined),
    make: Optional[str] = Query(default=None),
    model: Optional[str] = Query(default=None),
    as_of_date: Optional[date] = Query(default=None),
    _token: str = Depends(require_auth),
):
    params = FilterParams(
        time_range=time_range, inventory_type=inventory_type, make=make, model=model
    )
    dr = resolve_time_range(time_range, as_of_date)

    async with get_conn() as conn:
        resolved = await resolve_filter_keys(conn, params)
        latest_key = latest_date_subquery(mds, params, resolved, dr)

        # ---- avg_list_price and median_list_price: STOCK from latest snapshot ----
        stock_conds = [
            mds.c.date_key == latest_key,
            mds.c.boat_model_key.isnot(None),
            mds.c.state.isnot(None),
        ] + common_dim_filters(mds, params, resolved)

        stock_q = select(
            (
                func.sum(mds.c.avg_list_price * mds.c.active_listings)
                / func.nullif(func.sum(mds.c.active_listings), 0)
            ).label("avg_list_price"),
            (
                func.sum(mds.c.median_list_price * mds.c.active_listings)
                / func.nullif(func.sum(mds.c.active_listings), 0)
            ).label("median_list_price"),
            func.max(mds.c.last_scrape_date).label("last_scrape_date"),
        ).where(and_(*stock_conds))

        s = (await conn.execute(stock_q)).fetchone()

        if s is None or s.avg_list_price is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_detail("NO_DATA", "No data for the requested filters."),
            )

        # ---- mom_price_change_pct and top_selling_band from mart_pricing_trends ----
        # Always uses the most recently completed calendar month regardless of time_range.
        mpt_conds = [mpt.c.is_partial_month.is_(False)]
        if "manufacturer_key" in resolved:
            mpt_conds.append(mpt.c.manufacturer_key == resolved["manufacturer_key"])
        if "boat_model_keys" in resolved:
            mpt_conds.append(mpt.c.boat_model_key.in_(resolved["boat_model_keys"]))

        most_recent_month_subq = (
            select(func.max(mpt.c.month_key))
            .where(and_(*mpt_conds))
            .scalar_subquery()
        )

        mpt_q = select(
            mpt.c.mom_price_change_pct,
            mpt.c.top_selling_band_low,
            mpt.c.top_selling_band_high,
            mpt.c.top_selling_band_units,
        ).where(
            and_(
                mpt.c.month_key == most_recent_month_subq,
                *mpt_conds,
            )
        )

        mpt_row = (await conn.execute(mpt_q)).fetchone()

        if mpt_row is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=error_detail(
                    "INSUFFICIENT_DATA",
                    "Month-over-month pricing requires at least one completed calendar month of data.",
                ),
            )

        raw_low = mpt_row.top_selling_band_low
        raw_high = mpt_row.top_selling_band_high
        band = _band_from_price(
            float(raw_low) if raw_low is not None else None,
            float(raw_high) if raw_high is not None else None,
        )

        data = PricingSummaryData(
            avg_list_price=round(safe_float(s.avg_list_price), 2),
            median_list_price=round(safe_float(s.median_list_price), 2),
            mom_price_change_pct=round(safe_float(mpt_row.mom_price_change_pct) * 100, 2),
            top_selling_band=TopSellingBand(
                band=band,
                band_label=PRICE_BAND_LABELS[band],
                units_sold=safe_int(mpt_row.top_selling_band_units),
            ),
        )

        return make_envelope(data.model_dump(), s.last_scrape_date, params)


# ---------------------------------------------------------------------------
# GET /api/v1/pricing/dom-by-price-tier
# ---------------------------------------------------------------------------

@router.get("/dom-by-price-tier", response_model=ApiResponse[DomByPriceTierData])
async def dom_by_price_tier(
    time_range: TimeRange = Query(...),
    inventory_type: InventoryType = Query(default=InventoryType.combined),
    make: Optional[str] = Query(default=None),
    model: Optional[str] = Query(default=None),
    as_of_date: Optional[date] = Query(default=None),
    _token: str = Depends(require_auth),
):
    params = FilterParams(
        time_range=time_range, inventory_type=inventory_type, make=make, model=model
    )
    dr = resolve_time_range(time_range, as_of_date)

    async with get_conn() as conn:
        resolved = await resolve_filter_keys(conn, params)
        latest_key = latest_date_subquery(mds, params, resolved, dr)

        conds = [
            mds.c.date_key == latest_key,
            mds.c.boat_model_key.isnot(None),
            mds.c.state.isnot(None),
        ] + common_dim_filters(mds, params, resolved)

        q = select(
            func.sum(mds.c.avg_dom_band_under_60k * mds.c.listing_count_band_under_60k)
            .label("dom_under_60k_w"),
            func.sum(mds.c.listing_count_band_under_60k).label("cnt_under_60k"),
            func.sum(mds.c.avg_dom_band_60_80k * mds.c.listing_count_band_60_80k)
            .label("dom_60_80k_w"),
            func.sum(mds.c.listing_count_band_60_80k).label("cnt_60_80k"),
            func.sum(mds.c.avg_dom_band_80_100k * mds.c.listing_count_band_80_100k)
            .label("dom_80_100k_w"),
            func.sum(mds.c.listing_count_band_80_100k).label("cnt_80_100k"),
            func.sum(mds.c.avg_dom_band_100_120k * mds.c.listing_count_band_100_120k)
            .label("dom_100_120k_w"),
            func.sum(mds.c.listing_count_band_100_120k).label("cnt_100_120k"),
            func.sum(mds.c.avg_dom_band_120_140k * mds.c.listing_count_band_120_140k)
            .label("dom_120_140k_w"),
            func.sum(mds.c.listing_count_band_120_140k).label("cnt_120_140k"),
            func.sum(mds.c.avg_dom_band_over_140k * mds.c.listing_count_band_over_140k)
            .label("dom_over_140k_w"),
            func.sum(mds.c.listing_count_band_over_140k).label("cnt_over_140k"),
            func.max(mds.c.last_scrape_date).label("last_scrape_date"),
        ).where(and_(*conds))

        row = (await conn.execute(q)).fetchone()

        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_detail("NO_DATA", "No data for the requested filters."),
            )

        def weighted_avg(w_sum, cnt) -> float:
            c = safe_int(cnt)
            return round(safe_float(w_sum) / c, 1) if c else 0.0

        band_data = [
            (PriceBand.under_60k,      weighted_avg(row.dom_under_60k_w,  row.cnt_under_60k)),
            (PriceBand.band_60k_80k,   weighted_avg(row.dom_60_80k_w,     row.cnt_60_80k)),
            (PriceBand.band_80k_100k,  weighted_avg(row.dom_80_100k_w,    row.cnt_80_100k)),
            (PriceBand.band_100k_120k, weighted_avg(row.dom_100_120k_w,   row.cnt_100_120k)),
            (PriceBand.band_120k_140k, weighted_avg(row.dom_120_140k_w,   row.cnt_120_140k)),
            (PriceBand.over_140k,      weighted_avg(row.dom_over_140k_w,  row.cnt_over_140k)),
        ]

        bands = [
            DomByPriceTierRow(
                band=band,
                band_label=PRICE_BAND_LABELS[band],
                avg_days_on_market=avg_dom,
                velocity_label=classify_dom_velocity(avg_dom if avg_dom > 0 else None),
            )
            for band, avg_dom in band_data
        ]

        return make_envelope(
            DomByPriceTierData(bands=bands).model_dump(), row.last_scrape_date, params
        )


# ---------------------------------------------------------------------------
# GET /api/v1/pricing/listings-by-price-tier
# ---------------------------------------------------------------------------

@router.get("/listings-by-price-tier", response_model=ApiResponse[ListingsByPriceTierData])
async def listings_by_price_tier(
    time_range: TimeRange = Query(...),
    inventory_type: InventoryType = Query(default=InventoryType.combined),
    make: Optional[str] = Query(default=None),
    model: Optional[str] = Query(default=None),
    as_of_date: Optional[date] = Query(default=None),
    _token: str = Depends(require_auth),
):
    params = FilterParams(
        time_range=time_range, inventory_type=inventory_type, make=make, model=model
    )
    dr = resolve_time_range(time_range, as_of_date)

    async with get_conn() as conn:
        resolved = await resolve_filter_keys(conn, params)
        latest_key = latest_date_subquery(mds, params, resolved, dr)

        conds = [
            mds.c.date_key == latest_key,
            mds.c.boat_model_key.isnot(None),
            mds.c.state.isnot(None),
        ] + common_dim_filters(mds, params, resolved)

        q = select(
            func.sum(mds.c.listing_count_band_under_60k).label("under_60k"),
            func.sum(mds.c.listing_count_band_60_80k).label("b60_80k"),
            func.sum(mds.c.listing_count_band_80_100k).label("b80_100k"),
            func.sum(mds.c.listing_count_band_100_120k).label("b100_120k"),
            func.sum(mds.c.listing_count_band_120_140k).label("b120_140k"),
            func.sum(mds.c.listing_count_band_over_140k).label("over_140k"),
            func.max(mds.c.last_scrape_date).label("last_scrape_date"),
        ).where(and_(*conds))

        row = (await conn.execute(q)).fetchone()

        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_detail("NO_DATA", "No data for the requested filters."),
            )

        counts = [
            (PriceBand.under_60k,      safe_int(row.under_60k)),
            (PriceBand.band_60k_80k,   safe_int(row.b60_80k)),
            (PriceBand.band_80k_100k,  safe_int(row.b80_100k)),
            (PriceBand.band_100k_120k, safe_int(row.b100_120k)),
            (PriceBand.band_120k_140k, safe_int(row.b120_140k)),
            (PriceBand.over_140k,      safe_int(row.over_140k)),
        ]

        bands = [
            ListingsByPriceTierRow(
                band=band,
                band_label=PRICE_BAND_LABELS[band],
                listings=cnt,
            )
            for band, cnt in counts
        ]

        return make_envelope(
            ListingsByPriceTierData(bands=bands).model_dump(), row.last_scrape_date, params
        )


# ---------------------------------------------------------------------------
# GET /api/v1/pricing/model-efficiency
# ---------------------------------------------------------------------------

@router.get("/model-efficiency", response_model=ApiResponse[ModelEfficiencyData])
async def model_efficiency(
    time_range: TimeRange = Query(...),
    inventory_type: InventoryType = Query(default=InventoryType.combined),
    make: Optional[str] = Query(default=None),
    model: Optional[str] = Query(default=None),
    as_of_date: Optional[date] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _token: str = Depends(require_auth),
):
    params = FilterParams(
        time_range=time_range, inventory_type=inventory_type, make=make, model=model
    )
    dr = resolve_time_range(time_range, as_of_date)

    async with get_conn() as conn:
        resolved = await resolve_filter_keys(conn, params)
        latest_key = latest_date_subquery(mds, params, resolved, dr)

        conds = [
            mds.c.date_key == latest_key,
            mds.c.boat_model_key.isnot(None),
            mds.c.state.isnot(None),
        ] + common_dim_filters(mds, params, resolved)

        # price_band_low/high use min/max list price as a proxy for 10th/90th percentile.
        # For exact percentiles, query fact_listing_snapshot with PERCENTILE_CONT.
        q = (
            select(
                mds.c.manufacturer_key,
                mds.c.boat_model_key,
                (
                    func.sum(mds.c.avg_list_price * mds.c.active_listings)
                    / func.nullif(func.sum(mds.c.active_listings), 0)
                ).label("avg_list_price"),
                func.min(mds.c.min_list_price).label("price_band_low"),
                func.max(mds.c.max_list_price).label("price_band_high"),
                (
                    func.sum(mds.c.avg_dom * mds.c.active_listings)
                    / func.nullif(func.sum(mds.c.active_listings), 0)
                ).label("avg_dom"),
                func.sum(mds.c.active_listings).label("listings"),
                func.max(mds.c.last_scrape_date).label("last_scrape_date"),
                dim_boat_model.c.make,
                dim_boat_model.c.model,
                dim_boat_model.c.model_year,
                dim_manufacturer.c.manufacturer_name,
            )
            .join(dim_boat_model, mds.c.boat_model_key == dim_boat_model.c.boat_model_key)
            .join(dim_manufacturer, mds.c.manufacturer_key == dim_manufacturer.c.manufacturer_key)
            .where(and_(*conds))
            .group_by(
                mds.c.manufacturer_key,
                mds.c.boat_model_key,
                dim_boat_model.c.make,
                dim_boat_model.c.model,
                dim_boat_model.c.model_year,
                dim_manufacturer.c.manufacturer_name,
            )
        )

        rows = (await conn.execute(q)).fetchall()

        if not rows:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_detail("NO_DATA", "No data for the requested filters."),
            )

        # Sort by avg_dom ascending in Python — avoids duplicating the weighted-avg expression
        # in ORDER BY.  NULL avg_dom (no active listings) sorts last.
        rows = sorted(
            rows,
            key=lambda r: safe_float(r.avg_dom) if r.avg_dom is not None else float("inf"),
        )

        last_scrape = max(r.last_scrape_date for r in rows if r.last_scrape_date)

        result_rows = []
        for rank, r in enumerate(rows, start=1):
            low = safe_float(r.price_band_low)
            high = safe_float(r.price_band_high)
            result_rows.append(
                ModelEfficiencyRow(
                    rank=rank,
                    model_year=f"{r.model_year} {r.manufacturer_name} {r.model}",
                    manufacturer=r.manufacturer_name,
                    model=r.model,
                    year=r.model_year,
                    avg_list_price=round(safe_float(r.avg_list_price), 2),
                    price_band_low=round(low, 2),
                    price_band_high=round(high, 2),
                    price_band_label=_price_band_label(
                        low if r.price_band_low is not None else None,
                        high if r.price_band_high is not None else None,
                    ),
                    avg_days_on_market=round(safe_float(r.avg_dom), 1),
                    dom_velocity_label=classify_dom_velocity(safe_float(r.avg_dom)),
                    listings=safe_int(r.listings),
                )
            )

        # All rows are fetched from the DB before slicing; pagination is applied in Python.
        # Intentional at current dataset size — revisit with DB-level LIMIT/OFFSET if row
        # counts grow significantly. An offset beyond total_records returns an empty rows
        # array; this is valid pagination behaviour, not an error.
        return make_envelope(
            ModelEfficiencyData(
                rows=result_rows[offset : offset + limit],
                total_records=len(result_rows),
                limit=limit,
                offset=offset,
            ).model_dump(),
            last_scrape,
            params,
        )
