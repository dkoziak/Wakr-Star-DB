from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, select

from auth import require_auth
from db.engine import get_conn
from db.tables import fact_estimated_sale as fes
from db.tables import mart_daily_snapshot as mds
from db.tables import mart_regional_summary as mrs
from models.common import (
    ApiResponse,
    FilterParams,
    InventoryType,
    TimeRange,
    US_STATE_NAMES,
    error_detail,
    make_envelope,
)
from models.responses import (
    MarketLeaderRow,
    MarketState,
    RegionalMarketLeadersData,
    RegionalStateOverviewData,
    RegionalStateRow,
    RegionalSummaryData,
    SalesTrends,
    TopGrowthState,
)
from query.params import (
    classify_dom_velocity,
    dim_conditions_no_state,
    fes_conditions,
    latest_date_subquery,
    resolve_filter_keys,
    safe_float,
    safe_int,
)
from query.time_range import resolve_time_range

router = APIRouter(prefix="/api/v1/regional", tags=["Regional"])


# ---------------------------------------------------------------------------
# GET /api/v1/regional/summary
# ---------------------------------------------------------------------------

@router.get("/summary", response_model=ApiResponse[RegionalSummaryData])
async def regional_summary(
    time_range: TimeRange = Query(...),
    inventory_type: InventoryType = Query(default=InventoryType.combined),
    make: Optional[str] = Query(default=None),
    model: Optional[str] = Query(default=None),
    state: Optional[str] = Query(default=None),
    as_of_date: Optional[date] = Query(default=None),
    _token: str = Depends(require_auth),
):
    if state is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_detail(
                "INVALID_PARAM",
                "regional/summary aggregates all states and does not support the state filter.",
                "state",
            ),
        )
    params = FilterParams(
        time_range=time_range,
        inventory_type=inventory_type,
        make=make,
        model=model,
    )
    dr = resolve_time_range(time_range, as_of_date)

    async with get_conn() as conn:
        resolved = await resolve_filter_keys(conn, params)
        # Build dim conditions without state — we need all states to compute national stats.
        no_state_conds = dim_conditions_no_state(mds, params, resolved)

        latest_key_national = (
            select(func.max(mds.c.date_key))
            .where(mds.c.date_key >= dr.from_key)
            .where(mds.c.date_key <= dr.to_key)
            .where(mds.c.boat_model_key.isnot(None))
            .where(mds.c.state.isnot(None))
        )
        for c in no_state_conds:
            latest_key_national = latest_key_national.where(c)
        latest_key_national = latest_key_national.scalar_subquery()

        per_state_q = (
            select(
                mds.c.state,
                (
                    func.sum(mds.c.avg_dom * mds.c.active_listings)
                    / func.nullif(func.sum(mds.c.active_listings), 0)
                ).label("avg_dom"),
                func.sum(mds.c.active_listings).label("active_listings"),
                func.max(mds.c.last_scrape_date).label("last_scrape_date"),
            )
            .where(
                and_(
                    mds.c.date_key == latest_key_national,
                    mds.c.boat_model_key.isnot(None),
                    mds.c.state.isnot(None),
                    *no_state_conds,
                )
            )
            .group_by(mds.c.state)
            .having(func.sum(mds.c.active_listings) > 0)
        )

        state_rows = (await conn.execute(per_state_q)).fetchall()

        if not state_rows:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_detail("NO_DATA", "No data for the requested filters."),
            )

        # Weighted national avg_dom
        total_weighted = sum(safe_float(r.avg_dom) * safe_int(r.active_listings) for r in state_rows)
        total_active = sum(safe_int(r.active_listings) for r in state_rows)
        national_avg_dom = total_weighted / total_active if total_active else 0.0

        sorted_by_dom = sorted(state_rows, key=lambda r: safe_float(r.avg_dom))
        fastest_row = sorted_by_dom[0]
        slowest_row = sorted_by_dom[-1]

        fastest_dom = safe_float(fastest_row.avg_dom)
        slowest_dom = safe_float(slowest_row.avg_dom)

        fastest_pct = (
            (national_avg_dom - fastest_dom) / national_avg_dom * 100
            if national_avg_dom else 0.0
        )
        slowest_pct = (
            (slowest_dom - national_avg_dom) / national_avg_dom * 100
            if national_avg_dom else 0.0
        )

        last_scrape = max(
            (r.last_scrape_date for r in state_rows if r.last_scrape_date), default=None
        )

        # ---- YoY and sales trend from mart_regional_summary (most recent complete month) ----
        mrs_conds = [mrs.c.is_partial_month.is_(False)]
        if "manufacturer_key" in resolved:
            mrs_conds.append(mrs.c.manufacturer_key == resolved["manufacturer_key"])
        if "boat_model_keys" in resolved:
            mrs_conds.append(mrs.c.boat_model_key.in_(resolved["boat_model_keys"]))

        recent_month_subq = (
            select(func.max(mrs.c.month_key))
            .where(and_(*mrs_conds))
            .scalar_subquery()
        )

        trend_q = select(
            mrs.c.state,
            mrs.c.yoy_supply_change_pct,
            mrs.c.sales_trend_direction,
        ).where(and_(mrs.c.month_key == recent_month_subq, *mrs_conds))

        trend_rows = (await conn.execute(trend_q)).fetchall()

        top_growth_state_code = "N/A"
        top_growth_pct = 0.0
        rising = 0
        falling = 0

        if trend_rows:
            best = max(trend_rows, key=lambda r: safe_float(r.yoy_supply_change_pct))
            top_growth_state_code = best.state
            top_growth_pct = round(safe_float(best.yoy_supply_change_pct) * 100, 2)
            rising = sum(1 for r in trend_rows if r.sales_trend_direction == "Rising")
            falling = sum(1 for r in trend_rows if r.sales_trend_direction == "Falling")

        fastest_code = fastest_row.state.strip()
        slowest_code = slowest_row.state.strip()

        data = RegionalSummaryData(
            national_avg_dom=round(national_avg_dom, 1),
            fastest_market=MarketState(
                state=fastest_code,
                state_name=US_STATE_NAMES.get(fastest_code, fastest_code),
                avg_dom=round(fastest_dom, 1),
                pct_vs_national=round(fastest_pct, 2),
            ),
            slowest_market=MarketState(
                state=slowest_code,
                state_name=US_STATE_NAMES.get(slowest_code, slowest_code),
                avg_dom=round(slowest_dom, 1),
                pct_vs_national=round(slowest_pct, 2),
            ),
            top_growth_state=TopGrowthState(
                state=top_growth_state_code,
                state_name=US_STATE_NAMES.get(top_growth_state_code, top_growth_state_code),
                yoy_supply_change_pct=top_growth_pct,
            ),
            sales_trends=SalesTrends(states_rising=rising, states_falling=falling),
        )

        return make_envelope(data.model_dump(), last_scrape, params)


