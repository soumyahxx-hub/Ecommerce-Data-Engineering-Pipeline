"""Source and silver schemas. Source columns follow the published Olist Kaggle dataset
(including its original spelling 'lenght'); validate_schema() fails loudly if they differ."""
from __future__ import annotations

SOURCE_FILES: dict[str, tuple[str, list[str]]] = {
    "customers": ("olist_customers_dataset.csv",
                  ["customer_id", "customer_unique_id", "customer_zip_code_prefix", "customer_city", "customer_state"]),
    "geolocation": ("olist_geolocation_dataset.csv",
                    ["geolocation_zip_code_prefix", "geolocation_lat", "geolocation_lng",
                     "geolocation_city", "geolocation_state"]),
    "order_items": ("olist_order_items_dataset.csv",
                    ["order_id", "order_item_id", "product_id", "seller_id", "shipping_limit_date",
                     "price", "freight_value"]),
    "payments": ("olist_order_payments_dataset.csv",
                 ["order_id", "payment_sequential", "payment_type", "payment_installments", "payment_value"]),
    "reviews": ("olist_order_reviews_dataset.csv",
                ["review_id", "order_id", "review_score", "review_comment_title", "review_comment_message",
                 "review_creation_date", "review_answer_timestamp"]),
    "orders": ("olist_orders_dataset.csv",
               ["order_id", "customer_id", "order_status", "order_purchase_timestamp", "order_approved_at",
                "order_delivered_carrier_date", "order_delivered_customer_date", "order_estimated_delivery_date"]),
    "products": ("olist_products_dataset.csv",
                 ["product_id", "product_category_name", "product_name_lenght", "product_description_lenght",
                  "product_photos_qty", "product_weight_g", "product_length_cm", "product_height_cm",
                  "product_width_cm"]),
    "sellers": ("olist_sellers_dataset.csv",
                ["seller_id", "seller_zip_code_prefix", "seller_city", "seller_state"]),
    "category_translation": ("product_category_name_translation.csv",
                             ["product_category_name", "product_category_name_english"]),
}

RENAMES: dict[str, dict[str, str]] = {
    "customers": {"customer_zip_code_prefix": "zip_code_prefix", "customer_city": "city", "customer_state": "state"},
    "geolocation": {"geolocation_zip_code_prefix": "zip_code_prefix", "geolocation_lat": "lat",
                    "geolocation_lng": "lng", "geolocation_city": "city", "geolocation_state": "state"},
    "order_items": {"shipping_limit_date": "shipping_limit_ts"},
    "reviews": {"review_comment_title": "comment_title", "review_comment_message": "comment_message",
                "review_creation_date": "creation_ts", "review_answer_timestamp": "answer_ts"},
    "orders": {"order_purchase_timestamp": "purchase_ts", "order_approved_at": "approved_ts",
               "order_delivered_carrier_date": "delivered_carrier_ts",
               "order_delivered_customer_date": "delivered_customer_ts",
               "order_estimated_delivery_date": "estimated_delivery_ts"},
    "products": {"product_category_name": "category_name_pt", "product_name_lenght": "name_length",
                 "product_description_lenght": "description_length", "product_photos_qty": "photos_qty",
                 "product_weight_g": "weight_g", "product_length_cm": "length_cm",
                 "product_height_cm": "height_cm", "product_width_cm": "width_cm"},
    "sellers": {"seller_zip_code_prefix": "zip_code_prefix", "seller_city": "city", "seller_state": "state"},
}

# Column order of silver parquet == staging tables (stg.<name>) minus the trailing _run_id column.
SILVER_COLUMNS: dict[str, list[str]] = {
    "customers": ["customer_id", "customer_unique_id", "zip_code_prefix", "city", "state"],
    "geolocation": ["zip_code_prefix", "lat", "lng", "city", "state"],
    "order_items": ["order_id", "order_item_id", "product_id", "seller_id", "shipping_limit_ts", "price",
                    "freight_value"],
    "payments": ["order_id", "payment_sequential", "payment_type", "payment_installments", "payment_value"],
    "reviews": ["review_id", "order_id", "review_score", "comment_title", "comment_message", "creation_ts",
                "answer_ts"],
    "orders": ["order_id", "customer_id", "order_status", "purchase_ts", "approved_ts", "delivered_carrier_ts",
               "delivered_customer_ts", "estimated_delivery_ts"],
    "products": ["product_id", "category_name_pt", "category_name_en", "name_length", "description_length",
                 "photos_qty", "weight_g", "length_cm", "height_cm", "width_cm"],
    "sellers": ["seller_id", "zip_code_prefix", "city", "state"],
    "fx_rates": ["rate_date", "base_currency", "quote_currency", "rate"],
}

SILVER_TABLES = list(SILVER_COLUMNS)
PRIMARY_KEYS: dict[str, list[str]] = {
    "customers": ["customer_id"], "geolocation": ["zip_code_prefix"],
    "order_items": ["order_id", "order_item_id"], "payments": ["order_id", "payment_sequential"],
    "reviews": ["review_id", "order_id"], "orders": ["order_id"], "products": ["product_id"],
    "sellers": ["seller_id"], "fx_rates": ["rate_date", "base_currency", "quote_currency"],
}

ORDER_STATUSES = {"created", "approved", "invoiced", "processing", "shipped", "delivered",
                  "unavailable", "canceled"}

# Brazil bounding box (approx.) used to drop impossible geolocation points
BRAZIL_LAT = (-34.0, 5.5)
BRAZIL_LNG = (-74.0, -34.0)
