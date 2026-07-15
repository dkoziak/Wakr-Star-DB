"""
Pagination tests for endpoints that support limit/offset:
  - GET /api/v1/pricing/model-efficiency
  - GET /api/v1/regional/state-overview

Each class covers:
  - Pagination envelope fields present (total_records, limit, offset)
  - Default values echoed (limit=50, offset=0)
  - limit restricts the returned rows
  - offset skips rows
  - limit + offset combined pages correctly
  - total_records is always the full dataset size, unaffected by pagination
  - offset beyond total_records returns empty rows with 200 OK (valid empty page)
  - Invalid limit (0, >500) and negative offset return 400

Endpoint-specific extras:
  - Model efficiency: rank is global (assigned before slicing, stable across pages)
  - State overview: national_total_boats_sold is unaffected by pagination
"""

from unittest.mock import patch

from tests.conftest import AUTH, get_conn_for, mock_conn, mock_result
from tests.mock_data import (
    MODEL_EFF_ROWS_MANY,
    STATE_FLOW_MANY,
    STATE_STOCK_MANY,
)

PRICE_BASE = "/api/v1/pricing"
REG_BASE = "/api/v1/regional"

# ---------------------------------------------------------------------------
# /pricing/model-efficiency
# ---------------------------------------------------------------------------

class TestModelEfficiencyPagination:
    """
    Mock DB returns 5 rows; after sort by avg_dom asc:
      rank1 Ri235 12.4  rank2 Ri245 21.7  rank3 SL450 31.2
      rank4 230Surf 43.8  rank5 G23 58.1
    """

    def _conn(self):
        return mock_conn(mock_result(*MODEL_EFF_ROWS_MANY))

    def _get(self, client, qs=""):
        with patch("routers.pricing.get_conn", get_conn_for(self._conn())):
            return client.get(
                f"{PRICE_BASE}/model-efficiency?time_range=trailing_30{qs}", headers=AUTH
            )

    def test_pagination_fields_present(self, client):
        data = self._get(client).json()["data"]
        assert "total_records" in data
        assert "limit" in data
        assert "offset" in data

    def test_default_limit_and_offset_echoed(self, client):
        data = self._get(client).json()["data"]
        assert data["limit"] == 50
        assert data["offset"] == 0

    def test_default_returns_all_rows_when_under_limit(self, client):
        data = self._get(client).json()["data"]
        assert len(data["rows"]) == 5

    def test_custom_limit_restricts_rows(self, client):
        data = self._get(client, "&limit=2").json()["data"]
        assert len(data["rows"]) == 2
        assert data["limit"] == 2

    def test_custom_offset_skips_rows(self, client):
        data = self._get(client, "&offset=2").json()["data"]
        assert len(data["rows"]) == 3
        # First returned row is the 3rd in sort order (SL450, dom=31.2)
        assert data["rows"][0]["model"] == "SL450"

    def test_limit_and_offset_combined(self, client):
        data = self._get(client, "&limit=2&offset=2").json()["data"]
        assert len(data["rows"]) == 2
        assert data["rows"][0]["model"] == "SL450"
        assert data["rows"][1]["model"] == "230 Surf"

    def test_total_records_unaffected_by_limit(self, client):
        data = self._get(client, "&limit=1").json()["data"]
        assert data["total_records"] == 5

    def test_total_records_unaffected_by_offset(self, client):
        data = self._get(client, "&offset=3").json()["data"]
        assert data["total_records"] == 5

    def test_offset_beyond_total_returns_empty_page(self, client):
        r = self._get(client, "&offset=100")
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["rows"] == []
        assert data["total_records"] == 5

    def test_rank_is_global_not_per_page(self, client):
        # At offset=2 the first row should carry rank=3, not rank=1
        data = self._get(client, "&limit=2&offset=2").json()["data"]
        assert data["rows"][0]["rank"] == 3
        assert data["rows"][1]["rank"] == 4

    def test_rank_starts_at_1_on_first_page(self, client):
        data = self._get(client, "&limit=2").json()["data"]
        assert data["rows"][0]["rank"] == 1
        assert data["rows"][1]["rank"] == 2

    def test_limit_zero_returns_400(self, client):
        r = self._get(client, "&limit=0")
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "INVALID_PARAM"

    def test_limit_over_max_returns_400(self, client):
        r = self._get(client, "&limit=501")
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "INVALID_PARAM"

    def test_negative_offset_returns_400(self, client):
        r = self._get(client, "&offset=-1")
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "INVALID_PARAM"

    def test_limit_text_value_returns_400(self, client):
        r = self._get(client, "&limit=abc")
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "INVALID_PARAM"

    def test_offset_text_value_returns_400(self, client):
        r = self._get(client, "&offset=abc")
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "INVALID_PARAM"

    def test_limit_float_value_returns_400(self, client):
        r = self._get(client, "&limit=1.5")
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "INVALID_PARAM"

    def test_no_db_rows_returns_404_with_pagination_params(self, client):
        empty_conn = mock_conn(mock_result())
        with patch("routers.pricing.get_conn", get_conn_for(empty_conn)):
            r = client.get(
                f"{PRICE_BASE}/model-efficiency?time_range=trailing_30&limit=2&offset=0",
                headers=AUTH,
            )
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "NO_DATA"

    def test_as_of_date_combined_with_pagination(self, client):
        data = self._get(client, "&as_of_date=2026-04-01&limit=2").json()["data"]
        assert len(data["rows"]) == 2
        assert data["limit"] == 2
        assert data["total_records"] == 5

    def test_inventory_type_filter_combined_with_pagination(self, client):
        data = self._get(client, "&inventory_type=used&limit=2").json()["data"]
        assert len(data["rows"]) == 2
        assert data["limit"] == 2
        assert "total_records" in data

    def test_make_all_combined_with_pagination(self, client):
        data = self._get(client, "&make=all&limit=2").json()["data"]
        assert len(data["rows"]) == 2
        assert "total_records" in data


