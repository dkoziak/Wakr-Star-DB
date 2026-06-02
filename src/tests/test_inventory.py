from unittest.mock import patch

import pytest

from tests.conftest import AUTH, get_conn_for, mock_conn, mock_result
from tests.mock_data import (
    INV_BOATS_SOLD,
    INV_FLOW,
    INV_STOCK,
    TREND_ROWS,
    VELOCITY_CURRENT,
    VELOCITY_FLOW,
    VELOCITY_PRIOR,
)

BASE = "/api/v1/inventory"


# ---------------------------------------------------------------------------
# /summary
# ---------------------------------------------------------------------------

class TestInventorySummary:
    def _conn(self):
        return mock_conn(
            mock_result(INV_STOCK),       # STOCK query
            mock_result(INV_FLOW),        # FLOW query (new_listings → inventory_added)
            mock_result(INV_BOATS_SOLD),  # fact_estimated_sale (boats_sold)
        )

    def test_happy_path(self, client):
        with patch("routers.inventory.get_conn", get_conn_for(self._conn())):
            r = client.get(f"{BASE}/summary?time_range=trailing_30", headers=AUTH)

        assert r.status_code == 200
        body = r.json()
        assert "data" in body
        assert "data_as_of" in body
        assert "generated_at" in body
        assert "filters_applied" in body

    def test_active_listings(self, client):
        with patch("routers.inventory.get_conn", get_conn_for(self._conn())):
            data = client.get(f"{BASE}/summary?time_range=trailing_30", headers=AUTH).json()["data"]

        assert data["active_listings"] == 3201
        assert data["boats_sold"] == 148
        assert data["inventory_added"] == 820

    def test_avg_dom(self, client):
        with patch("routers.inventory.get_conn", get_conn_for(self._conn())):
            data = client.get(f"{BASE}/summary?time_range=trailing_30", headers=AUTH).json()["data"]

        assert data["avg_days_on_market"] == 23.0

    def test_pct_aging(self, client):
        # (bucket_31_60=748 + bucket_60_plus=0) / 3201 * 100 ≈ 23.37
        with patch("routers.inventory.get_conn", get_conn_for(self._conn())):
            data = client.get(f"{BASE}/summary?time_range=trailing_30", headers=AUTH).json()["data"]

        assert abs(data["pct_aging_past_30d"] - 23.37) < 0.1

    def test_dom_distribution_shape(self, client):
        with patch("routers.inventory.get_conn", get_conn_for(self._conn())):
            dom = client.get(f"{BASE}/summary?time_range=trailing_30", headers=AUTH).json()["data"]["dom_distribution"]

        assert dom["bucket_0_7"] == 897
        assert dom["bucket_8_15"] == 1082
        assert dom["bucket_16_30"] == 762
        assert dom["bucket_31_60"] == 748
        assert dom["bucket_60_plus"] == 0

    def test_filters_applied_echo(self, client):
        with patch("routers.inventory.get_conn", get_conn_for(self._conn())):
            fa = client.get(
                f"{BASE}/summary?time_range=trailing_30&inventory_type=new", headers=AUTH
            ).json()["filters_applied"]

        assert fa["time_range"] == "trailing_30"
        assert fa["inventory_type"] == "new"

    def test_data_as_of_is_iso_datetime(self, client):
        with patch("routers.inventory.get_conn", get_conn_for(self._conn())):
            body = client.get(f"{BASE}/summary?time_range=trailing_30", headers=AUTH).json()

        # Must be a full ISO datetime, not just a date
        assert "T" in body["data_as_of"]
        assert body["data_as_of"].endswith("Z")

    def test_as_of_date_param_accepted(self, client):
        with patch("routers.inventory.get_conn", get_conn_for(self._conn())):
            r = client.get(
                f"{BASE}/summary?time_range=trailing_30&as_of_date=2026-04-01", headers=AUTH
            )

        assert r.status_code == 200

    def test_requires_time_range(self, client):
        r = client.get(f"{BASE}/summary", headers=AUTH)
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "MISSING_PARAM"

    def test_invalid_time_range(self, client):
        r = client.get(f"{BASE}/summary?time_range=bad_value", headers=AUTH)
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "INVALID_PARAM"

    def test_requires_auth(self, client):
        r = client.get(f"{BASE}/summary?time_range=trailing_30")
        assert r.status_code == 401
        assert r.json()["error"]["code"] == "UNAUTHORIZED"

    def test_no_data_returns_404(self, client):
        from types import SimpleNamespace as Row
        empty_conn = mock_conn(mock_result(Row(active_listings=None, avg_dom=None,
                                               b0=0, b1=0, b2=0, b3=0, b4=0,
                                               last_scrape_date=None)))
        with patch("routers.inventory.get_conn", get_conn_for(empty_conn)):
            r = client.get(f"{BASE}/summary?time_range=trailing_30", headers=AUTH)

        assert r.status_code == 404
        assert r.json()["error"]["code"] == "NO_DATA"


# ---------------------------------------------------------------------------
# /trend
# ---------------------------------------------------------------------------