# ---------------------------------------------------------------------------
# GET /api/v1/regional/state-overview
# ---------------------------------------------------------------------------

@router.get("/state-overview", response_model=ApiResponse[RegionalStateOverviewData])
async def regional_state_overview(
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
        no_state_conds = dim_conditions_no_state(mds, params, resolved)

        latest_key = (
            select(func.max(mds.c.date_key))
            .where(mds.c.date_key >= dr.from_key)
            .where(mds.c.date_key <= dr.to_key)
            .where(mds.c.boat_model_key.isnot(None))
            .where(mds.c.state.isnot(None))
        )
        for c in no_state_conds:
            latest_key = latest_key.where(c)
        latest_key = latest_key.scalar_subquery()

        # ---- STOCK: active listings, avg_dom, avg_list_price per state (latest date) ----
        stock_q = (
            select(
                mds.c.state,
                func.sum(mds.c.active_listings).label("listings"),
                (
                    func.sum(mds.c.avg_dom * mds.c.active_listings)
                    / func.nullif(func.sum(mds.c.active_listings), 0)
                ).label("avg_dom"),
                (
                    func.sum(mds.c.avg_list_price * mds.c.active_listings)
                    / func.nullif(func.sum(mds.c.active_listings), 0)
                ).label("avg_list_price"),
                func.max(mds.c.last_scrape_date).label("last_scrape_date"),
            )
            .where(
                and_(
                    mds.c.date_key == latest_key,
                    mds.c.boat_model_key.isnot(None),
                    mds.c.state.isnot(None),
                    *no_state_conds,
                )
            )
            .group_by(mds.c.state)
        )

        stock_map = {
            r.state.strip(): r for r in (await conn.execute(stock_q)).fetchall()
        }

        if not stock_map:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_detail("NO_DATA", "No data for the requested filters."),
            )

        # ---- FLOW: boats sold per state from fact_estimated_sale ----
        fes_conds = fes_conditions(fes, params, resolved, dr, include_state=False)
        flow_q = (
            select(
                fes.c.state,
                func.count().label("boats_sold"),
            )
            .where(and_(*fes_conds))
            .group_by(fes.c.state)
        )

        flow_map = {
            r.state.strip(): safe_int(r.boats_sold)
            for r in (await conn.execute(flow_q)).fetchall()
        }

        national_total = sum(flow_map.values())

        result_rows: list[RegionalStateRow] = []
        last_scrape = None

        for state_code, sr in sorted(
            stock_map.items(), key=lambda kv: flow_map.get(kv[0], 0), reverse=True
        ):
            boats_sold = flow_map.get(state_code, 0)
            avg_dom = safe_float(sr.avg_dom)
            pct_mkt = round(boats_sold / national_total * 100, 2) if national_total else 0.0

            result_rows.append(
                RegionalStateRow(
                    state=state_code,
                    state_name=US_STATE_NAMES.get(state_code, state_code),
                    listings=safe_int(sr.listings),
                    avg_days_on_market=round(avg_dom, 1),
                    dom_velocity_label=classify_dom_velocity(avg_dom),
                    boats_sold=boats_sold,
                    pct_market=pct_mkt,
                    avg_list_price=round(safe_float(sr.avg_list_price), 2),
                )
            )
            if sr.last_scrape_date:
                last_scrape = (
                    sr.last_scrape_date
                    if last_scrape is None
                    else max(last_scrape, sr.last_scrape_date)
                )

        # All rows are fetched from the DB before slicing; pagination is applied in Python.
        # Intentional at current dataset size — revisit with DB-level LIMIT/OFFSET if row
        # counts grow significantly. An offset beyond total_records returns an empty rows
        # array; this is valid pagination behaviour, not an error.
        return make_envelope(
            RegionalStateOverviewData(
                national_total_boats_sold=national_total,
                rows=result_rows[offset : offset + limit],
                total_records=len(result_rows),
                limit=limit,
                offset=offset,
            ).model_dump(),
            last_scrape,
            params,
        )


