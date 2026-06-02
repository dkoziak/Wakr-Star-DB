"""
test_live_payloads.py

One test per endpoint against a real database.  No DB mocking — get_conn is
never patched, so the FastAPI app talks to the actual Star DB.

Prerequisites
-------------
1. Seed the database:
       python -c "from tests.seed_test_db import seed_test_db; seed_test_db()"

2. Set environment variables and run:
       STARDB_URL=postgresql+asyncpg://postgres:postgres@127.0.0.1:5433/wakr_stardb \\
       RUN_LIVE_TESTS=1 \\
       python -m pytest tests/test_live_payloads.py -v

The suite is skipped automatically unless RUN_LIVE_TESTS=1.
Assertions check response shape and status only — not specific values —
so the tests pass regardless of what data is in the database.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tests.conftest import AUTH

# ---------------------------------------------------------------------------
# Skip guard — never runs unless explicitly requested
# ---------------------------------------------------------------------------

pytestmark = pytest.mark.skipif(
    not os.environ.get("RUN_LIVE_TESTS"),
    reason="Set RUN_LIVE_TESTS=1 to run live DB tests",
)

# ---------------------------------------------------------------------------
# Session-scoped payload log (separate file from the mock-based run)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def live_payload_log():
    entries: list[dict] = []
    yield entries

    log_dir = Path(__file__).parent / "payload_logs"
    log_dir.mkdir(exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    log_path = log_dir / f"live_api_payloads_{ts}.json"
    log_path.write_text(
        json.dumps(
            {
                "run_at": datetime.now(timezone.utc).isoformat() + "Z",
                "db_url": os.environ.get("STARDB_URL", ""),
                "total_calls": len(entries),
                "calls": entries,
            },
            indent=2,
            default=str,
        )
    )
    print(f"\nLive payload log → {log_path.resolve()}")


def _log(log: list, method: str, path: str, status: int, body: dict) -> None:
    log.append({"method": method, "path": path, "status": status, "payload": body})


# ---------------------------------------------------------------------------
# Shared envelope assertion
# ---------------------------------------------------------------------------

ENVELOPE_FIELDS = ("data", "data_as_of", "generated_at", "filters_applied")


def _assert_envelope(body: dict) -> None:
    for f in ENVELOPE_FIELDS:
        assert f in body, f"missing envelope field: {f}"
    assert "T" in body["data_as_of"]
    assert body["data_as_of"].endswith("Z")


# ---------------------------------------------------------------------------
# GET /api/v1/inventory/summary
# ---------------------------------------------------------------------------

class TestLiveInventorySummary:
    def test_payload(self, client, live_payload_log):
        r = client.get("/api/v1/inventory/summary?time_range=trailing_30", headers=AUTH)
        body = r.json()
        _log(live_payload_log, "GET", "/api/v1/inventory/summary?time_range=trailing_30",
             r.status_code, body)

        assert r.status_code == 200
        _assert_envelope(body)
        data = body["data"]
        for f in ("active_listings", "boats_sold", "inventory_added",
                  "avg_days_on_market", "pct_aging_past_30d", "dom_distribution"):
            assert f in data, f"missing field: {f}"
        dom = data["dom_distribution"]
        for b in ("bucket_0_7", "bucket_8_15", "bucket_16_30", "bucket_31_60", "bucket_60_plus"):
            assert b in dom
        assert isinstance(data["active_listings"], int)
        assert data["active_listings"] > 0


# ---------------------------------------------------------------------------
# GET /api/v1/inventory/trend
# ---------------------------------------------------------------------------

class TestLiveInventoryTrend:
    def test_payload(self, client, live_payload_log):
        r = client.get("/api/v1/inventory/trend?time_range=l12m", headers=AUTH)
        body = r.json()
        _log(live_payload_log, "GET", "/api/v1/inventory/trend?time_range=l12m",
             r.status_code, body)

        assert r.status_code == 200
        _assert_envelope(body)
        series = body["data"]["series"]
        assert isinstance(series, list)
        assert len(series) > 0
        for pt in series:
            assert "snapshot_date" in pt
            assert "active_listings" in pt
            parts = pt["snapshot_date"].split("-")
            assert len(parts) == 3 and len(parts[0]) == 4


# ---------------------------------------------------------------------------
# GET /api/v1/inventory/velocity
# ---------------------------------------------------------------------------

class TestLiveInventoryVelocity:
    def test_payload(self, client, live_payload_log):
        r = client.get("/api/v1/inventory/velocity?time_range=trailing_30", headers=AUTH)
        body = r.json()
        _log(live_payload_log, "GET", "/api/v1/inventory/velocity?time_range=trailing_30",
             r.status_code, body)

        assert r.status_code == 200
        _assert_envelope(body)
        rows = body["data"]["rows"]
        assert isinstance(rows, list)
        assert len(rows) > 0
        for row in rows:
            for f in ("model_year", "avg_days_on_market", "dom_velocity_label",
                      "active_units", "boats_sold", "momentum"):
                assert f in row, f"missing velocity row field: {f}"


# ---------------------------------------------------------------------------
# GET /api/v1/pricing/summary
# ---------------------------------------------------------------------------

class TestLivePricingSummary:
    def test_payload(self, client, live_payload_log):
        r = client.get("/api/v1/pricing/summary?time_range=trailing_30", headers=AUTH)
        body = r.json()
        _log(live_payload_log, "GET", "/api/v1/pricing/summary?time_range=trailing_30",
             r.status_code, body)

        assert r.status_code == 200
        _assert_envelope(body)
        data = body["data"]
        for f in ("avg_list_price", "median_list_price",
                  "mom_price_change_pct", "top_selling_band"):
            assert f in data, f"missing field: {f}"
        band = data["top_selling_band"]
        for f in ("band", "band_label", "units_sold"):
            assert f in band, f"missing band field: {f}"


# ---------------------------------------------------------------------------
# GET /api/v1/pricing/dom-by-price-tier
# ---------------------------------------------------------------------------

class TestLivePricingDomByTier:
    def test_payload(self, client, live_payload_log):
        r = client.get("/api/v1/pricing/dom-by-price-tier?time_range=trailing_30", headers=AUTH)
        body = r.json()
        _log(live_payload_log, "GET", "/api/v1/pricing/dom-by-price-tier?time_range=trailing_30",
             r.status_code, body)

        assert r.status_code == 200
        _assert_envelope(body)
        bands = body["data"]["bands"]
        assert len(bands) == 6
        for band in bands:
            for f in ("band", "band_label", "avg_days_on_market", "velocity_label"):
                assert f in band


# ---------------------------------------------------------------------------
# GET /api/v1/pricing/listings-by-price-tier
# ---------------------------------------------------------------------------

class TestLivePricingListingsByTier:
    def test_payload(self, client, live_payload_log):
        r = client.get("/api/v1/pricing/listings-by-price-tier?time_range=trailing_30", headers=AUTH)
        body = r.json()
        _log(live_payload_log, "GET", "/api/v1/pricing/listings-by-price-tier?time_range=trailing_30",
             r.status_code, body)

        assert r.status_code == 200
        _assert_envelope(body)
        bands = body["data"]["bands"]
        assert len(bands) == 6
        for band in bands:
            assert "band" in band
            assert "listings" in band


# ---------------------------------------------------------------------------
# GET /api/v1/pricing/model-efficiency
# ---------------------------------------------------------------------------

class TestLivePricingModelEfficiency:
    def test_payload(self, client, live_payload_log):
        r = client.get("/api/v1/pricing/model-efficiency?time_range=trailing_30", headers=AUTH)
        body = r.json()
        _log(live_payload_log, "GET", "/api/v1/pricing/model-efficiency?time_range=trailing_30",
             r.status_code, body)

        assert r.status_code == 200
        _assert_envelope(body)
        rows = body["data"]["rows"]
        assert isinstance(rows, list)
        assert len(rows) > 0
        for row in rows:
            for f in ("rank", "model_year", "avg_list_price",
                      "avg_days_on_market", "dom_velocity_label", "listings"):
                assert f in row, f"missing model-efficiency field: {f}"


# ---------------------------------------------------------------------------
# GET /api/v1/regional/summary
# ---------------------------------------------------------------------------

class TestLiveRegionalSummary:
    def test_payload(self, client, live_payload_log):
        r = client.get("/api/v1/regional/summary?time_range=trailing_30", headers=AUTH)
        body = r.json()
        _log(live_payload_log, "GET", "/api/v1/regional/summary?time_range=trailing_30",
             r.status_code, body)

        assert r.status_code == 200
        _assert_envelope(body)
        data = body["data"]
        for f in ("national_avg_dom", "fastest_market", "slowest_market",
                  "top_growth_state", "sales_trends"):
            assert f in data, f"missing regional summary field: {f}"
        assert "states_rising" in data["sales_trends"]
        assert "states_falling" in data["sales_trends"]


# ---------------------------------------------------------------------------
# GET /api/v1/regional/state-overview
# ---------------------------------------------------------------------------

class TestLiveRegionalStateOverview:
    def test_payload(self, client, live_payload_log):
        r = client.get("/api/v1/regional/state-overview?time_range=trailing_30", headers=AUTH)
        body = r.json()
        _log(live_payload_log, "GET", "/api/v1/regional/state-overview?time_range=trailing_30",
             r.status_code, body)

        assert r.status_code == 200
        _assert_envelope(body)
        assert "national_total_boats_sold" in body["data"]
        rows = body["data"]["rows"]
        assert isinstance(rows, list)
        assert len(rows) > 0
        for row in rows:
            for f in ("state", "state_name", "listings",
                      "avg_days_on_market", "boats_sold", "pct_market"):
                assert f in row, f"missing state-overview field: {f}"


# ---------------------------------------------------------------------------
# GET /api/v1/regional/market-leaders
# ---------------------------------------------------------------------------

class TestLiveRegionalMarketLeaders:
    def test_payload(self, client, live_payload_log):
        r = client.get("/api/v1/regional/market-leaders?time_range=trailing_30&top_n=3",
                       headers=AUTH)
        body = r.json()
        _log(live_payload_log, "GET",
             "/api/v1/regional/market-leaders?time_range=trailing_30&top_n=3",
             r.status_code, body)

        assert r.status_code == 200
        _assert_envelope(body)
        data = body["data"]
        assert "top_states" in data
        assert "bottom_states" in data
        assert len(data["top_states"]) == 3
        for row in data["top_states"] + data["bottom_states"]:
            for f in ("rank", "state", "state_name", "boats_sold", "listings"):
                assert f in row, f"missing market-leaders field: {f}"