class TestInventoryTrend:
    def _conn(self):
        return mock_conn(mock_result(*TREND_ROWS))

    def test_happy_path(self, client):
        with patch("routers.inventory.get_conn", get_conn_for(self._conn())):
            r = client.get(f"{BASE}/trend?time_range=l12m", headers=AUTH)

        assert r.status_code == 200

    def test_series_structure(self, client):
        with patch("routers.inventory.get_conn", get_conn_for(self._conn())):
            series = client.get(f"{BASE}/trend?time_range=l12m", headers=AUTH).json()["data"]["series"]

        assert len(series) == 3
        assert series[0]["snapshot_date"] == "2026-04-30"
        assert series[0]["active_listings"] == 3050
        assert series[-1]["active_listings"] == 3201

    def test_series_dates_are_iso(self, client):
        with patch("routers.inventory.get_conn", get_conn_for(self._conn())):
            series = client.get(f"{BASE}/trend?time_range=trailing_30", headers=AUTH).json()["data"]["series"]

        for point in series:
            parts = point["snapshot_date"].split("-")
            assert len(parts) == 3
            assert len(parts[0]) == 4  # year

    def test_as_of_date_param_accepted(self, client):
        with patch("routers.inventory.get_conn", get_conn_for(self._conn())):
            r = client.get(
                f"{BASE}/trend?time_range=trailing_30&as_of_date=2026-04-01", headers=AUTH
            )

        assert r.status_code == 200

    def test_no_data_returns_404(self, client):
        empty_conn = mock_conn(mock_result())   # fetchall returns []
        with patch("routers.inventory.get_conn", get_conn_for(empty_conn)):
            r = client.get(f"{BASE}/trend?time_range=trailing_30", headers=AUTH)

        assert r.status_code == 404


# ---------------------------------------------------------------------------
# /velocity
# ---------------------------------------------------------------------------

class TestInventoryVelocity:
    def _conn(self):
        return mock_conn(
            mock_result(*VELOCITY_CURRENT),  # current STOCK + names
            mock_result(*VELOCITY_FLOW),     # fact_estimated_sale per model
            mock_result(*VELOCITY_PRIOR),    # prior STOCK
        )

    def test_happy_path(self, client):
        with patch("routers.inventory.get_conn", get_conn_for(self._conn())):
            r = client.get(f"{BASE}/velocity?time_range=trailing_30", headers=AUTH)

        assert r.status_code == 200

    def test_row_count(self, client):
        with patch("routers.inventory.get_conn", get_conn_for(self._conn())):
            rows = client.get(f"{BASE}/velocity?time_range=trailing_30", headers=AUTH).json()["data"]["rows"]

        assert len(rows) == 2

    def test_row_fields_present(self, client):
        with patch("routers.inventory.get_conn", get_conn_for(self._conn())):
            row = client.get(f"{BASE}/velocity?time_range=trailing_30", headers=AUTH).json()["data"]["rows"][0]

        for field in ("model_year", "manufacturer", "model", "year",
                      "avg_days_on_market", "dom_velocity_label",
                      "active_units", "boats_sold", "momentum"):
            assert field in row, f"missing field: {field}"

    def test_momentum_accelerating(self, client):
        # Fi23: cur_dom=14.2, prior_dom=17.0 → (14.2-17.0)/17.0 = -16.5% → Accelerating
        with patch("routers.inventory.get_conn", get_conn_for(self._conn())):
            rows = client.get(f"{BASE}/velocity?time_range=trailing_30", headers=AUTH).json()["data"]["rows"]

        fi23 = next(r for r in rows if "Fi23" in r["model_year"])
        assert fi23["momentum"] == "Accelerating"

    def test_momentum_slowing(self, client):
        # Ri245: cur_dom=28.5, prior_dom=25.0 → (28.5-25.0)/25.0 = +14% → Slowing
        with patch("routers.inventory.get_conn", get_conn_for(self._conn())):
            rows = client.get(f"{BASE}/velocity?time_range=trailing_30", headers=AUTH).json()["data"]["rows"]

        ri245 = next(r for r in rows if "Ri245" in r["model_year"])
        assert ri245["momentum"] == "Slowing"

    def test_dom_velocity_label_fast(self, client):
        with patch("routers.inventory.get_conn", get_conn_for(self._conn())):
            rows = client.get(f"{BASE}/velocity?time_range=trailing_30", headers=AUTH).json()["data"]["rows"]

        fi23 = next(r for r in rows if "Fi23" in r["model_year"])
        assert fi23["dom_velocity_label"] == "Fast"   # 14.2 < 15

    def test_sorted_by_dom_ascending(self, client):
        with patch("routers.inventory.get_conn", get_conn_for(self._conn())):
            rows = client.get(f"{BASE}/velocity?time_range=trailing_30", headers=AUTH).json()["data"]["rows"]

        doms = [r["avg_days_on_market"] for r in rows]
        assert doms == sorted(doms)

    def test_model_year_label_format(self, client):
        with patch("routers.inventory.get_conn", get_conn_for(self._conn())):
            rows = client.get(f"{BASE}/velocity?time_range=trailing_30", headers=AUTH).json()["data"]["rows"]

        fi23 = next(r for r in rows if "Fi23" in r["model_year"])
        assert fi23["model_year"] == "2026 Centurion Fi23"

    def test_as_of_date_param_accepted(self, client):
        with patch("routers.inventory.get_conn", get_conn_for(self._conn())):
            r = client.get(
                f"{BASE}/velocity?time_range=trailing_30&as_of_date=2026-04-01", headers=AUTH
            )

        assert r.status_code == 200

    def test_no_data_returns_404(self, client):
        empty_conn = mock_conn(mock_result())
        with patch("routers.inventory.get_conn", get_conn_for(empty_conn)):
            r = client.get(f"{BASE}/velocity?time_range=trailing_30", headers=AUTH)

        assert r.status_code == 404
