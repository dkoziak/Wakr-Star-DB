"""
Query-layer utilities: key resolution, filter building, and Tier 2 classifiers.
"""

from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncConnection

from db.tables import dim_boat_model, dim_manufacturer
from models.common import (
    DomVelocityLabel,
    FilterParams,
    InventoryType,
    MomentumLabel,
    error_detail,
)
from query.time_range import DateRange

__all__ = [
    "resolve_filter_keys",
    "common_dim_filters",
    "dim_conditions_no_state",
    "fes_conditions",
    "latest_date_subquery",
    "classify_dom_velocity",
    "classify_momentum",
    "pct_aging",
    "safe_float",
    "safe_int",
]


# ---------------------------------------------------------------------------
# Key resolution
# ---------------------------------------------------------------------------

async def resolve_filter_keys(conn: AsyncConnection, params: FilterParams) -> dict:
    """
    Resolve make/model name strings to integer surrogate keys.
    Returns a dict that may contain 'manufacturer_key' (int) and
    'boat_model_keys' (list[int]).  Missing keys mean "no filter".
    """
    keys: dict = {}

    if params.make and params.make.lower() != "all":
        row = (
            await conn.execute(
                select(dim_manufacturer.c.manufacturer_key).where(
                    func.lower(dim_manufacturer.c.manufacturer_name) == params.make.lower()
                )
            )
        ).fetchone()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_detail("INVALID_PARAM", f"Unknown make: {params.make}", "make"),
            )
        keys["manufacturer_key"] = row[0]

    if params.model and params.model.lower() != "all" and "manufacturer_key" in keys:
        rows = (
            await conn.execute(
                select(dim_boat_model.c.boat_model_key).where(
                    and_(
                        func.lower(dim_boat_model.c.model) == params.model.lower(),
                        dim_boat_model.c.manufacturer_key == keys["manufacturer_key"],
                    )
                )
            )
        ).fetchall()
        if not rows:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_detail("INVALID_PARAM", f"Unknown model: {params.model}", "model"),
            )
        keys["boat_model_keys"] = [r[0] for r in rows]

    return keys


# ---------------------------------------------------------------------------
# WHERE clause builders
# ---------------------------------------------------------------------------

def common_dim_filters(mds, params: FilterParams, resolved: dict) -> list:
    """Dimension filters (make, model, inventory_type, state) for mart_daily_snapshot."""
    conds = []
    if "manufacturer_key" in resolved:
        conds.append(mds.c.manufacturer_key == resolved["manufacturer_key"])
    if "boat_model_keys" in resolved:
        conds.append(mds.c.boat_model_key.in_(resolved["boat_model_keys"]))
    if params.inventory_type and params.inventory_type != InventoryType.combined:
        inv_val = "New" if params.inventory_type == InventoryType.new else "Used"
        conds.append(mds.c.inventory_type == inv_val)
    if params.state and params.state.lower() != "all":
        conds.append(mds.c.state == params.state.upper())
    return conds


def dim_conditions_no_state(mds, params: FilterParams, resolved: dict) -> list:
    """Dimension filters excluding state — for regional endpoints that aggregate all states."""
    conds = []
    if "manufacturer_key" in resolved:
        conds.append(mds.c.manufacturer_key == resolved["manufacturer_key"])
    if "boat_model_keys" in resolved:
        conds.append(mds.c.boat_model_key.in_(resolved["boat_model_keys"]))
    if params.inventory_type and params.inventory_type != InventoryType.combined:
        inv_val = "New" if params.inventory_type == InventoryType.new else "Used"
        conds.append(mds.c.inventory_type == inv_val)
    return conds


def fes_conditions(fes, params: FilterParams, resolved: dict, dr: DateRange, *, include_state: bool = True) -> list:
    """WHERE conditions for fact_estimated_sale queries over a date window."""
    conds = [
        fes.c.date_key >= dr.from_key,
        fes.c.date_key <= dr.to_key,
    ]
    if "manufacturer_key" in resolved:
        conds.append(fes.c.manufacturer_key == resolved["manufacturer_key"])
    if "boat_model_keys" in resolved:
        conds.append(fes.c.boat_model_key.in_(resolved["boat_model_keys"]))
    if params.inventory_type and params.inventory_type != InventoryType.combined:
        inv_val = "New" if params.inventory_type == InventoryType.new else "Used"
        conds.append(fes.c.inventory_type == inv_val)
    if include_state and params.state and params.state.lower() != "all":
        conds.append(fes.c.state == params.state.upper())
    return conds


def latest_date_subquery(mds, params: FilterParams, resolved: dict, dr: DateRange):
    """Scalar subquery for MAX(date_key) within the window, respecting filters."""
    q = (
        select(func.max(mds.c.date_key))
        .where(mds.c.date_key >= dr.from_key)
        .where(mds.c.date_key <= dr.to_key)
        .where(mds.c.boat_model_key.isnot(None))
        .where(mds.c.state.isnot(None))
    )
    for cond in common_dim_filters(mds, params, resolved):
        q = q.where(cond)
    return q.scalar_subquery()


# ---------------------------------------------------------------------------
# Tier 2 classifiers (pure Python — executed after DB fetch)
# ---------------------------------------------------------------------------

def classify_dom_velocity(avg_dom: Optional[float]) -> DomVelocityLabel:
    if avg_dom is None:
        return DomVelocityLabel.very_slow
    if avg_dom < 15:
        return DomVelocityLabel.fast
    if avg_dom < 22:
        return DomVelocityLabel.healthy
    if avg_dom < 30:
        return DomVelocityLabel.slow
    return DomVelocityLabel.very_slow


def classify_momentum(current_dom: Optional[float], prior_dom: Optional[float]) -> MomentumLabel:
    if prior_dom is None or prior_dom == 0 or current_dom is None:
        return MomentumLabel.stable
    change = (current_dom - prior_dom) / prior_dom
    if change < -0.10:
        return MomentumLabel.accelerating
    if change > 0.10:
        return MomentumLabel.slowing
    return MomentumLabel.stable


def pct_aging(bucket_31_60: int, bucket_60_plus: int, active: int) -> float:
    if not active:
        return 0.0
    return round((bucket_31_60 + bucket_60_plus) / active * 100, 2)


def safe_float(v) -> float:
    return float(v) if v is not None else 0.0


def safe_int(v) -> int:
    return int(v) if v is not None else 0
