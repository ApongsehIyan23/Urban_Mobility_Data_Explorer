import os
import pandas as pd
from glob import glob
from datetime import datetime


class TLCCleaner:
    """
    Cleans and transforms NYC Yellow Taxi 2025 trip data.
    Processes all 12 monthly parquet files, applies validation rules,
    joins zone lookup data, and outputs a single combined clean parquet file.
    """

    # ------------------------------------------------------------------
    # CONSTANTS
    # ------------------------------------------------------------------
    VALID_VENDORS       = {1, 2, 6, 7}
    VALID_RATE_CODES    = {1, 2, 3, 4, 5, 6, 99}
    VALID_PAYMENT_TYPES = {0, 1, 2, 3, 4, 5, 6}
    VALID_LOCATION_IDS  = set(range(1, 264))
    VALID_PASSENGERS    = {1, 2, 3, 4}
    FREE_PAYMENT_TYPES  = {3, 4}  # No charge / Dispute — fare can be 0

    FINANCIAL_COLS = [
        "extra", "mta_tax", "tip_amount", "tolls_amount",
        "improvement_surcharge", "congestion_surcharge",
        "airport_fee", "cbd_congestion_fee"
    ]

    # Columns to impute before filtering
    IMPUTE_MAP = {
        "ratecode_id":        99,
        "store_and_fwd_flag": "N",
        "congestion_surcharge": 0.0,
        "airport_fee":        0.0,
    }

    # Rename raw columns to snake_case for DB compatibility
    COLUMN_RENAME_MAP = {
        "VendorID":               "vendor_id",
        "tpep_pickup_datetime":   "pickup_datetime",
        "tpep_dropoff_datetime":  "dropoff_datetime",
        "RatecodeID":             "ratecode_id",
        "PULocationID":           "pu_location_id",
        "DOLocationID":           "do_location_id",
        "Airport_fee":            "airport_fee",
    }