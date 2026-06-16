from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, select

from auth import require_auth
from db.engine import get_conn
from db.tables import (
    dim_boat_model,
    dim_manufacturer,
    fact_estimated_sale as fes,
    mart_daily_snapshot as mds,
)
from models.common import (
    ApiResponse,
    FilterParams,
    InventoryType,
    TimeRange,
    error_detail,
    make_envelope,
)
from models.responses import (
    DomDistribution,
    InventorySummaryData,
    InventoryTrendData,
    InventoryTrendPoint,
    InventoryVelocityData,
    InventoryVelocityRow,
)
from query.params import (
    classify_dom_velocity,
    classify_momentum,
    common_dim_filters,
    fes_conditions,
    latest_date_subquery,
    pct_aging,
    resolve_filter_keys,
    safe_float,
    safe_int,
)
from query.time_range import resolve_time_range

router = APIRouter(prefix="/api/v1/inventory", tags=["Inventory"])


def _key_to_iso(date_key: int) -> str:
    s = str(date_key)
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}"


# ---------------------------------------------------------------------------
# GET /api/v1/inventory/summary
# ---------------------------------------------------------------------------

@router.get("/summary", response_model=ApiResponse[InventorySummaryData])
async def inventory_summary(
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
        dim_conds = common_dim_filters(mds, params, resolved)

        # ---- STOCK: active listing counts from the most recent date in the window ----
        stock_conds = [
            mds.c.date_key == latest_key,
            mds.c.boat_model_key.isnot(None),
            mds.c.state.isnot(None),
        ] + dim_conds

        stock_q = select(
            func.sum(mds.c.active_listings).label("active_listings"),
            (
                func.sum(mds.c.avg_dom * mds.c.active_listings)
                / func.nullif(func.sum(mds.c.active_listings), 0)
            ).label("avg_dom"),
            func.sum(mds.c.dom_bucket_0_7).label("b0"),
            func.sum(mds.c.dom_bucket_8_15).label("b1"),
            func.sum(mds.c.dom_bucket_16_30).label("b2"),
            func.sum(mds.c.dom_bucket_31_60).label("b3"),
            func.sum(mds.c.dom_bucket_60_plus).label("b4"),
            func.max(mds.c.last_scrape_date).label("last_scrape_date"),
        ).where(and_(*stock_conds))

        s = (await conn.execute(stock_q)).fetchone()

        if s is None or s.active_listings is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_detail("NO_DATA", "No data for the requested filters."),
            )

        # ---- FLOW: inventory added (new listings) over the full window ----
        flow_conds = [
            mds.c.date_key >= dr.from_key,
            mds.c.date_key <= dr.to_key,
            mds.c.boat_model_key.isnot(None),
            mds.c.state.isnot(None),
        ] + dim_conds

        flow_q = select(
            func.sum(mds.c.new_listings).label("inventory_added"),
        ).where(and_(*flow_conds))

        f = (await conn.execute(flow_q)).fetchone()

        # ---- SALES: boats sold from fact_estimated_sale ----
        sale_q = select(
            func.count().label("boats_sold"),
        ).where(and_(*fes_conditions(fes, params, resolved, dr)))

        sale_row = (await conn.execute(sale_q)).fetchone()

        active = safe_int(s.active_listings)
        b3 = safe_int(s.b3)
        b4 = safe_int(s.b4)

        data = InventorySummaryData(
            active_listings=active,
            boats_sold=safe_int(sale_row.boats_sold) if sale_row else 0,
            inventory_added=safe_int(f.inventory_added) if f else 0,
            avg_days_on_market=round(safe_float(s.avg_dom), 1),
            pct_aging_past_30d=pct_aging(b3, b4, active),
            dom_distribution=DomDistribution(
                bucket_0_7=safe_int(s.b0),
                bucket_8_15=safe_int(s.b1),
                bucket_16_30=safe_int(s.b2),
                bucket_31_60=b3,
                bucket_60_plus=b4,
            ),
        )

        return make_envelope(data.model_dump(), s.last_scrape_date, params)


# ---------------------------------------------------------------------------
# GET /api/v1/inventory/trend
# ---------------------------------------------------------------------------

@router.get("/trend", response_model=ApiResponse[InventoryTrendData])
async def inventory_trend(
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

        trend_conds = [
            mds.c.date_key >= dr.from_key,
            mds.c.date_key <= dr.to_key,
            mds.c.boat_model_key.isnot(None),
            mds.c.state.isnot(None),
        ] + common_dim_filters(mds, params, resolved)

        # Each date_key point: sum active_listings across all grain dimensions at that date.
        # Summing STOCK across grain dimensions (not across dates) is valid.
        trend_q = (
            select(
                mds.c.date_key,
                func.sum(mds.c.active_listings).label("active_listings"),
                func.max(mds.c.last_scrape_date).label("last_scrape_date"),
            )
            .where(and_(*trend_conds))
            .group_by(mds.c.date_key)
            .order_by(mds.c.date_key)
        )

        rows = (await conn.execute(trend_q)).fetchall()

        if not rows:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_detail("NO_DATA", "No data for the requested filters."),
            )

        series = [
            InventoryTrendPoint(
                snapshot_date=_key_to_iso(r.date_key),
                active_listings=safe_int(r.active_listings),
            )
            for r in rows
        ]

        last_scrape = max(r.last_scrape_date for r in rows if r.last_scrape_date)

        return make_envelope(
            InventoryTrendData(series=series).model_dump(), last_scrape, params
        )


# ---------------------------------------------------------------------------
# GET /api/v1/inventory/velocity
# ---------------------------------------------------------------------------

