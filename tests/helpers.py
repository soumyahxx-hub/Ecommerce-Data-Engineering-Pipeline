"""SYNTHETIC test data in the Olist column format (NOT real Olist records). Used by unit + integration tests."""
import pandas as pd


def _df(rows, cols):
    return pd.DataFrame(rows, columns=cols, dtype=str)


def raw_batch1() -> dict[str, pd.DataFrame]:
    return {
        "customers": _df([
            ["c1", "u1", "1046", "Sao Paulo ", "sp"],
            ["c2", "u2", "20040", "rio de janeiro", "RJ"],
            ["c2", "u2", "20040", "rio de janeiro", "RJ"],          # duplicate key
        ], ["customer_id", "customer_unique_id", "customer_zip_code_prefix", "customer_city", "customer_state"]),
        "sellers": _df([["s1", "13023", "campinas", "sp"]],
                       ["seller_id", "seller_zip_code_prefix", "seller_city", "seller_state"]),
        "products": _df([
            ["p1", "beleza_saude", "40", "287", "1", "225", "16", "10", "14"],
            ["p2", None, None, None, None, "-5", None, None, None],     # no category, negative weight
        ], ["product_id", "product_category_name", "product_name_lenght", "product_description_lenght",
            "product_photos_qty", "product_weight_g", "product_length_cm", "product_height_cm", "product_width_cm"]),
        "category_translation": _df([["beleza_saude", "health_beauty"]],
                                    ["product_category_name", "product_category_name_english"]),
        "orders": _df([
            ["o1", "c1", "delivered", "2017-01-05 10:00:00", None, None, None, None],          # stale duplicate (last record wins)
            ["o1", "c1", "delivered", "2017-01-05 10:00:00", "2017-01-05 11:00:00", "2017-01-06 10:00:00", "2017-01-12 10:00:00", "2017-01-20 00:00:00"],
            ["o2", "c2", "shipped", "2017-01-06 09:00:00", "2017-01-06 10:00:00", "2017-01-07 10:00:00", None, "2017-01-25 00:00:00"],
            ["o3", "c_missing", "delivered", "2017-01-07 09:00:00", "2017-01-07 10:00:00", "2017-01-08 10:00:00", "2017-01-30 10:00:00", "2017-01-20 00:00:00"],
            ["o_bad", "c1", "weird_status", "2017-01-08 09:00:00", None, None, None, None],    # invalid status
            ["o_nodate", "c1", "created", "not-a-date", None, None, None, None],               # invalid timestamp
        ], ["order_id", "customer_id", "order_status", "order_purchase_timestamp", "order_approved_at",
            "order_delivered_carrier_date", "order_delivered_customer_date", "order_estimated_delivery_date"]),
        "order_items": _df([
            ["o1", "1", "p1", "s1", "2017-01-10 00:00:00", "100.00", "10.00"],
            ["o1", "2", "p1", "s1", "2017-01-10 00:00:00", "50.50", "5.25"],
            ["o2", "1", "p1", "s1", "2017-01-11 00:00:00", "20.00", "7.00"],
            ["o3", "1", "p_missing", "s_missing", "2017-01-11 00:00:00", "30.00", "3.00"],
            ["o_orphan", "1", "p1", "s1", "2017-01-11 00:00:00", "9.00", "1.00"],              # orphan order
            ["o2", "2", "p1", "s1", "2017-01-11 00:00:00", "-1", "1.00"],                       # negative price
        ], ["order_id", "order_item_id", "product_id", "seller_id", "shipping_limit_date", "price", "freight_value"]),
        "payments": _df([
            ["o1", "1", "credit_card", "3", "100.00"],
            ["o1", "2", "voucher", "1", "65.75"],
            ["o2", "1", "boleto", "1", "27.00"],
            ["o3", "1", "credit_card", "1", "33.00"],
        ], ["order_id", "payment_sequential", "payment_type", "payment_installments", "payment_value"]),
        "reviews": _df([
            ["r1", "o1", "5", "great", "loved it", "2017-01-13 00:00:00", "2017-01-14 00:00:00"],
            ["r1", "o1", "4", None, None, "2017-01-13 00:00:00", "2017-01-15 00:00:00"],       # duplicate -> keep latest
            ["r2", "o2", "9", None, None, "2017-01-13 00:00:00", "2017-01-14 00:00:00"],       # invalid score
        ], ["review_id", "order_id", "review_score", "review_comment_title", "review_comment_message",
            "review_creation_date", "review_answer_timestamp"]),
        "geolocation": _df([
            ["1046", "-23.55", "-46.63", "sao paulo", "SP"],
            ["1046", "-23.57", "-46.65", "sao paulo", "SP"],
            ["1046", "40.0", "10.0", "nowhere", "XX"],                                          # outside Brazil
        ], ["geolocation_zip_code_prefix", "geolocation_lat", "geolocation_lng", "geolocation_city", "geolocation_state"]),
    }


def raw_batch2() -> dict[str, pd.DataFrame]:
    """Later batch: u1 moved city (new customer_id c3), product p1 changed weight, o2 progressed to delivered."""
    b = raw_batch1()
    return {
        "customers": _df([["c2", "u2", "20040", "rio de janeiro", "RJ"], ["c3", "u1", "22000", "rio de janeiro", "RJ"]],
                         list(b["customers"].columns)),
        "sellers": b["sellers"],
        "products": _df([["p1", "beleza_saude", "40", "287", "1", "300", "16", "10", "14"]], list(b["products"].columns)),
        "category_translation": b["category_translation"],
        "orders": _df([
            ["o2", "c2", "delivered", "2017-01-06 09:00:00", "2017-01-06 10:00:00", "2017-01-07 10:00:00", "2017-01-24 10:00:00", "2017-01-25 00:00:00"],
            ["o4", "c3", "delivered", "2017-03-01 09:00:00", "2017-03-01 10:00:00", "2017-03-02 10:00:00", "2017-03-09 10:00:00", "2017-03-20 00:00:00"],
        ], list(b["orders"].columns)),
        "order_items": _df([
            ["o2", "1", "p1", "s1", "2017-01-11 00:00:00", "20.00", "7.00"],
            ["o4", "1", "p1", "s1", "2017-03-03 00:00:00", "80.00", "8.00"],
        ], list(b["order_items"].columns)),
        "payments": _df([["o2", "1", "boleto", "1", "27.00"], ["o4", "1", "credit_card", "2", "88.00"]],
                        list(b["payments"].columns)),
        "reviews": _df([["r4", "o4", "3", None, None, "2017-03-10 00:00:00", "2017-03-11 00:00:00"]],
                       list(b["reviews"].columns)),
        "geolocation": b["geolocation"],
    }
