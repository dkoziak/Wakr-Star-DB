from unittest.mock import patch

import pytest

from tests.conftest import AUTH, get_conn_for, mock_conn, mock_result
from tests.mock_data import (
    LEADER_FLOW_ROWS,
    LEADER_LISTING_ROWS,
    STATE_FLOW_ROWS,
    STATE_ROWS,
    STATE_STOCK_ROWS,
    TREND_REGIONAL,
)

BASE = "/api/v1/regional"


# ---------------------------------------------------------------------------
# /summary
# ---------------------------------------------------------------------------

class TestRegionalSummary:
    def _conn(self):
        return mock_conn(
            mock_result(*STATE_ROWS),       # per-state avg_dom from mart_daily_snapshot
            mock_result(*TREND_REGIONAL),   # YoY + sales trend from mart_regional_summary
        )

    def test_happy_path(self, client):
        with patch("routers.regional.get_conn", get_conn_for(self._conn())):
            r = client.get(f"{BASE}/summary?time_range=trailing_30", headers=AUTH)

        assert r.status_code == 200

    def test_national_avg_dom(self, client):
        # Weighted: (21.3*487 + 14.9*412 + 26.1*389) / (487+412+389)
        total_w = 21.3 * 487 + 14.9 * 412 + 26.1 * 389
        total_n = 487 + 412 + 389
        expected = total_w / total_n

        with patch("routers.regional.get_conn", get_conn_for(self._conn())):
            data = client.get(f"{BASE}/summary?time_range=trailing_30", headers=AUTH).json()["data"]

        assert abs(data["national_avg_dom"] - round(expected, 1)) < 0.1

    def test_fastest_market_is_tx(self, client):
        with patch("routers.regional.get_conn", get_conn_for(self._conn())):
            fastest = client.get(
                f"{BASE}/summary?time_range=trailing_30", headers=AUTH
            ).json()["data"]["fastest_market"]

        assert fastest["state"] == "TX"
        assert fastest["avg_dom"] == 14.9

    def test_slowest_market_is_ca(self, client):
        with patch("routers.regional.get_conn", get_conn_for(self._conn())):
            slowest = client.get(
                f"{BASE}/summary?time_range=trailing_30", headers=AUTH
            ).json()["data"]["slowest_market"]

        assert slowest["state"] == "CA"

    def test_fastest_pct_vs_national_is_positive(self, client):
        with patch("routers.regional.get_conn", get_conn_for(self._conn())):
            fastest = client.get(
                f"{BASE}/summary?time_range=trailing_30", headers=AUTH
            ).json()["data"]["fastest_market"]

        assert fastest["pct_vs_national"] > 0

    def test_top_growth_state_is_tx(self, client):
        with patch("routers.regional.get_conn", get_conn_for(self._conn())):
            tgs = client.get(
                f"{BASE}/summary?time_range=trailing_30", headers=AUTH
            ).json()["data"]["top_growth_state"]

        assert tgs["state"] == "TX"
        assert abs(tgs["yoy_supply_change_pct"] - 9.1) < 0.1

    def test_sales_trends_rising_falling(self, client):
        # TX=Rising, FL=Stable, CA=Falling → rising=1, falling=1
        with patch("routers.regional.get_conn", get_conn_for(self._conn())):
            st = client.get(
                f"{BASE}/summary?time_range=trailing_30", headers=AUTH
            ).json()["data"]["sales_trends"]

        assert st["states_rising"] == 1
        assert st["states_falling"] == 1

    def test_state_names_resolved(self, client):
        with patch("routers.regional.get_conn", get_conn_for(self._conn())):
            data = client.get(f"{BASE}/summary?time_range=trailing_30", headers=AUTH).json()["data"]

        assert data["fastest_market"]["state_name"] == "Texas"
        assert data["slowest_market"]["state_name"] == "California"

    def test_requires_auth(self, client):
        r = client.get(f"{BASE}/summary?time_range=trailing_30")
        assert r.status_code == 401

    def test_as_of_date_param_accepted(self, client):
        with patch("routers.regional.get_conn", get_conn_for(self._conn())):
            r = client.get(
                f"{BASE}/summary?time_range=trailing_30&as_of_date=2026-04-01", headers=AUTH
            )

        assert r.status_code == 200

    def test_no_data_returns_404(self, client):
        empty_conn = mock_conn(mock_result())
        with patch("routers.regional.get_conn", get_conn_for(empty_conn)):
            r = client.get(f"{BASE}/summary?time_range=trailing_30", headers=AUTH)

        assert r.status_code == 404


