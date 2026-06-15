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
    
    def _apply_filters(self, df: pd.DataFrame) -> tuple:
        """
        Applies all 14 exclusion rules.
        """
        reasons = self._build_exclusion_mask(df)

        excluded_mask = reasons != ""
        clean_df      = df[~excluded_mask].copy()
        excluded_df   = df[excluded_mask].copy()
        excluded_df["flag_reasons"] = reasons[excluded_mask]

        return clean_df, excluded_df
    
    def _normalize_timestamps(self, df: pd.DataFrame) -> pd.DataFrame:
        """Convert timestamps to DB-ready string format YYYY-MM-DD HH:MM:SS."""
        for col in ["pickup_datetime", "dropoff_datetime"]:
            df[col] = df[col].dt.strftime("%Y-%m-%d %H:%M:%S")
        return df
    
    def _join_zones(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Joins taxi_zone_lookup.csv to trip data for both pickup
        and dropoff locations. Adds borough, zone name, and
        service zone for each.
        """
        lookup = self.zone_lookup.rename(columns={
            "LocationID":   "location_id",
            "Borough":      "borough",
            "Zone":         "zone",
            "service_zone": "service_zone"
        })

        # Join for pickup location
        df = df.merge(
            lookup.rename(columns={
                "location_id": "pu_location_id",
                "borough":     "pu_borough",
                "zone":        "pu_zone",
                "service_zone":"pu_service_zone"
            }),
            on="pu_location_id",
            how="left"
        )

        # Join for dropoff location
        df = df.merge(
            lookup.rename(columns={
                "location_id": "do_location_id",
                "borough":     "do_borough",
                "zone":        "do_zone",
                "service_zone":"do_service_zone"
            }),
            on="do_location_id",
            how="left"
        )

        return df
    
    def _engineer_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Derives new analytical columns from existing fields.
        """
        # Feature 1 — Trip duration in minutes
        df["trip_duration_minutes"] = (
            (df["dropoff_datetime"] - df["pickup_datetime"])
            .dt.total_seconds() / 60
        ).round(2)

        # Feature 2 — Fare per mile (cost efficiency metric)
        df["fare_per_mile"] = (df["fare_amount"] / df["trip_distance"]).round(4)

        # Feature 3 — Time of day category
        hour = df["pickup_datetime"].dt.hour
        # Simpler direct mapping
        df["time_of_day"] = "Night"
        df.loc[(hour >= 5)  & (hour < 12), "time_of_day"] = "Morning"
        df.loc[(hour >= 12) & (hour < 17), "time_of_day"] = "Afternoon"
        df.loc[(hour >= 17) & (hour < 21), "time_of_day"] = "Evening"

        return df
    

    def _print_month_summary(self, label: str, raw_count: int, clean_count: int, excluded_count: int, exclusion_breakdown: dict):
        """Prints per-month cleaning statistics to console."""
        retention = (clean_count / raw_count * 100) if raw_count > 0 else 0
        sep = "=" * 60

        print(f"\n{sep}")
        print(f"  CLEANED: {label}")
        print(sep)
        print(f"  Raw rows:      {raw_count:>12,}")
        print(f"  Clean rows:    {clean_count:>12,}")
        print(f"  Excluded rows: {excluded_count:>12,}")
        print(f"  Retention:     {retention:>11.2f}%")
        print(f"\n  --- Exclusion Breakdown ---")
        for reason, count in sorted(exclusion_breakdown.items(), key=lambda x: -x[1]):
            print(f" {reason:<35} {count:>10,}")

    
    def _save_cleaning_summary(self):
        """Writes the full year cleaning summary to cleaning_summary.txt."""
        path = os.path.join(self.log_dir, "cleaning_summary.txt")
        total_raw     = sum(s["raw_count"] for s in self.monthly_stats)
        total_clean   = sum(s["clean_count"] for s in self.monthly_stats)
        total_excluded= sum(s["excluded_count"] for s in self.monthly_stats)
        retention     = (total_clean / total_raw * 100) if total_raw > 0 else 0

        # Aggregate exclusion reasons across all months
        agg_reasons = {}
        for s in self.monthly_stats:
            for reason, count in s["exclusion_breakdown"].items():
                agg_reasons[reason] = agg_reasons.get(reason, 0) + count

        with open(path, "w") as f:
            f.write("=" * 60 + "\n")
            f.write("TLC Yellow Taxi 2025 — Cleaning Summary\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 60 + "\n\n")

            f.write("FULL YEAR OVERVIEW:\n")
            f.write(f"  Total raw rows:      {total_raw:>12,}\n")
            f.write(f"  Total clean rows:    {total_clean:>12,}\n")
            f.write(f"  Total excluded:      {total_excluded:>12,}\n")
            f.write(f"  Overall retention:   {retention:>11.2f}%\n\n")

            f.write("PER MONTH BREAKDOWN:\n")
            f.write(f"  {'Month':<12} {'Raw Rows':>12} {'Clean Rows':>12} "
                    f"{'Excluded':>12} {'Retention%':>12}\n")
            f.write("  " + "-" * 52 + "\n")
            for s in self.monthly_stats:
                r = (s["clean_count"] / s["raw_count"] * 100) if s["raw_count"] > 0 else 0
                f.write(f"  {s['month']:<12} {s['raw_count']:>12,} "
                        f"{s['clean_count']:>12,} {s['excluded_count']:>12,} "
                        f"{r:>11.2f}%\n")

            f.write("\nEXCLUSION BREAKDOWN (all months combined):\n")
            for reason, count in sorted(agg_reasons.items(), key=lambda x: -x[1]):
                f.write(f"  {reason:<40} {count:>12,}\n")

            f.write("\nFINAL CLEAN DATASET:\n")
            f.write(f"  Output: data/processed/yellow_2025_clean.parquet\n")
            f.write(f"  Passenger range: 1–4 passengers only\n")
            f.write(f"  Date range: 2025-01-01 to 2025-12-31\n")

        print(f"\n  Cleaning summary saved → {path}")

    def _cleanup_monthly_files(self):
        """
        Deletes all intermediate monthly clean parquet files and
        monthly exclusion CSV files after they have been merged
        into single combined output files via DuckDB.
        Called only after successful merge of both outputs.
        """
        import glob as glob_module

        # Delete monthly clean parquet files
        monthly_clean_files = glob_module.glob(
            os.path.join(self.processed_dir, "yellow_2025-*_clean.parquet")
        )
        for f in monthly_clean_files:
            os.remove(f)

        # Delete monthly exclusion CSV files
        monthly_exclusion_files = glob_module.glob(
            os.path.join(self.log_dir, "exclusions_2025-*.csv")
        )
        for f in monthly_exclusion_files:
            os.remove(f)

        print(f"  Deleted {len(monthly_clean_files)} monthly clean parquet files.")
        print(f"  Deleted {len(monthly_exclusion_files)} monthly exclusion CSV files.")


    def run(self):
        """
        Orchestrates the full cleaning pipeline across all 12 months:
        load → rename → impute → filter → engineer → join zones →
        normalize timestamps → save monthly files → merge via DuckDB → summarize
        """
        import duckdb

        print("TLC Yellow Taxi 2025 — Cleaning Pipeline")
        print(f"Files to process: {len(self.files)}")

        for filepath in self.files:
            label     = self._get_month_label(filepath)
            print(f"\nProcessing {label}...")
            df = self._load_month(filepath)
            raw_count = len(df)

            df = self._impute_nulls(df)
            clean_df, excluded_df = self._apply_filters(df)
            del df

            clean_df  = self._engineer_features(clean_df)
            clean_df  = self._join_zones(clean_df)
            clean_df  = self._normalize_timestamps(clean_df)
            monthly_clean_path = os.path.join(
                self.processed_dir, f"yellow_{label}_clean.parquet"
            )
            clean_df.to_parquet(monthly_clean_path, index=False)
            # Step 8 — Tag excluded rows with month label and save to disk
            excluded_df["month"] = label
            monthly_exclusion_path = os.path.join(
            self.log_dir, f"exclusions_{label}.csv"
            )
            excluded_df.to_csv(monthly_exclusion_path, index=False)
            # Step 9 — Compute exclusion breakdown for this month
            
            exclusion_breakdown = {}
            for reasons_str in excluded_df["flag_reasons"]:
                for reason in reasons_str.split("|"):
                    if reason:
                        exclusion_breakdown[reason] = \
                            exclusion_breakdown.get(reason, 0) + 1

            # Step 10 — Store monthly stats for summary report
            self.monthly_stats.append({
                "month": label,
                "raw_count": raw_count,
                "clean_count": len(clean_df),
                "excluded_count": len(excluded_df),
                "exclusion_breakdown": exclusion_breakdown
            })

            # Step 11 — Print month summary then free memory
            self._print_month_summary(
                label, raw_count, len(clean_df),
                len(excluded_df), exclusion_breakdown
            )
            del clean_df, excluded_df

        # MERGE PHASE — Combine monthly files on disk via DuckDB (no RAM spike)
        # ------------------------------------------------------------------

        # Merge all clean monthly parquet files into one combined file
        print("\nMerging all clean months into single file via DuckDB...")
        monthly_clean_pattern  = os.path.join(
            self.processed_dir, "yellow_2025-*_clean.parquet"
        ).replace("\\", "/")
        clean_path = os.path.join(
            self.processed_dir, "yellow_2025_clean.parquet"
        ).replace("\\", "/")

        duckdb.execute(f"""
            COPY (
                SELECT * FROM read_parquet('{monthly_clean_pattern}')
            ) TO '{clean_path}' (FORMAT PARQUET)
        """)

        final_count = duckdb.execute(
            f"SELECT COUNT(*) FROM read_parquet('{clean_path}')"
        ).fetchone()[0]
        print(f"Clean data saved    → {clean_path}")
        print(f"Final row count     → {final_count:,}")

        # Merge all monthly exclusion CSVs into one combined log
        print("\nMerging all exclusion logs...")
        monthly_exclusion_pattern = os.path.join(
            self.log_dir, "exclusions_2025-*.csv"
        ).replace("\\", "/")
        exclusion_path = os.path.join(
            self.log_dir, "exclusions_2025_all.csv"
        ).replace("\\", "/")

        duckdb.execute(f"""
            COPY (
                SELECT * FROM read_csv_auto('{monthly_exclusion_pattern}')
                ) TO '{exclusion_path}'
            """)

        exclusion_count = duckdb.execute(
            f"SELECT COUNT(*) FROM read_csv_auto('{exclusion_path}')").fetchone()[0]
        print(f"Exclusion log saved → {exclusion_path}")
        print(f"Total excluded rows → {exclusion_count:,}")


        # Cleanup
        print("\nCleaning up intermediate monthly files...")
        self._cleanup_monthly_files()

        # Save cleaning summary report
        self._save_cleaning_summary()

        print("\nPipeline complete.")


#Launch the cleaner when this script is run directly

if __name__ == "__main__":
    cleaner = TLCCleaner(
        data_dir      = "data/raw",
        processed_dir = "data/processed",
        log_dir       = "data/logs"
    )
    cleaner.run()


    

    
    

