"""
test_api_payloads.py

One test per endpoint — asserts the complete response envelope and every
required payload field, then logs the full response body to a JSON file.

Log location: tests/payload_logs/api_payloads_<YYYYMMDD_HHMMSS>.json
A new file is written on every test run.

How the mocking works
---------------------
Each test patches the router's `get_conn` dependency with a fake that yields
a pre-loaded AsyncMock connection (`mock_conn`).  `mock_conn` returns
canned `mock_result` objects in sequence — one per SQL query the endpoint
fires.  `SimpleNamespace` rows (in mock_data.py) mimic SQLAlchemy attribute
access.  No database or server is started; FastAPI's TestClient dispatches
requests in-process.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from tests.conftest import AUTH, get_conn_for, mock_conn, mock_result
from tests.mock_data import (
    DOM_BY_BAND,
    INV_BOATS_SOLD,
    INV_FLOW,
    INV_STOCK,
    LEADER_FLOW_ROWS,
    LEADER_LISTING_ROWS,
    LISTINGS_BY_BAND,
    MODEL_EFF_ROWS,
    MPT_ROW,
    PRICE_STOCK,
    STATE_FLOW_ROWS,
    STATE_ROWS,
    STATE_STOCK_ROWS,
    TREND_REGIONAL,
    TREND_ROWS,
    VELOCITY_CURRENT,
    VELOCITY_FLOW,
    VELOCITY_PRIOR,
)

# ---------------------------------------------------------------------------
# Session-scoped payload log
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def payload_log():
    """
    Accumulates one entry per endpoint test.  At session teardown writes the
    full log to tests/payload_logs/api_payloads_<timestamp>.json.
    """
    entries: list[dict] = []
    yield entries

    log_dir = Path(__file__).parent / "payload_logs"
    log_dir.mkdir(exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    log_path = log_dir / f"api_payloads_{ts}.json"
    log_path.write_text(
        json.dumps(
            {
                "run_at": datetime.now(timezone.utc).isoformat() + "Z",
                "total_calls": len(entries),
                "calls": entries,
            },
            indent=2,
            default=str,
        )
    )
    print(f"\nPayload log → {log_path.resolve()}")


def _record(log: list, method: str, path: str, status: int, body: dict) -> None:
    log.append({"method": method, "path": path, "status": status, "payload": body})


# ---------------------------------------------------------------------------
# Shared envelope assertion
# ---------------------------------------------------------------------------

ENVELOPE_FIELDS = ("data", "data_as_of", "generated_at", "filters_applied")


def _assert_envelope(body: dict) -> None:
    for field in ENVELOPE_FIELDS:
        assert field in body, f"missing envelope field: {field}"
    assert "T" in body["data_as_of"], "data_as_of must be an ISO datetime"
    assert body["data_as_of"].endswith("Z"), "data_as_of must end with Z"


# ---------------------------------------------------------------------------
# GET /api/v1/inventory/summary
# ---------------------------------------------------------------------------

class TestInventorySummaryPayload:
    def _conn(self):
        return mock_conn(
            mock_result(INV_STOCK),
            mock_result(INV_FLOW),
            mock_result(INV_BOATS_SOLD),
        )

    def test_payload(self, client, payload_log):
        with patch("routers.inventory.get_conn", get_conn_for(self._conn())):
            r = client.get("/api/v1/inventory/summary?time_range=trailing_30", headers=AUTH)

        body = r.json()
        _record(payload_log, "GET", "/api/v1/inventory/summary?time_range=trailing_30",
                r.status_code, body)

        assert r.status_code == 200
        _assert_envelope(body)

        data = body["data"]
        for field in ("active_listings", "boats_sold", "inventory_added",
                      "avg_days_on_market", "pct_aging_past_30d", "dom_distribution"):
            assert field in data, f"missing data field: {field}"

        dom = data["dom_distribution"]
        for bucket in ("bucket_0_7", "bucket_8_15", "bucket_16_30",
                       "bucket_31_60", "bucket_60_plus"):
            assert bucket in dom, f"missing DOM bucket: {bucket}"

        assert data["active_listings"] == 3201
        assert data["boats_sold"] == 148
        assert data["inventory_added"] == 820
        assert data["avg_days_on_market"] == 23.0
        assert dom["bucket_0_7"] == 897


# ---------------------------------------------------------------------------
# GET /api/v1/inventory/trend
# ---------------------------------------------------------------------------

class TestInventoryTrendPayload:
    def _conn(self):
        return mock_conn(mock_result(*TREND_ROWS))

    def test_payload(self, client, payload_log):
        with patch("routers.inventory.get_conn", get_conn_for(self._conn())):
            r = client.get("/api/v1/inventory/trend?time_range=l12m", headers=AUTH)

        body = r.json()
        _record(payload_log, "GET", "/api/v1/inventory/trend?time_range=l12m",
                r.status_code, body)

        assert r.status_code == 200
        _assert_envelope(body)

        series = body["data"]["series"]
        assert isinstance(series, list)
        assert len(series) == 3

        point = series[0]
        for field in ("snapshot_date", "active_listings"):
            assert field in point, f"missing series field: {field}"

        # Dates must be ISO format (YYYY-MM-DD)
        for pt in series:
            parts = pt["snapshot_date"].split("-")
            assert len(parts) == 3 and len(parts[0]) == 4

        assert series[0]["active_listings"] == 3050
        assert series[-1]["active_listings"] == 3201


# ---------------------------------------------------------------------------
# GET /api/v1/inventory/velocity
# ---------------------------------------------------------------------------

class TestInventoryVelocityPayload:
    def _conn(self):
        return mock_conn(
            mock_result(*VELOCITY_CURRENT),
            mock_result(*VELOCITY_FLOW),
            mock_result(*VELOCITY_PRIOR),
        )

    def test_payload(self, client, payload_log):
        with patch("routers.inventory.get_conn", get_conn_for(self._conn())):
            r = client.get("/api/v1/inventory/velocity?time_range=trailing_30", headers=AUTH)

        body = r.json()
        _record(payload_log, "GET", "/api/v1/inventory/velocity?time_range=trailing_30",
                r.status_code, body)

        assert r.status_code == 200
        _assert_envelope(body)

        rows = body["data"]["rows"]
        assert isinstance(rows, list)
        assert len(rows) == 2

        row = rows[0]
        for field in ("model_year", "manufacturer", "model", "year",
                      "avg_days_on_market", "dom_velocity_label",
                      "active_units", "boats_sold", "momentum"):
            assert field in row, f"missing velocity row field: {field}"

        assert row["model_year"] == "2026 Centurion Fi23"
        assert row["momentum"] in ("Accelerating", "Slowing", "Stable")

        # Sorted by DOM ascending
        doms = [r["avg_days_on_market"] for r in rows]
        assert doms == sorted(doms)


# ---------------------------------------------------------------------------
# GET /api/v1/pricing/summary
# ---------------------------------------------------------------------------

class TestPricingSummaryPayload:
    def _conn(self):
        return mock_conn(
            mock_result(PRICE_STOCK),
            mock_result(MPT_ROW),
        )

    def test_payload(self, client, payload_log):
        with patch("routers.pricing.get_conn", get_conn_for(self._conn())):
            r = client.get("/api/v1/pricing/summary?time_range=trailing_30", headers=AUTH)

        body = r.json()
        _record(payload_log, "GET", "/api/v1/pricing/summary?time_range=trailing_30",
                r.status_code, body)

        assert r.status_code == 200
        _assert_envelope(body)

        data = body["data"]
        for field in ("avg_list_price", "median_list_price",
                      "mom_price_change_pct", "top_selling_band"):
            assert field in data, f"missing pricing field: {field}"

        tsb = data["top_selling_band"]
        for field in ("band", "band_label", "units_sold"):
            assert field in tsb, f"missing top_selling_band field: {field}"

        assert data["avg_list_price"] == 142500.0
        assert data["median_list_price"] == 136000.0
        assert abs(data["mom_price_change_pct"] - (-4.1)) < 0.01
        assert tsb["band"] == "over_140k"
        assert tsb["units_sold"] == 134


# ---------------------------------------------------------------------------
# GET /api/v1/pricing/dom-by-price-tier
# ---------------------------------------------------------------------------

class TestDomByPriceTierPayload:
    def _conn(self):
        return mock_conn(mock_result(DOM_BY_BAND))

    def test_payload(self, client, payload_log):
        with patch("routers.pricing.get_conn", get_conn_for(self._conn())):
            r = client.get("/api/v1/pricing/dom-by-price-tier?time_range=trailing_30", headers=AUTH)

        body = r.json()
        _record(payload_log, "GET", "/api/v1/pricing/dom-by-price-tier?time_range=trailing_30",
                r.status_code, body)

        assert r.status_code == 200
        _assert_envelope(body)

        bands = body["data"]["bands"]
        assert len(bands) == 6

        band = bands[0]
        for field in ("band", "band_label", "avg_days_on_market", "velocity_label"):
            assert field in band, f"missing band field: {field}"

        band_ids = [b["band"] for b in bands]
        assert band_ids == ["under_60k", "60k_80k", "80k_100k", "100k_120k", "120k_140k", "over_140k"]

        valid_labels = {"Fast", "Healthy", "Slow", "Very Slow"}
        for b in bands:
            assert b["velocity_label"] in valid_labels


# ---------------------------------------------------------------------------
# GET /api/v1/pricing/listings-by-price-tier
# ---------------------------------------------------------------------------

class TestListingsByPriceTierPayload:
    def _conn(self):
        return mock_conn(mock_result(LISTINGS_BY_BAND))

    def test_payload(self, client, payload_log):
        with patch("routers.pricing.get_conn", get_conn_for(self._conn())):
            r = client.get("/api/v1/pricing/listings-by-price-tier?time_range=trailing_30", headers=AUTH)

        body = r.json()
        _record(payload_log, "GET", "/api/v1/pricing/listings-by-price-tier?time_range=trailing_30",
                r.status_code, body)

        assert r.status_code == 200
        _assert_envelope(body)

        bands = body["data"]["bands"]
        assert len(bands) == 6

        band = bands[0]
        for field in ("band", "band_label", "listings"):
            assert field in band, f"missing band field: {field}"

        for b in bands:
            assert b["band_label"] != "", "band_label must not be empty"

        counts = {b["band"]: b["listings"] for b in bands}
        assert counts["under_60k"] == 12
        assert counts["80k_100k"] == 618
        assert counts["100k_120k"] == 891


# ---------------------------------------------------------------------------
# GET /api/v1/pricing/model-efficiency
# ---------------------------------------------------------------------------

class TestModelEfficiencyPayload:
    def _conn(self):
        return mock_conn(mock_result(*MODEL_EFF_ROWS))

    def test_payload(self, client, payload_log):
        with patch("routers.pricing.get_conn", get_conn_for(self._conn())):
            r = client.get("/api/v1/pricing/model-efficiency?time_range=trailing_30", headers=AUTH)

        body = r.json()
        _record(payload_log, "GET", "/api/v1/pricing/model-efficiency?time_range=trailing_30",
                r.status_code, body)

        assert r.status_code == 200
        _assert_envelope(body)

        rows = body["data"]["rows"]
        assert len(rows) == 2

        row = rows[0]
        for field in ("rank", "model_year", "manufacturer", "model", "year",
                      "avg_list_price", "price_band_low", "price_band_high",
                      "price_band_label", "avg_days_on_market",
                      "dom_velocity_label", "listings"):
            assert field in row, f"missing model-efficiency field: {field}"

        # Ranked by DOM ascending — Ri235 (12.4) before Ri245 (21.7)
        assert rows[0]["rank"] == 1
        assert rows[1]["rank"] == 2
        assert rows[0]["avg_days_on_market"] < rows[1]["avg_days_on_market"]
        assert rows[0]["price_band_label"] == "$68k–$91k"


# ---------------------------------------------------------------------------
# GET /api/v1/regional/summary
# ---------------------------------------------------------------------------

class TestRegionalSummaryPayload:
    def _conn(self):
        return mock_conn(
            mock_result(*STATE_ROWS),
            mock_result(*TREND_REGIONAL),
        )

    def test_payload(self, client, payload_log):
        with patch("routers.regional.get_conn", get_conn_for(self._conn())):
            r = client.get("/api/v1/regional/summary?time_range=trailing_30", headers=AUTH)

        body = r.json()
        _record(payload_log, "GET", "/api/v1/regional/summary?time_range=trailing_30",
                r.status_code, body)

        assert r.status_code == 200
        _assert_envelope(body)

        data = body["data"]
        for field in ("national_avg_dom", "fastest_market", "slowest_market",
                      "top_growth_state", "sales_trends"):
            assert field in data, f"missing regional summary field: {field}"

        fm = data["fastest_market"]
        for field in ("state", "state_name", "avg_dom", "pct_vs_national"):
            assert field in fm, f"missing fastest_market field: {field}"

        st = data["sales_trends"]
        for field in ("states_rising", "states_falling"):
            assert field in st, f"missing sales_trends field: {field}"

        assert data["fastest_market"]["state"] == "TX"
        assert data["fastest_market"]["state_name"] == "Texas"
        assert data["slowest_market"]["state"] == "CA"
        assert data["top_growth_state"]["state"] == "TX"
        assert abs(data["top_growth_state"]["yoy_supply_change_pct"] - 9.1) < 0.1
        assert st["states_rising"] == 1
        assert st["states_falling"] == 1


# ---------------------------------------------------------------------------
# GET /api/v1/regional/state-overview
# ---------------------------------------------------------------------------

class TestRegionalStateOverviewPayload:
    def _conn(self):
        return mock_conn(
            mock_result(*STATE_STOCK_ROWS),
            mock_result(*STATE_FLOW_ROWS),
        )

    def test_payload(self, client, payload_log):
        with patch("routers.regional.get_conn", get_conn_for(self._conn())):
            r = client.get("/api/v1/regional/state-overview?time_range=trailing_30", headers=AUTH)

        body = r.json()
        _record(payload_log, "GET", "/api/v1/regional/state-overview?time_range=trailing_30",
                r.status_code, body)

        assert r.status_code == 200
        _assert_envelope(body)

        data = body["data"]
        assert "national_total_boats_sold" in data
        assert "rows" in data

        rows = data["rows"]
        assert len(rows) == 3

        row = rows[0]
        for field in ("state", "state_name", "listings", "avg_days_on_market",
                      "dom_velocity_label", "boats_sold", "pct_market", "avg_list_price"):
            assert field in row, f"missing state-overview row field: {field}"

        assert data["national_total_boats_sold"] == 598

        # Sorted by boats_sold descending
        sales = [r["boats_sold"] for r in rows]
        assert sales == sorted(sales, reverse=True)

        # pct_market must sum to ~100%
        assert abs(sum(r["pct_market"] for r in rows) - 100.0) < 0.1

        name_map = {r["state"]: r["state_name"] for r in rows}
        assert name_map["FL"] == "Florida"
        assert name_map["TX"] == "Texas"


# ---------------------------------------------------------------------------
# GET /api/v1/regional/market-leaders
# ---------------------------------------------------------------------------

class TestRegionalMarketLeadersPayload:
    def _conn(self):
        return mock_conn(
            mock_result(*LEADER_FLOW_ROWS),
            mock_result(*LEADER_LISTING_ROWS),
        )

    def test_payload(self, client, payload_log):
        with patch("routers.regional.get_conn", get_conn_for(self._conn())):
            r = client.get(
                "/api/v1/regional/market-leaders?time_range=trailing_30&top_n=3", headers=AUTH
            )

        body = r.json()
        _record(payload_log, "GET", "/api/v1/regional/market-leaders?time_range=trailing_30&top_n=3",
                r.status_code, body)

        assert r.status_code == 200
        _assert_envelope(body)

        data = body["data"]
        for field in ("top_states", "bottom_states"):
            assert field in data, f"missing market-leaders field: {field}"

        assert len(data["top_states"]) == 3
        assert len(data["bottom_states"]) == 3

        row = data["top_states"][0]
        for field in ("rank", "state", "state_name", "boats_sold", "listings"):
            assert field in row, f"missing market-leaders row field: {field}"

        # Top sorted by sales desc; bottom by sales asc
        top_sales = [r["boats_sold"] for r in data["top_states"]]
        assert top_sales == sorted(top_sales, reverse=True)

        assert data["top_states"][0]["state"] == "FL"
        assert data["top_states"][0]["boats_sold"] == 226
        assert data["bottom_states"][0]["state"] == "AK"
        assert data["top_states"][0]["state_name"] == "Florida"

        # No state appears in both top and bottom
        top_codes = {r["state"] for r in data["top_states"]}
        bottom_codes = {r["state"] for r in data["bottom_states"]}
        assert top_codes.isdisjoint(bottom_codes)


# ---------------------------------------------------------------------------
# Filter tests — inventory/summary
# ---------------------------------------------------------------------------

class TestInventorySummaryFilters:
    def test_inventory_type_new(self, client, payload_log):
        """inventory_type is a WHERE clause — same 3 queries as the baseline."""
        conn = mock_conn(
            mock_result(INV_STOCK),
            mock_result(INV_FLOW),
            mock_result(INV_BOATS_SOLD),
        )
        with patch("routers.inventory.get_conn", get_conn_for(conn)):
            r = client.get(
                "/api/v1/inventory/summary?time_range=trailing_30&inventory_type=new",
                headers=AUTH,
            )
        body = r.json()
        _record(payload_log, "GET",
                "/api/v1/inventory/summary?time_range=trailing_30&inventory_type=new",
                r.status_code, body)
        assert r.status_code == 200
        _assert_envelope(body)
        assert body["filters_applied"]["inventory_type"] == "new"

    def test_make_filter(self, client, payload_log):
        """make filter resolves manufacturer_key via 1 extra query before 3 data queries."""
        conn = mock_conn(
            mock_result((1,)),          # manufacturer key lookup — row[0] = 1
            mock_result(INV_STOCK),
            mock_result(INV_FLOW),
            mock_result(INV_BOATS_SOLD),
        )
        with patch("routers.inventory.get_conn", get_conn_for(conn)):
            r = client.get(
                "/api/v1/inventory/summary?time_range=trailing_30&make=centurion",
                headers=AUTH,
            )
        body = r.json()
        _record(payload_log, "GET",
                "/api/v1/inventory/summary?time_range=trailing_30&make=centurion",
                r.status_code, body)
        assert r.status_code == 200
        _assert_envelope(body)
        assert body["filters_applied"]["make"] == "centurion"

    def test_make_and_model_filter(self, client, payload_log):
        """make+model resolves 2 surrogate keys before the 3 data queries."""
        conn = mock_conn(
            mock_result((1,)),          # manufacturer key
            mock_result((10,)),         # boat_model_key — fetchall returns [(10,)]
            mock_result(INV_STOCK),
            mock_result(INV_FLOW),
            mock_result(INV_BOATS_SOLD),
        )
        with patch("routers.inventory.get_conn", get_conn_for(conn)):
            r = client.get(
                "/api/v1/inventory/summary?time_range=trailing_30&make=centurion&model=fi23",
                headers=AUTH,
            )
        body = r.json()
        _record(payload_log, "GET",
                "/api/v1/inventory/summary?time_range=trailing_30&make=centurion&model=fi23",
                r.status_code, body)
        assert r.status_code == 200
        _assert_envelope(body)
        assert body["filters_applied"]["make"] == "centurion"
        assert body["filters_applied"]["model"] == "fi23"

    def test_unknown_make_returns_400(self, client, payload_log):
        """make not found in dim_manufacturer → 400 INVALID_PARAM."""
        conn = mock_conn(mock_result())  # fetchone() → None
        with patch("routers.inventory.get_conn", get_conn_for(conn)):
            r = client.get(
                "/api/v1/inventory/summary?time_range=trailing_30&make=unknown_brand",
                headers=AUTH,
            )
        body = r.json()
        _record(payload_log, "GET",
                "/api/v1/inventory/summary?time_range=trailing_30&make=unknown_brand",
                r.status_code, body)
        assert r.status_code == 400
        assert body["error"]["code"] == "INVALID_PARAM"
        assert body["error"]["field"] == "make"

    def test_unknown_model_returns_400(self, client, payload_log):
        """make found but model not in dim_boat_model → 400 INVALID_PARAM."""
        conn = mock_conn(
            mock_result((1,)),   # make found
            mock_result(),       # model fetchall() → []
        )
        with patch("routers.inventory.get_conn", get_conn_for(conn)):
            r = client.get(
                "/api/v1/inventory/summary?time_range=trailing_30&make=centurion&model=unknown_model",
                headers=AUTH,
            )
        body = r.json()
        _record(payload_log, "GET",
                "/api/v1/inventory/summary?time_range=trailing_30&make=centurion&model=unknown_model",
                r.status_code, body)
        assert r.status_code == 400
        assert body["error"]["code"] == "INVALID_PARAM"
        assert body["error"]["field"] == "model"


# ---------------------------------------------------------------------------
# Filter tests — pricing/summary
# ---------------------------------------------------------------------------

class TestPricingSummaryFilters:
    def test_inventory_type_used(self, client, payload_log):
        """inventory_type=used — same 2 queries as the baseline."""
        conn = mock_conn(
            mock_result(PRICE_STOCK),
            mock_result(MPT_ROW),
        )
        with patch("routers.pricing.get_conn", get_conn_for(conn)):
            r = client.get(
                "/api/v1/pricing/summary?time_range=trailing_30&inventory_type=used",
                headers=AUTH,
            )
        body = r.json()
        _record(payload_log, "GET",
                "/api/v1/pricing/summary?time_range=trailing_30&inventory_type=used",
                r.status_code, body)
        assert r.status_code == 200
        _assert_envelope(body)
        assert body["filters_applied"]["inventory_type"] == "used"

    def test_make_filter(self, client, payload_log):
        """make filter adds 1 key-resolution query before the 2 data queries."""
        conn = mock_conn(
            mock_result((1,)),          # manufacturer key lookup
            mock_result(PRICE_STOCK),
            mock_result(MPT_ROW),
        )
        with patch("routers.pricing.get_conn", get_conn_for(conn)):
            r = client.get(
                "/api/v1/pricing/summary?time_range=trailing_30&make=centurion",
                headers=AUTH,
            )
        body = r.json()
        _record(payload_log, "GET",
                "/api/v1/pricing/summary?time_range=trailing_30&make=centurion",
                r.status_code, body)
        assert r.status_code == 200
        _assert_envelope(body)
        assert body["filters_applied"]["make"] == "centurion"


# ---------------------------------------------------------------------------
# Filter tests — regional/summary
# ---------------------------------------------------------------------------

class TestRegionalSummaryFilters:
    def test_state_filter_rejected(self, client, payload_log):
        """regional/summary does not support state= — must return 400 INVALID_PARAM."""
        r = client.get(
            "/api/v1/regional/summary?time_range=trailing_30&state=TX",
            headers=AUTH,
        )
        body = r.json()
        _record(payload_log, "GET",
                "/api/v1/regional/summary?time_range=trailing_30&state=TX",
                r.status_code, body)
        assert r.status_code == 400
        assert body["error"]["code"] == "INVALID_PARAM"
        assert body["error"]["field"] == "state"

    def test_inventory_type_new(self, client, payload_log):
        conn = mock_conn(
            mock_result(*STATE_ROWS),
            mock_result(*TREND_REGIONAL),
        )
        with patch("routers.regional.get_conn", get_conn_for(conn)):
            r = client.get(
                "/api/v1/regional/summary?time_range=trailing_30&inventory_type=new",
                headers=AUTH,
            )
        body = r.json()
        _record(payload_log, "GET",
                "/api/v1/regional/summary?time_range=trailing_30&inventory_type=new",
                r.status_code, body)
        assert r.status_code == 200
        _assert_envelope(body)
        assert body["filters_applied"]["inventory_type"] == "new"

    def test_make_filter(self, client, payload_log):
        """make filter adds 1 key-resolution query before the 2 data queries."""
        conn = mock_conn(
            mock_result((1,)),           # manufacturer key
            mock_result(*STATE_ROWS),
            mock_result(*TREND_REGIONAL),
        )
        with patch("routers.regional.get_conn", get_conn_for(conn)):
            r = client.get(
                "/api/v1/regional/summary?time_range=trailing_30&make=centurion",
                headers=AUTH,
            )
        body = r.json()
        _record(payload_log, "GET",
                "/api/v1/regional/summary?time_range=trailing_30&make=centurion",
                r.status_code, body)
        assert r.status_code == 200
        _assert_envelope(body)
        assert body["filters_applied"]["make"] == "centurion"
