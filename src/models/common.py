from datetime import datetime, timezone
from typing import Generic, Optional, TypeVar

from pydantic import BaseModel, Field

from models.enums import (  # noqa: F401 — re-exported for existing callers
    DomVelocityLabel,
    InventoryType,
    MomentumLabel,
    PRICE_BAND_DEFS,
    PRICE_BAND_LABELS,
    PriceBand,
    TimeRange,
    US_STATE_NAMES,
)

__all__ = [
    # re-exports from enums
    "TimeRange",
    "InventoryType",
    "MomentumLabel",
    "DomVelocityLabel",
    "PriceBand",
    "PRICE_BAND_LABELS",
    "PRICE_BAND_DEFS",
    "US_STATE_NAMES",
    # defined here
    "FilterParams",
    "ApiResponse",
    "make_envelope",
    "error_detail",
]

T = TypeVar("T")


class FilterParams(BaseModel):
    time_range: TimeRange
    inventory_type: InventoryType = InventoryType.combined
    make: Optional[str] = None
    model: Optional[str] = None
    state: Optional[str] = None


class ApiResponse(BaseModel, Generic[T]):
    data: T
    data_as_of: str = Field(description="ISO 8601 datetime of most recent scrape snapshot")
    generated_at: str = Field(description="ISO 8601 datetime of this response")
    filters_applied: FilterParams


def make_envelope(data: T, data_as_of, filters: FilterParams) -> dict:
    if data_as_of is None:
        as_of_str = "unknown"
    elif hasattr(data_as_of, "hour"):
        # datetime object
        as_of_str = data_as_of.isoformat() + ("Z" if data_as_of.tzinfo is None else "")
    elif hasattr(data_as_of, "isoformat"):
        # date object — promote to midnight UTC datetime
        as_of_str = f"{data_as_of.isoformat()}T00:00:00Z"
    else:
        as_of_str = str(data_as_of)

    return {
        "data": data,
        "data_as_of": as_of_str,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "filters_applied": filters.model_dump(exclude_none=True),
    }


def error_detail(code: str, message: str, field: Optional[str] = None) -> dict:
    err: dict = {"code": code, "message": message}
    if field:
        err["field"] = field
    return {"error": err}
