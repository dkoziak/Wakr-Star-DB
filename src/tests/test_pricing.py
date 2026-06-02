from unittest.mock import patch

import pytest

from tests.conftest import AUTH, get_conn_for, mock_conn, mock_result
from tests.mock_data import (
    DOM_BY_BAND,
    LISTINGS_BY_BAND,
    MODEL_EFF_ROWS,
    MPT_ROW,
    PRICE_STOCK,
)

BASE = "/api/v1/pricing"


# ---------------------------------------------------------------------------
# /summary
# ---------------------------------------------------------------------------

class TestPricingSummary:
    def _conn(self):
        return mock_conn(
            mock_result(PRICE_STOCK),  # STOCK query (avg/median price)
            mock_result(MPT_ROW),      # mart_pricing_trends (MoM + top band)
        )

    def test_happy_path(self, client):
        with patch("routers.pricing.get_conn", get_conn_for(self._conn())):
            r = client.get(f"{BASE}/summary?time_range=trailing_30", headers=AUTH)

        assert r.status_code == 200

    def test_avg_and_median_price(self, client):
        with patch("routers.pricing.get_conn", get_conn_for(self._conn())):
            data = client.get(f"{BASE}/summary?time_range=trailing_30", headers=AUTH).json()["data"]

        assert data["avg_list_price"] == 142500.0
        assert data["median_list_price"] == 136000.0

    def test_mom_price_change_pct(self, client):
        # MPT_ROW.mom_price_change_pct = -0.041 → API multiplies by 100 → -4.1
        with patch("routers.pricing.get_conn", get_conn_for(self._conn())):
            data = client.get(f"{BASE}/summary?time_range=trailing_30", headers=AUTH).json()["data"]

        assert abs(data["mom_price_change_pct"] - (-4.1)) < 0.01

    def test_top_selling_band_present(self, client):
        with patch("routers.pricing.get_conn", get_conn_for(self._conn())):
            tsb = client.get(f"{BASE}/summary?time_range=trailing_30", headers=AUTH).json()["data"]["top_selling_band"]

        assert "band" in tsb
        assert "band_label" in tsb
        assert tsb["units_sold"] == 134

    def test_top_selling_band_over_140k(self, client):
        # MPT_ROW has top_selling_band_low=140000, high=None → over_140k
        with patch("routers.pricing.get_conn", get_conn_for(self._conn())):
            tsb = client.get(f"{BASE}/summary?time_range=trailing_30", headers=AUTH).json()["data"]["top_selling_band"]

        assert tsb["band"] == "over_140k"
        assert tsb["band_label"] == "Over $140k"

    def test_requires_auth(self, client):
        r = client.get(f"{BASE}/summary?time_range=trailing_30")
        assert r.status_code == 401

    def test_insufficient_data_when_no_mpt_rows(self, client):
        conn = mock_conn(
            mock_result(PRICE_STOCK),
            mock_result(),             # no MPT rows → 422
        )
        with patch("routers.pricing.get_conn", get_conn_for(conn)):
            r = client.get(f"{BASE}/summary?time_range=trailing_30", headers=AUTH)

        assert r.status_code == 422
        assert r.json()["error"]["code"] == "INSUFFICIENT_DATA"

    def test_response_envelope_fields(self, client):
        with patch("routers.pricing.get_conn", get_conn_for(self._conn())):
            body = client.get(f"{BASE}/summary?time_range=trailing_30", headers=AUTH).json()

        for field in ("data", "data_as_of", "generated_at", "filters_applied"):
            assert field in body

    def test_data_as_of_is_iso_datetime(self, client):
        with patch("routers.pricing.get_conn", get_conn_for(self._conn())):
            body = client.get(f"{BASE}/summary?time_range=trailing_30", headers=AUTH).json()

        assert "T" in body["data_as_of"]
        assert body["data_as_of"].endswith("Z")

    def test_as_of_date_param_accepted(self, client):
        with patch("routers.pricing.get_conn", get_conn_for(self._conn())):
            r = client.get(
                f"{BASE}/summary?time_range=trailing_30&as_of_date=2026-04-01", headers=AUTH
            )

        assert r.status_code == 200

    def test_missing_time_range_returns_400(self, client):
        r = client.get(f"{BASE}/summary", headers=AUTH)
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "MISSING_PARAM"


# ---------------------------------------------------------------------------
# /dom-by-price-tier
# ---------------------------------------------------------------------------

