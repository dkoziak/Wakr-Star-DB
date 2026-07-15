from typing import Optional

from pydantic import BaseModel

from models.common import DomVelocityLabel, MomentumLabel, PriceBand


# ---------------------------------------------------------------------------
# Inventory Tab
# ---------------------------------------------------------------------------

class DomDistribution(BaseModel):
    bucket_0_7: int
    bucket_8_15: int
    bucket_16_30: int
    bucket_31_60: int
    bucket_60_plus: int


class InventorySummaryData(BaseModel):
    active_listings: int
    boats_sold: int
    inventory_added: int
    avg_days_on_market: float
    pct_aging_past_30d: float
    dom_distribution: DomDistribution


class InventoryTrendPoint(BaseModel):
    snapshot_date: str
    active_listings: int


class InventoryTrendData(BaseModel):
    series: list[InventoryTrendPoint]


class InventoryVelocityRow(BaseModel):
    model_year: str
    manufacturer: str
    model: str
    year: Optional[int]
    avg_days_on_market: Optional[float] = None
    dom_velocity_label: DomVelocityLabel
    active_units: int
    boats_sold: int
    momentum: Optional[MomentumLabel] = None


class InventoryVelocityData(BaseModel):
    rows: list[InventoryVelocityRow]
    total_records: int


# ---------------------------------------------------------------------------
# Pricing Tab
# ---------------------------------------------------------------------------

class TopSellingBand(BaseModel):
    band: PriceBand
    band_label: str
    units_sold: int


class PricingSummaryData(BaseModel):
    avg_list_price: float
    median_list_price: float
    mom_price_change_pct: float
    top_selling_band: TopSellingBand


class DomByPriceTierRow(BaseModel):
    band: PriceBand
    band_label: str
    avg_days_on_market: float
    velocity_label: DomVelocityLabel


class DomByPriceTierData(BaseModel):
    bands: list[DomByPriceTierRow]


class ListingsByPriceTierRow(BaseModel):
    band: PriceBand
    band_label: str
    listings: int


class ListingsByPriceTierData(BaseModel):
    bands: list[ListingsByPriceTierRow]


class ModelEfficiencyRow(BaseModel):
    rank: int
    model_year: str
    manufacturer: str
    model: str
    year: Optional[int]
    avg_list_price: float
    price_band_low: float
    price_band_high: float
    price_band_label: str
    avg_days_on_market: float
    dom_velocity_label: DomVelocityLabel
    listings: int


class ModelEfficiencyData(BaseModel):
    rows: list[ModelEfficiencyRow]
    total_records: int
    limit: int
    offset: int


# ---------------------------------------------------------------------------
# Regional Tab
# ---------------------------------------------------------------------------

class MarketState(BaseModel):
    state: str
    state_name: str
    avg_dom: float
    pct_vs_national: float


class TopGrowthState(BaseModel):
    state: str
    state_name: str
    yoy_supply_change_pct: float


class SalesTrends(BaseModel):
    states_rising: int
    states_falling: int


class RegionalSummaryData(BaseModel):
    national_avg_dom: float
    fastest_market: MarketState
    slowest_market: MarketState
    top_growth_state: TopGrowthState
    sales_trends: SalesTrends


class RegionalStateRow(BaseModel):
    state: str
    state_name: str
    listings: int
    avg_days_on_market: float
    dom_velocity_label: DomVelocityLabel
    boats_sold: int
    pct_market: float
    avg_list_price: float


class RegionalStateOverviewData(BaseModel):
    national_total_boats_sold: int
    rows: list[RegionalStateRow]
    total_records: int
    limit: int
    offset: int


class MarketLeaderRow(BaseModel):
    rank: int
    state: str
    state_name: str
    boats_sold: int
    listings: int


class RegionalMarketLeadersData(BaseModel):
    top_states: list[MarketLeaderRow]
    bottom_states: list[MarketLeaderRow]