@router.get("/velocity", response_model=ApiResponse[InventoryVelocityData])
async def inventory_velocity(
    time_range: TimeRange = Query(...),
    inventory_type: InventoryType = Query(default=InventoryType.combined),
    make: Optional[str] = Query(default=None),
    state: Optional[str] = Query(default=None),
    as_of_date: Optional[date] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _token: str = Depends(require_auth),
):
    params = FilterParams(
        time_range=time_range, inventory_type=inventory_type, make=make, state=state
    )
    dr = resolve_time_range(time_range, as_of_date)

    async with get_conn() as conn:
        resolved = await resolve_filter_keys(conn, params)

        dim_conds = common_dim_filters(mds, params, resolved)
        latest_key = latest_date_subquery(mds, params, resolved, dr)

        # ---- Current window STOCK + names (JOIN dim tables) ----
        stock_conds = [
            mds.c.date_key == latest_key,
            mds.c.boat_model_key.isnot(None),
            mds.c.state.isnot(None),
        ] + dim_conds

        current_q = (
            select(
                mds.c.manufacturer_key,
                mds.c.boat_model_key,
                (
                    func.sum(mds.c.avg_dom * mds.c.active_listings)
                    / func.nullif(func.sum(mds.c.active_listings), 0)
                ).label("avg_dom"),
                func.sum(mds.c.active_listings).label("active_units"),
                func.max(mds.c.last_scrape_date).label("last_scrape_date"),
                dim_boat_model.c.make,
                dim_boat_model.c.model,
                dim_boat_model.c.model_year,
                dim_manufacturer.c.manufacturer_name,
            )
            .join(dim_boat_model, mds.c.boat_model_key == dim_boat_model.c.boat_model_key)
            .join(dim_manufacturer, mds.c.manufacturer_key == dim_manufacturer.c.manufacturer_key)
            .where(and_(*stock_conds))
            .group_by(
                mds.c.manufacturer_key,
                mds.c.boat_model_key,
                dim_boat_model.c.make,
                dim_boat_model.c.model,
                dim_boat_model.c.model_year,
                dim_manufacturer.c.manufacturer_name,
            )
        )

        current_rows = (await conn.execute(current_q)).fetchall()

        if not current_rows:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_detail("NO_DATA", "No data for the requested filters."),
            )

        # ---- Current window boats sold from fact_estimated_sale ----
        sale_q = (
            select(
                fes.c.manufacturer_key,
                fes.c.boat_model_key,
                func.count().label("boats_sold"),
            )
            .where(and_(*fes_conditions(fes, params, resolved, dr)))
            .group_by(fes.c.manufacturer_key, fes.c.boat_model_key)
        )

        flow_map = {
            (r.manufacturer_key, r.boat_model_key): safe_int(r.boats_sold)
            for r in (await conn.execute(sale_q)).fetchall()
        }

        # ---- Prior window STOCK (for momentum) ----
        prior_latest = (
            select(func.max(mds.c.date_key))
            .where(mds.c.date_key >= dr.prior_from_key)
            .where(mds.c.date_key <= dr.prior_to_key)
            .where(mds.c.boat_model_key.isnot(None))
            .where(mds.c.state.isnot(None))
        )
        for c in dim_conds:
            prior_latest = prior_latest.where(c)
        prior_latest = prior_latest.scalar_subquery()

        prior_conds = [
            mds.c.date_key == prior_latest,
            mds.c.boat_model_key.isnot(None),
            mds.c.state.isnot(None),
        ] + dim_conds

        prior_q = (
            select(
                mds.c.manufacturer_key,
                mds.c.boat_model_key,
                (
                    func.sum(mds.c.avg_dom * mds.c.active_listings)
                    / func.nullif(func.sum(mds.c.active_listings), 0)
                ).label("avg_dom"),
            )
            .where(and_(*prior_conds))
            .group_by(mds.c.manufacturer_key, mds.c.boat_model_key)
        )

        prior_map = {
            (r.manufacturer_key, r.boat_model_key): safe_float(r.avg_dom)
            for r in (await conn.execute(prior_q)).fetchall()
        }

        # ---- Assemble rows ----
        velocity_rows = []
        for r in current_rows:
            key = (r.manufacturer_key, r.boat_model_key)
            cur_dom = safe_float(r.avg_dom)
            prior_dom = prior_map.get(key)
            velocity_rows.append(
                InventoryVelocityRow(
                    model_year=f"{r.model_year or '?'} {r.manufacturer_name} {r.model}",
                    manufacturer=r.manufacturer_name,
                    model=r.model,
                    year=r.model_year,
                    avg_days_on_market=round(cur_dom, 1),
                    dom_velocity_label=classify_dom_velocity(cur_dom),
                    active_units=safe_int(r.active_units),
                    boats_sold=flow_map.get(key, 0),
                    momentum=classify_momentum(cur_dom, prior_dom),
                )
            )

        velocity_rows.sort(key=lambda x: x.avg_days_on_market)
        # All rows are fetched from the DB before slicing; pagination is applied in Python.
        # Intentional at current dataset size — revisit with DB-level LIMIT/OFFSET if row
        # counts grow significantly. An offset beyond total_records returns an empty rows
        # array; this is valid pagination behaviour, not an error.
        total_records = len(velocity_rows)
        last_scrape = max(
            (r.last_scrape_date for r in current_rows if r.last_scrape_date), default=None
        )

        return make_envelope(
            InventoryVelocityData(
                rows=velocity_rows[offset : offset + limit],
                total_records=total_records,
                limit=limit,
                offset=offset,
            ).model_dump(),
            last_scrape,
            params,
        )
