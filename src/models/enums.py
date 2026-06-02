from enum import Enum
from typing import Optional

__all__ = [
    "TimeRange",
    "InventoryType",
    "MomentumLabel",
    "DomVelocityLabel",
    "PriceBand",
    "PRICE_BAND_LABELS",
    "PRICE_BAND_DEFS",
    "US_STATE_NAMES",
]


class TimeRange(str, Enum):
    trailing_7 = "trailing_7"
    trailing_30 = "trailing_30"
    trailing_90 = "trailing_90"
    last_month = "last_month"
    last_quarter = "last_quarter"
    ytd = "ytd"
    l12m = "l12m"


class InventoryType(str, Enum):
    new = "new"
    used = "used"
    combined = "combined"


class MomentumLabel(str, Enum):
    accelerating = "Accelerating"
    stable = "Stable"
    slowing = "Slowing"


class DomVelocityLabel(str, Enum):
    fast = "Fast"
    healthy = "Healthy"
    slow = "Slow"
    very_slow = "Very Slow"


class PriceBand(str, Enum):
    under_60k = "under_60k"
    band_60k_80k = "60k_80k"
    band_80k_100k = "80k_100k"
    band_100k_120k = "100k_120k"
    band_120k_140k = "120k_140k"
    over_140k = "over_140k"


PRICE_BAND_LABELS: dict[PriceBand, str] = {
    PriceBand.under_60k: "Under $60k",
    PriceBand.band_60k_80k: "$60–80k",
    PriceBand.band_80k_100k: "$80–100k",
    PriceBand.band_100k_120k: "$100–120k",
    PriceBand.band_120k_140k: "$120–140k",
    PriceBand.over_140k: "Over $140k",
}

# (band, column_suffix, low_bound, high_bound) — bounds in dollars, None = unbounded
PRICE_BAND_DEFS: list[tuple[PriceBand, str, Optional[float], Optional[float]]] = [
    (PriceBand.under_60k,      "under_60k",  None,    60_000),
    (PriceBand.band_60k_80k,   "60_80k",     60_000,  80_000),
    (PriceBand.band_80k_100k,  "80_100k",    80_000,  100_000),
    (PriceBand.band_100k_120k, "100_120k",   100_000, 120_000),
    (PriceBand.band_120k_140k, "120_140k",   120_000, 140_000),
    (PriceBand.over_140k,      "over_140k",  140_000, None),
]

US_STATE_NAMES: dict[str, str] = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming",
}