# ---------------------------------------------------------------------------
# /state-overview
# ---------------------------------------------------------------------------

class TestRegionalStateOverview:
    def _conn(self):
        return mock_conn(
            mock_result(*STATE_STOCK_ROWS),  # STOCK per state (latest snapshot)
            mock_result(*STATE_FLOW_ROWS),   # fact_estimated_sale per state (boats sold)
        )

    def test_happy_path(self, client):
        with patch("routers.regional.get_conn", get_conn_for(self._conn())):
            r = client.get(f"{BASE}/state-overview?time_range=trailing_30", headers=AUTH)

        assert r.status_code == 200

    def test_national_total_boats_sold(self, client):
        # FL=226 + TX=198 + CA=174 = 598
        with patch("routers.regional.get_conn", get_conn_for(self._conn())):
            data = client.get(
                f"{BASE}/state-overview?time_range=trailing_30", headers=AUTH
            ).json()["data"]

        assert data["national_total_boats_sold"] == 598

    def test_row_count(self, client):
        with patch("routers.regional.get_conn", get_conn_for(self._conn())):
            rows = client.get(
                f"{BASE}/state-overview?time_range=trailing_30", headers=AUTH
            ).json()["data"]["rows"]

        assert len(rows) == 3

    def test_sorted_by_boats_sold_desc(self, client):
        with patch("routers.regional.get_conn", get_conn_for(self._conn())):
            rows = client.get(
                f"{BASE}/state-overview?time_range=trailing_30", headers=AUTH
            ).json()["data"]["rows"]

        sales = [r["boats_sold"] for r in rows]
        assert sales == sorted(sales, reverse=True)

    def test_pct_market_sums_to_100(self, client):
        with patch("routers.regional.get_conn", get_conn_for(self._conn())):
            rows = client.get(
                f"{BASE}/state-overview?time_range=trailing_30", headers=AUTH
            ).json()["data"]["rows"]

        total_pct = sum(r["pct_market"] for r in rows)
        assert abs(total_pct - 100.0) < 0.1

    def test_row_fields_present(self, client):
        with patch("routers.regional.get_conn", get_conn_for(self._conn())):
            row = client.get(
                f"{BASE}/state-overview?time_range=trailing_30", headers=AUTH
            ).json()["data"]["rows"][0]

        for field in ("state", "state_name", "listings", "avg_days_on_market",
                      "dom_velocity_label", "boats_sold", "pct_market", "avg_list_price"):
            assert field in row, f"missing field: {field}"

    def test_dom_velocity_labels_valid(self, client):
        with patch("routers.regional.get_conn", get_conn_for(self._conn())):
            rows = client.get(
                f"{BASE}/state-overview?time_range=trailing_30", headers=AUTH
            ).json()["data"]["rows"]

        valid = {"Fast", "Healthy", "Slow", "Very Slow"}
        for r in rows:
            assert r["dom_velocity_label"] in valid

    def test_fl_is_fast_mover(self, client):
        with patch("routers.regional.get_conn", get_conn_for(self._conn())):
            rows = client.get(
                f"{BASE}/state-overview?time_range=trailing_30", headers=AUTH
            ).json()["data"]["rows"]

        tx = next(r for r in rows if r["state"] == "TX")
        assert tx["dom_velocity_label"] == "Fast"   # 14.9 < 15

    def test_state_names_resolved(self, client):
        with patch("routers.regional.get_conn", get_conn_for(self._conn())):
            rows = client.get(
                f"{BASE}/state-overview?time_range=trailing_30", headers=AUTH
            ).json()["data"]["rows"]

        name_map = {r["state"]: r["state_name"] for r in rows}
        assert name_map["FL"] == "Florida"
        assert name_map["TX"] == "Texas"
        assert name_map["CA"] == "California"

    def test_no_data_returns_404(self, client):
        empty_conn = mock_conn(mock_result())
        with patch("routers.regional.get_conn", get_conn_for(empty_conn)):
            r = client.get(f"{BASE}/state-overview?time_range=trailing_30", headers=AUTH)

        assert r.status_code == 404


# ---------------------------------------------------------------------------
# /market-leaders
# ---------------------------------------------------------------------------