# ---------------------------------------------------------------------------
# /regional/state-overview
# ---------------------------------------------------------------------------

class TestStateOverviewPagination:
    """
    Mock DB returns 5 states; after sort by boats_sold desc:
      [0] FL 226  [1] TX 198  [2] CA 174  [3] WA 95  [4] TN 67
      national_total_boats_sold = 760
    """

    NATIONAL_TOTAL = 760  # 226 + 198 + 174 + 95 + 67

    def _conn(self):
        return mock_conn(
            mock_result(*STATE_STOCK_MANY),
            mock_result(*STATE_FLOW_MANY),
        )

    def _get(self, client, qs=""):
        with patch("routers.regional.get_conn", get_conn_for(self._conn())):
            return client.get(
                f"{REG_BASE}/state-overview?time_range=trailing_30{qs}", headers=AUTH
            )

    def test_pagination_fields_present(self, client):
        data = self._get(client).json()["data"]
        assert "total_records" in data
        assert "limit" in data
        assert "offset" in data

    def test_default_limit_and_offset_echoed(self, client):
        data = self._get(client).json()["data"]
        assert data["limit"] == 50
        assert data["offset"] == 0

    def test_default_returns_all_rows_when_under_limit(self, client):
        data = self._get(client).json()["data"]
        assert len(data["rows"]) == 5

    def test_custom_limit_restricts_rows(self, client):
        data = self._get(client, "&limit=2").json()["data"]
        assert len(data["rows"]) == 2
        assert data["limit"] == 2

    def test_custom_offset_skips_rows(self, client):
        data = self._get(client, "&offset=2").json()["data"]
        assert len(data["rows"]) == 3
        # First returned row is the 3rd in sort order (CA, boats_sold=174)
        assert data["rows"][0]["state"] == "CA"

    def test_limit_and_offset_combined(self, client):
        data = self._get(client, "&limit=2&offset=2").json()["data"]
        assert len(data["rows"]) == 2
        assert data["rows"][0]["state"] == "CA"
        assert data["rows"][1]["state"] == "WA"

    def test_total_records_unaffected_by_limit(self, client):
        data = self._get(client, "&limit=1").json()["data"]
        assert data["total_records"] == 5

    def test_total_records_unaffected_by_offset(self, client):
        data = self._get(client, "&offset=3").json()["data"]
        assert data["total_records"] == 5

    def test_offset_beyond_total_returns_empty_page(self, client):
        r = self._get(client, "&offset=100")
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["rows"] == []
        assert data["total_records"] == 5
        assert data["national_total_boats_sold"] == self.NATIONAL_TOTAL

    def test_national_total_unaffected_by_limit(self, client):
        # national_total_boats_sold is computed across all states before pagination
        data = self._get(client, "&limit=2").json()["data"]
        assert data["national_total_boats_sold"] == self.NATIONAL_TOTAL

    def test_national_total_unaffected_by_offset(self, client):
        data = self._get(client, "&offset=3").json()["data"]
        assert data["national_total_boats_sold"] == self.NATIONAL_TOTAL

    def test_pct_market_relative_to_national_total_not_page(self, client):
        # FL on page 1 should have pct = 226/760 * 100 ≈ 29.74, not 226/sum_of_page * 100
        data = self._get(client, "&limit=2").json()["data"]
        fl = next(r for r in data["rows"] if r["state"] == "FL")
        expected = round(226 / self.NATIONAL_TOTAL * 100, 2)
        assert abs(fl["pct_market"] - expected) < 0.1

    def test_limit_zero_returns_400(self, client):
        r = self._get(client, "&limit=0")
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "INVALID_PARAM"

    def test_limit_over_max_returns_400(self, client):
        r = self._get(client, "&limit=501")
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "INVALID_PARAM"

    def test_negative_offset_returns_400(self, client):
        r = self._get(client, "&offset=-1")
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "INVALID_PARAM"

    def test_limit_text_value_returns_400(self, client):
        r = self._get(client, "&limit=abc")
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "INVALID_PARAM"

    def test_offset_text_value_returns_400(self, client):
        r = self._get(client, "&offset=abc")
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "INVALID_PARAM"

    def test_limit_float_value_returns_400(self, client):
        r = self._get(client, "&limit=1.5")
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "INVALID_PARAM"

    def test_no_db_rows_returns_404_with_pagination_params(self, client):
        empty_conn = mock_conn(mock_result())
        with patch("routers.regional.get_conn", get_conn_for(empty_conn)):
            r = client.get(
                f"{REG_BASE}/state-overview?time_range=trailing_30&limit=2&offset=0",
                headers=AUTH,
            )
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "NO_DATA"

    def test_as_of_date_combined_with_pagination(self, client):
        data = self._get(client, "&as_of_date=2026-04-01&limit=2").json()["data"]
        assert len(data["rows"]) == 2
        assert data["limit"] == 2
        assert data["total_records"] == 5

    def test_inventory_type_filter_combined_with_pagination(self, client):
        data = self._get(client, "&inventory_type=new&limit=2&offset=1").json()["data"]
        assert len(data["rows"]) == 2
        assert data["offset"] == 1
        assert "total_records" in data

    def test_make_all_combined_with_pagination(self, client):
        data = self._get(client, "&make=all&limit=2").json()["data"]
        assert len(data["rows"]) == 2
        assert "total_records" in data