class TestDomByPriceTier:
    def _conn(self):
        return mock_conn(mock_result(DOM_BY_BAND))

    def test_happy_path(self, client):
        with patch("routers.pricing.get_conn", get_conn_for(self._conn())):
            r = client.get(f"{BASE}/dom-by-price-tier?time_range=trailing_30", headers=AUTH)

        assert r.status_code == 200

    def test_always_six_bands(self, client):
        with patch("routers.pricing.get_conn", get_conn_for(self._conn())):
            bands = client.get(
                f"{BASE}/dom-by-price-tier?time_range=trailing_30", headers=AUTH
            ).json()["data"]["bands"]

        assert len(bands) == 6

    def test_band_keys_present(self, client):
        with patch("routers.pricing.get_conn", get_conn_for(self._conn())):
            band = client.get(
                f"{BASE}/dom-by-price-tier?time_range=trailing_30", headers=AUTH
            ).json()["data"]["bands"][0]

        for key in ("band", "band_label", "avg_days_on_market", "velocity_label"):
            assert key in band

    def test_band_order(self, client):
        with patch("routers.pricing.get_conn", get_conn_for(self._conn())):
            bands = client.get(
                f"{BASE}/dom-by-price-tier?time_range=trailing_30", headers=AUTH
            ).json()["data"]["bands"]

        expected_bands = ["under_60k", "60k_80k", "80k_100k", "100k_120k", "120k_140k", "over_140k"]
        assert [b["band"] for b in bands] == expected_bands

    def test_zero_listings_band_returns_zero_dom(self, client):
        # under_60k has cnt=0 → avg_dom should be 0.0
        with patch("routers.pricing.get_conn", get_conn_for(self._conn())):
            bands = client.get(
                f"{BASE}/dom-by-price-tier?time_range=trailing_30", headers=AUTH
            ).json()["data"]["bands"]

        under_60k = next(b for b in bands if b["band"] == "under_60k")
        assert under_60k["avg_days_on_market"] == 0.0

    def test_velocity_label_populated(self, client):
        with patch("routers.pricing.get_conn", get_conn_for(self._conn())):
            bands = client.get(
                f"{BASE}/dom-by-price-tier?time_range=trailing_30", headers=AUTH
            ).json()["data"]["bands"]

        valid_labels = {"Fast", "Healthy", "Slow", "Very Slow"}
        for b in bands:
            assert b["velocity_label"] in valid_labels

    def test_weighted_dom_calculation(self, client):
        # 80_100k: dom_w=13682, cnt=618 → 13682/618 ≈ 22.1
        with patch("routers.pricing.get_conn", get_conn_for(self._conn())):
            bands = client.get(
                f"{BASE}/dom-by-price-tier?time_range=trailing_30", headers=AUTH
            ).json()["data"]["bands"]

        b80 = next(b for b in bands if b["band"] == "80k_100k")
        assert abs(b80["avg_days_on_market"] - 22.1) < 0.2


# ---------------------------------------------------------------------------
# /listings-by-price-tier
# ---------------------------------------------------------------------------

class TestListingsByPriceTier:
    def _conn(self):
        return mock_conn(mock_result(LISTINGS_BY_BAND))

    def test_happy_path(self, client):
        with patch("routers.pricing.get_conn", get_conn_for(self._conn())):
            r = client.get(f"{BASE}/listings-by-price-tier?time_range=trailing_30", headers=AUTH)

        assert r.status_code == 200

    def test_always_six_bands(self, client):
        with patch("routers.pricing.get_conn", get_conn_for(self._conn())):
            bands = client.get(
                f"{BASE}/listings-by-price-tier?time_range=trailing_30", headers=AUTH
            ).json()["data"]["bands"]

        assert len(bands) == 6

    def test_listing_counts(self, client):
        with patch("routers.pricing.get_conn", get_conn_for(self._conn())):
            bands = client.get(
                f"{BASE}/listings-by-price-tier?time_range=trailing_30", headers=AUTH
            ).json()["data"]["bands"]

        counts = {b["band"]: b["listings"] for b in bands}
        assert counts["under_60k"] == 12
        assert counts["80k_100k"] == 618
        assert counts["100k_120k"] == 891

    def test_band_labels_populated(self, client):
        with patch("routers.pricing.get_conn", get_conn_for(self._conn())):
            bands = client.get(
                f"{BASE}/listings-by-price-tier?time_range=trailing_30", headers=AUTH
            ).json()["data"]["bands"]

        for b in bands:
            assert b["band_label"] != ""


# ---------------------------------------------------------------------------
# /model-efficiency
# ---------------------------------------------------------------------------

class TestModelEfficiency:
    def _conn(self):
        return mock_conn(mock_result(*MODEL_EFF_ROWS))

    def test_happy_path(self, client):
        with patch("routers.pricing.get_conn", get_conn_for(self._conn())):
            r = client.get(f"{BASE}/model-efficiency?time_range=trailing_30", headers=AUTH)

        assert r.status_code == 200

    def test_row_count(self, client):
        with patch("routers.pricing.get_conn", get_conn_for(self._conn())):
            rows = client.get(
                f"{BASE}/model-efficiency?time_range=trailing_30", headers=AUTH
            ).json()["data"]["rows"]

        assert len(rows) == 2

    def test_ranked_by_dom_ascending(self, client):
        with patch("routers.pricing.get_conn", get_conn_for(self._conn())):
            rows = client.get(
                f"{BASE}/model-efficiency?time_range=trailing_30", headers=AUTH
            ).json()["data"]["rows"]

        # Ri235 (12.4 DOM) should be rank 1, Ri245 (21.7 DOM) rank 2
        assert rows[0]["rank"] == 1
        assert rows[1]["rank"] == 2
        assert rows[0]["avg_days_on_market"] < rows[1]["avg_days_on_market"]

    def test_row_fields_present(self, client):
        with patch("routers.pricing.get_conn", get_conn_for(self._conn())):
            row = client.get(
                f"{BASE}/model-efficiency?time_range=trailing_30", headers=AUTH
            ).json()["data"]["rows"][0]

        for field in ("rank", "model_year", "manufacturer", "model", "year",
                      "avg_list_price", "price_band_low", "price_band_high",
                      "price_band_label", "avg_days_on_market", "dom_velocity_label", "listings"):
            assert field in row, f"missing field: {field}"

    def test_price_band_label_formatted(self, client):
        with patch("routers.pricing.get_conn", get_conn_for(self._conn())):
            row = client.get(
                f"{BASE}/model-efficiency?time_range=trailing_30", headers=AUTH
            ).json()["data"]["rows"][0]

        # price_band_low=68000, high=91000 → "$68k–$91k"
        assert row["price_band_label"] == "$68k–$91k"

    def test_no_data_returns_404(self, client):
        empty_conn = mock_conn(mock_result())
        with patch("routers.pricing.get_conn", get_conn_for(empty_conn)):
            r = client.get(f"{BASE}/model-efficiency?time_range=trailing_30", headers=AUTH)

        assert r.status_code == 404