# ---------------------------------------------------------------------------
# GET /api/v1/regional/market-leaders
# ---------------------------------------------------------------------------

@router.get("/market-leaders", response_model=ApiResponse[RegionalMarketLeadersData])
async def regional_market_leaders(
    time_range: TimeRange = Query(...),
    inventory_type: InventoryType = Query(default=InventoryType.combined),
    make: Optional[str] = Query(default=None),
    model: Optional[str] = Query(default=None),
    top_n: int = Query(default=5, ge=1, le=50),
    as_of_date: Optional[date] = Query(default=None),
    _token: str = Depends(require_auth),
):
    params = FilterParams(
        time_range=time_range, inventory_type=inventory_type, make=make, model=model
    )
    dr = resolve_time_range(time_range, as_of_date)

    async with get_conn() as conn:
        resolved = await resolve_filter_keys(conn, params)
        no_state_conds = dim_conditions_no_state(mds, params, resolved)

        latest_key = (
            select(func.max(mds.c.date_key))
            .where(mds.c.date_key >= dr.from_key)
            .where(mds.c.date_key <= dr.to_key)
            .where(mds.c.boat_model_key.isnot(None))
            .where(mds.c.state.isnot(None))
        )
        for c in no_state_conds:
            latest_key = latest_key.where(c)
        latest_key = latest_key.scalar_subquery()

        # ---- FLOW: boats sold per state from fact_estimated_sale ----
        fes_conds = fes_conditions(fes, params, resolved, dr, include_state=False)
        flow_q = (
            select(
                fes.c.state,
                func.count().label("boats_sold"),
            )
            .where(and_(*fes_conds))
            .group_by(fes.c.state)
        )

        flow_rows = (await conn.execute(flow_q)).fetchall()

        if not flow_rows:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_detail("NO_DATA", "No data for the requested filters."),
            )

        # ---- STOCK: active listings per state ----
        listing_q = (
            select(
                mds.c.state,
                func.sum(mds.c.active_listings).label("listings"),
                func.max(mds.c.last_scrape_date).label("last_scrape_date"),
            )
            .where(
                and_(
                    mds.c.date_key == latest_key,
                    mds.c.boat_model_key.isnot(None),
                    mds.c.state.isnot(None),
                    *no_state_conds,
                )
            )
            .group_by(mds.c.state)
        )

        listing_rows = (await conn.execute(listing_q)).fetchall()
        listing_map = {r.state.strip(): safe_int(r.listings) for r in listing_rows}
        last_scrape_vals = [r.last_scrape_date for r in listing_rows if r.last_scrape_date]

        sorted_states = sorted(
            flow_rows, key=lambda r: safe_int(r.boats_sold), reverse=True
        )

        def _make_row(rank: int, r) -> MarketLeaderRow:
            code = r.state.strip()
            return MarketLeaderRow(
                rank=rank,
                state=code,
                state_name=US_STATE_NAMES.get(code, code),
                boats_sold=safe_int(r.boats_sold),
                listings=listing_map.get(code, 0),
            )

        top_states = [_make_row(i + 1, r) for i, r in enumerate(sorted_states[:top_n])]

        # Exclude states already in top from bottom candidates to prevent overlap
        top_codes = {r.state for r in top_states}
        bottom_candidates = [r for r in sorted_states if r.state.strip() not in top_codes]
        bottom_candidates = list(reversed(bottom_candidates))[:top_n]
        bottom_states = [_make_row(i + 1, r) for i, r in enumerate(bottom_candidates)]

        last_scrape = max(last_scrape_vals) if last_scrape_vals else None

        return make_envelope(
            RegionalMarketLeadersData(
                top_states=top_states, bottom_states=bottom_states
            ).model_dump(),
            last_scrape,
            params,
        )
