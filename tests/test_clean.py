import pandas as pd
import pytest

from ecom_dw import clean
from ecom_dw.schemas import SILVER_COLUMNS
from tests.helpers import raw_batch1


@pytest.fixture(scope="module")
def result():
    return clean.run_clean(raw_batch1())


def test_silver_columns_match_schema(result):
    c, _ = result
    for t, df in c.items():
        assert list(df.columns) == SILVER_COLUMNS[t]


def test_orders_rejects_duplicate_invalid_status_and_bad_date(result):
    c, r = result
    assert sorted(c["orders"]["order_id"]) == ["o1", "o2", "o3"]
    reasons = sorted(r["orders"]["_reject_reason"])
    assert reasons == ["duplicate_key", "invalid_order_status", "invalid_purchase_ts"]
    assert pd.api.types.is_datetime64_any_dtype(c["orders"]["purchase_ts"])


def test_customers_standardised_and_deduped(result):
    c, r = result
    cu = c["customers"].set_index("customer_id")
    assert len(cu) == 2 and len(r["customers"]) == 1
    assert cu.loc["c1", "zip_code_prefix"] == "01046"      # leading zero restored
    assert cu.loc["c1", "city"] == "sao paulo" and cu.loc["c1", "state"] == "SP"


def test_items_orphan_and_negative_price_rejected(result):
    c, r = result
    assert len(c["order_items"]) == 4
    assert set(r["order_items"]["_reject_reason"]) == {"invalid_amount", "orphan_order_id"}


def test_reviews_dedup_keeps_latest_and_validates_score(result):
    c, r = result
    assert len(c["reviews"]) == 1 and c["reviews"].iloc[0]["review_score"] == 4
    assert set(r["reviews"]["_reject_reason"]) == {"duplicate_key", "invalid_review_score"}


def test_products_translation_fallback_and_negative_nullified(result):
    p = result[0]["products"].set_index("product_id")
    assert p.loc["p1", "category_name_en"] == "health_beauty"
    assert p.loc["p2", "category_name_en"] == "unknown"
    assert pd.isna(p.loc["p2", "weight_g"])


def test_geolocation_aggregated_and_bbox_filtered(result):
    c, r = result
    g = c["geolocation"]
    assert len(g) == 1 and g.iloc[0]["zip_code_prefix"] == "01046"
    assert g.iloc[0]["lat"] == pytest.approx(-23.56)
    assert list(r["geolocation"]["_reject_reason"]) == ["coordinates_outside_brazil"]


def test_clean_fx_parses_api_payload():
    payload = {"base": "USD", "rates": {"2017-01-02": {"BRL": 3.2}, "2017-01-03": {"BRL": 3.25}}}
    df, _ = clean.clean_fx(payload)
    assert list(df.columns) == SILVER_COLUMNS["fx_rates"] and len(df) == 2
