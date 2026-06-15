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

    #class variables
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

    def __init__(self, data_dir: str, processed_dir: str, log_dir: str):
        self.data_dir      = data_dir
        self.processed_dir = processed_dir
        self.log_dir       = log_dir

        os.makedirs(self.processed_dir, exist_ok=True)
        os.makedirs(self.log_dir, exist_ok=True)

        lookup_path = os.path.join(data_dir, "taxi_zone_lookup.csv")
        if not os.path.exists(lookup_path):
            raise FileNotFoundError(f"Zone lookup not found at {lookup_path}")
        self.zone_lookup = pd.read_csv(lookup_path)

        # Collect and sort all monthly parquet files
        self.files = sorted(glob(os.path.join(data_dir, "yellow_tripdata_2025-*.parquet")))
        if not self.files:
            raise FileNotFoundError(f"No parquet files found in {data_dir}")

        # Accumulators for combined output
        self.all_clean_dfs     = []
        self.all_exclusion_dfs = []
        self.monthly_stats     = []

    
    def _load_month(self, filepath: str) -> pd.DataFrame:
        """Load a monthly parquet file and rename columns to snake_case."""
        df = pd.read_parquet(filepath)
        df = df.rename(columns=self.COLUMN_RENAME_MAP)
        return df

    def _get_month_label(self, filepath: str) -> str:
        """Extract month label from filename e.g. '2025-01'."""
        return os.path.basename(filepath).replace("yellow_tripdata_", "").replace(".parquet", "")

    def _impute_nulls(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Fill nulls in non-critical fields with defined defaults
        before filtering rules are applied.
        Only rows that survive the passenger_count filter reach this stage.
        """
        for col, default in self.IMPUTE_MAP.items():
            if col in df.columns:
                df[col] = df[col].fillna(default)
        return df
    
    def _build_exclusion_mask(self, df: pd.DataFrame) -> pd.Series:
        """
        Error reasons are accumulated in a string for feedback
        """
        reasons = pd.Series([""] * len(df), index=df.index)

        def flag(mask: pd.Series, label: str):
            reasons[mask] += label + "|"

        # Rule 1 — Passenger count must be 1–4
        flag(~df["passenger_count"].isin(self.VALID_PASSENGERS), "invalid_passenger_count")

        # Rule 2 — Pickup must be within 2025
        flag(df["pickup_datetime"].dt.year != 2025, "out_of_range_timestamp")

        # Rule 3 — Dropoff must be after pickup
        flag(df["dropoff_datetime"] <= df["pickup_datetime"], "invalid_trip_duration")

        # Rule 4 — Trip distance must be > 0 and <= 150 miles
        flag(df["trip_distance"] <= 0, "invalid_distance")
        flag(df["trip_distance"] > 150, "distance_outlier")

        # Rule 5 — Fare amount must be > 0 (unless No Charge or Dispute)
        free_trip = df["payment_type"].isin(self.FREE_PAYMENT_TYPES)
        flag((df["fare_amount"] <= 0) & ~free_trip, "invalid_fare_amount")

        # Rule 6 — Fare amount must not exceed $500
        flag(df["fare_amount"] > 500, "fare_outlier")

        # Rule 7 — Total amount must be > 0 (unless No Charge or Dispute)
        flag((df["total_amount"] <= 0) & ~free_trip, "invalid_total_amount")

        # Rule 8 — No financial column should be negative
        for col in self.FINANCIAL_COLS:
            if col in df.columns:
                flag(df[col] < 0, f"negative_{col}")

        # Rule 9 — VendorID must be valid
        flag(~df["vendor_id"].isin(self.VALID_VENDORS), "invalid_vendor_id")

        # Rule 10 — RatecodeID must be valid
        flag(~df["ratecode_id"].isin(self.VALID_RATE_CODES), "invalid_ratecode_id")

        # Rule 11 — PULocationID must be valid
        flag(~df["pu_location_id"].isin(self.VALID_LOCATION_IDS), "invalid_pu_location")

        # Rule 12 — DOLocationID must be valid
        flag(~df["do_location_id"].isin(self.VALID_LOCATION_IDS), "invalid_do_location")

        # Rule 13 — Payment type must be valid
        flag(~df["payment_type"].isin(self.VALID_PAYMENT_TYPES), "invalid_payment_type")

        # Rule 14 — No duplicate rows
        duplicate_mask = df.duplicated(keep="first")
        flag(duplicate_mask, "duplicate_record")

        # Strip trailing pipe from each reason string
        reasons = reasons.str.rstrip("|")
        return reasons
    
    