class TestRegionalMarketLeaders:
    def _conn(self):
        return mock_conn(
            mock_result(*LEADER_FLOW_ROWS),    # fact_estimated_sale per state
            mock_result(*LEADER_LISTING_ROWS), # active listings per state
        )

    def test_happy_path(self, client):
        with patch("routers.regional.get_conn", get_conn_for(self._conn())):
            r = client.get(f"{BASE}/market-leaders?time_range=trailing_30&top_n=3", headers=AUTH)

        assert r.status_code == 200

    def test_top_states_count(self, client):
        with patch("routers.regional.get_conn", get_conn_for(self._conn())):
            data = client.get(
                f"{BASE}/market-leaders?time_range=trailing_30&top_n=3", headers=AUTH
            ).json()["data"]

        assert len(data["top_states"]) == 3

    def test_bottom_states_count(self, client):
        with patch("routers.regional.get_conn", get_conn_for(self._conn())):
            data = client.get(
                f"{BASE}/market-leaders?time_range=trailing_30&top_n=3", headers=AUTH
            ).json()["data"]

        assert len(data["bottom_states"]) == 3

    def test_top_states_ordered_by_sales_desc(self, client):
        with patch("routers.regional.get_conn", get_conn_for(self._conn())):
            top = client.get(
                f"{BASE}/market-leaders?time_range=trailing_30&top_n=3", headers=AUTH
            ).json()["data"]["top_states"]

        sales = [r["boats_sold"] for r in top]
        assert sales == sorted(sales, reverse=True)

    def test_top_state_is_fl(self, client):
        with patch("routers.regional.get_conn", get_conn_for(self._conn())):
            top = client.get(
                f"{BASE}/market-leaders?time_range=trailing_30&top_n=3", headers=AUTH
            ).json()["data"]["top_states"]

        assert top[0]["state"] == "FL"
        assert top[0]["boats_sold"] == 226

    def test_bottom_state_is_ak(self, client):
        with patch("routers.regional.get_conn", get_conn_for(self._conn())):
            bottom = client.get(
                f"{BASE}/market-leaders?time_range=trailing_30&top_n=3", headers=AUTH
            ).json()["data"]["bottom_states"]

        assert bottom[0]["state"] == "AK"
        assert bottom[0]["boats_sold"] == 2

    def test_row_fields_present(self, client):
        with patch("routers.regional.get_conn", get_conn_for(self._conn())):
            row = client.get(
                f"{BASE}/market-leaders?time_range=trailing_30&top_n=3", headers=AUTH
            ).json()["data"]["top_states"][0]

        for field in ("rank", "state", "state_name", "boats_sold", "listings"):
            assert field in row, f"missing field: {field}"

    def test_state_names_resolved(self, client):
        with patch("routers.regional.get_conn", get_conn_for(self._conn())):
            top = client.get(
                f"{BASE}/market-leaders?time_range=trailing_30&top_n=3", headers=AUTH
            ).json()["data"]["top_states"]

        name_map = {r["state"]: r["state_name"] for r in top}
        assert name_map["FL"] == "Florida"
        assert name_map["TX"] == "Texas"

    def test_default_top_n_is_5(self, client):
        with patch("routers.regional.get_conn", get_conn_for(self._conn())):
            data = client.get(
                f"{BASE}/market-leaders?time_range=trailing_30", headers=AUTH
            ).json()["data"]

        # 6 states in mock data, default top_n=5 → top 5
        assert len(data["top_states"]) == 5

    def test_top_n_respected(self, client):
        with patch("routers.regional.get_conn", get_conn_for(self._conn())):
            data = client.get(
                f"{BASE}/market-leaders?time_range=trailing_30&top_n=2", headers=AUTH
            ).json()["data"]

        assert len(data["top_states"]) == 2
        assert len(data["bottom_states"]) == 2

    def test_no_overlap_between_top_and_bottom(self, client):
        with patch("routers.regional.get_conn", get_conn_for(self._conn())):
            data = client.get(
                f"{BASE}/market-leaders?time_range=trailing_30&top_n=3", headers=AUTH
            ).json()["data"]

        top_codes = {r["state"] for r in data["top_states"]}
        bottom_codes = {r["state"] for r in data["bottom_states"]}
        assert top_codes.isdisjoint(bottom_codes), "top and bottom states must not overlap"

    def test_no_data_returns_404(self, client):
        empty_conn = mock_conn(mock_result())
        with patch("routers.regional.get_conn", get_conn_for(empty_conn)):
            r = client.get(f"{BASE}/market-leaders?time_range=trailing_30", headers=AUTH)

        assert r.status_code == 404

    def test_as_of_date_param_accepted(self, client):
        with patch("routers.regional.get_conn", get_conn_for(self._conn())):
            r = client.get(
                f"{BASE}/market-leaders?time_range=trailing_30&as_of_date=2026-04-01", headers=AUTH
            )

        assert r.status_code == 200
