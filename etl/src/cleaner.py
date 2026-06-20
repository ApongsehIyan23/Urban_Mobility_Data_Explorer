import os
import io
import sys
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import duckdb
import glob as glob_module
import multiprocessing
from datetime import datetime



#Funcion for multiprocessing
def process_month(args: tuple) -> dict:
    """
    Processes a single monthly parquet file through the full
    cleaning pipeline. Designed to run in a separate process.
    Steps: Load, Fill Nulls, Clean/Exclude rows, add error messages,
    engineer features, join zones, output results
    Returns a dict containing: cleaned_df, excluded_df, and monthly stats for summary report.
    """

    filepath, zone_lookup_path, config = args

    #config values
    VALID_VENDORS = config["VALID_VENDORS"]
    VALID_RATE_CODES = config["VALID_RATE_CODES"]
    VALID_PAYMENT_TYPES = config["VALID_PAYMENT_TYPES"]
    VALID_LOCATION_IDS  = config["VALID_LOCATION_IDS"]
    VALID_PASSENGERS    = config["VALID_PASSENGERS"]
    FREE_PAYMENT_TYPES  = config["FREE_PAYMENT_TYPES"]
    FINANCIAL_COLS  = config["FINANCIAL_COLS"]
    IMPUTE_MAP = config["IMPUTE_MAP"]
    COLUMN_RENAME_MAP = config["COLUMN_RENAME_MAP"]
    TRIP_KEY_COLS = config["TRIP_KEY_COLS"]

    label = (
        os.path.basename(filepath)
        .replace("yellow_tripdata_", "")
        .replace(".parquet", "")
    )
    print(f"  [{label}] Loading...")
    df = pd.read_parquet(filepath)
    df = df.rename(columns=COLUMN_RENAME_MAP) #rename columns
    raw_count = len(df)

    #check for duplicates based 5 key columns
    renamed_key_cols = [COLUMN_RENAME_MAP.get(c, c) for c in TRIP_KEY_COLS]
    duplicate_mask   = df.duplicated(subset=renamed_key_cols, keep="first")

    #fill nulls
    for col, default in IMPUTE_MAP.items():
        if col in df.columns:
            df[col] = df[col].fillna(default)
    
    free_trip = np.isin(df["payment_type"].values, list(FREE_PAYMENT_TYPES))

    masks = {
        "invalid_passenger_count": ~np.isin(df["passenger_count"].values, list(VALID_PASSENGERS)),
        "out_of_range_timestamp": df["pickup_datetime"].dt.year.values != 2025,
        "invalid_trip_duration":  df["dropoff_datetime"].values <= df["pickup_datetime"].values,
        "invalid_distance": df["trip_distance"].values <= 0,
        "distance_outlier": df["trip_distance"].values > 150,
        "invalid_fare_amount": (df["fare_amount"].values <= 0) & ~free_trip,
        "fare_outlier": df["fare_amount"].values > 500,
        "invalid_total_amount": (df["total_amount"].values <= 0) & ~free_trip,
        "invalid_vendor_id": ~np.isin(df["vendor_id"].values, list(VALID_VENDORS)),
        "invalid_ratecode_id": ~np.isin(df["ratecode_id"].values, list(VALID_RATE_CODES)),
        "invalid_pu_location": ~np.isin(df["pu_location_id"].values, list(VALID_LOCATION_IDS)),
        "invalid_do_location": ~np.isin(df["do_location_id"].values, list(VALID_LOCATION_IDS)),
        "invalid_payment_type": ~np.isin(df["payment_type"].values, list(VALID_PAYMENT_TYPES)),
        "duplicate_record": duplicate_mask.values,
    }


    # Add negative financial column masks
    for col in FINANCIAL_COLS:
        if col in df.columns:
            masks[f"negative_{col}"] = df[col].values < 0


    combined_exclusion_mask = np.zeros(len(df), dtype=bool)
    for mask in masks.values():
        combined_exclusion_mask |= mask

    clean_df    = df[~combined_exclusion_mask].copy()
    excluded_df = df[combined_exclusion_mask].copy()
    del df  # Free full DataFrame from memory immediately


    excluded_index  = excluded_df.index
    reason_series   = pd.Series([""] * len(excluded_df), index=excluded_index)

    for reason_label, mask in masks.items():
        # Align full mask to excluded subset only
        subset_mask = mask[combined_exclusion_mask]
        reason_series[subset_mask] = (
            reason_series[subset_mask] + reason_label + "|"
        )
    
    reason_series = reason_series.str.rstrip("|")
    excluded_df["flag_reasons"] = reason_series.values
    excluded_df["month"] = label

    #Features
    #trip duration in minutes
    clean_df["trip_duration_minutes"] = ((clean_df["dropoff_datetime"] - clean_df["pickup_datetime"]).dt.total_seconds() / 60).round(2)
    #fare per mile
    clean_df["fare_per_mile"] = ( clean_df["fare_amount"] / clean_df["trip_distance"]).round(4)
    #time of day category
    hour = clean_df["pickup_datetime"].dt.hour
    clean_df["time_of_day"] = "Night"
    clean_df.loc[(hour >= 5)  & (hour < 12), "time_of_day"] = "Morning"
    clean_df.loc[(hour >= 12) & (hour < 17), "time_of_day"] = "Afternoon"
    clean_df.loc[(hour >= 17) & (hour < 21), "time_of_day"] = "Evening"

    clean_df["speed_mph"] = ( clean_df["trip_distance"] / (clean_df["trip_duration_minutes"] / 60) ).round(4)
    clean_df["tip_percentage"] = ( clean_df["tip_amount"] / clean_df["fare_amount"] * 100 ).round(4)
    clean_df["is_weekend"] = clean_df["pickup_datetime"].dt.dayofweek.isin([5, 6]).astype(int)

    #Join zones
    zone_lookup = pd.read_csv(zone_lookup_path)
    lookup      = zone_lookup.rename(columns={
        "LocationID":   "location_id",
        "Borough":      "borough",
        "Zone":         "zone",
        "service_zone": "service_zone"
    })

    # Pickup join
    clean_df = clean_df.merge(
        lookup.rename(columns={
            "location_id":  "pu_location_id",
            "borough":      "pu_borough",
            "zone":         "pu_zone",
            "service_zone": "pu_service_zone"
        }),
        on="pu_location_id", how="left"
    )

    # Dropoff join
    clean_df = clean_df.merge(
        lookup.rename(columns={
            "location_id":  "do_location_id",
            "borough":      "do_borough",
            "zone":         "do_zone",
            "service_zone": "do_service_zone"
        }),
        on="do_location_id", how="left"
    )

    #exclusion breakdown
    exclusion_breakdown = {}
    for reason_label, mask in masks.items():
        count = int(mask[combined_exclusion_mask].sum())
        if count > 0:
            exclusion_breakdown[reason_label] = count

    stats = {
        "month": label,
        "raw_count": raw_count,
        "clean_count": len(clean_df),
        "excluded_count": len(excluded_df),
        "exclusion_breakdown": exclusion_breakdown
    }

    print(f"  [{label}] Done — {len(clean_df):,} clean / {len(excluded_df):,} excluded")

    return {
        "clean_df": clean_df,
        "excluded_df": excluded_df,
        "stats": stats,
        "label": label
    }




class TLCCleaner:
    """
    Orchestrates the full NYC Yellow Taxi 2025 ETL cleaning pipeline.
    Uses multiprocessing to process months in parallel and PyArrow
    ParquetWriter to append results directly to final output files/
    """

    # CONSTANTS
    VALID_VENDORS       = {1, 2, 6, 7}
    VALID_RATE_CODES    = {1, 2, 3, 4, 5, 6, 99}
    VALID_PAYMENT_TYPES = {0, 1, 2, 3, 4, 5, 6}
    VALID_LOCATION_IDS  = set(range(1, 264))
    VALID_PASSENGERS    = {1, 2, 3, 4}
    FREE_PAYMENT_TYPES  = {3, 4}

    FINANCIAL_COLS = [
        "extra", "mta_tax", "tip_amount", "tolls_amount",
        "improvement_surcharge", "congestion_surcharge",
        "airport_fee", "cbd_congestion_fee"
    ]

    IMPUTE_MAP = {
        "ratecode_id":          99,
        "store_and_fwd_flag":   "N",
        "congestion_surcharge": 0.0,
        "airport_fee":          0.0,
    }

    COLUMN_RENAME_MAP = {
        "VendorID":              "vendor_id",
        "tpep_pickup_datetime":  "pickup_datetime",
        "tpep_dropoff_datetime": "dropoff_datetime",
        "RatecodeID":            "ratecode_id",
        "PULocationID":          "pu_location_id",
        "DOLocationID":          "do_location_id",
        "Airport_fee":           "airport_fee",
    }

    # 5 key columns that uniquely identify a trip
    TRIP_KEY_COLS = [
        "VendorID",
        "tpep_pickup_datetime",
        "tpep_dropoff_datetime",
        "PULocationID",
        "DOLocationID"
    ]

    def __init__(self, data_dir: str, processed_dir: str, log_dir: str):
        self.data_dir      = data_dir
        self.processed_dir = processed_dir
        self.log_dir       = log_dir

        os.makedirs(self.processed_dir, exist_ok=True)
        os.makedirs(self.log_dir, exist_ok=True)

        self.zone_lookup_path = os.path.join(data_dir, "taxi_zone_lookup.csv")
        if not os.path.exists(self.zone_lookup_path):
            raise FileNotFoundError(
                f"Zone lookup not found at {self.zone_lookup_path}"
            )

        self.files = sorted(
            glob_module.glob(
                os.path.join(data_dir, "yellow_tripdata_2025-*.parquet")
            )
        )
        if not self.files:
            raise FileNotFoundError(f"No parquet files found in {data_dir}")

        self.monthly_stats = []

        #Added multiprocessing to use cpu cores simultaneously, but limit to 4 to avoid overwhelming the system
        #defaults to 1 core if os.cpu_count() returns None for any reason
        available_cores   = os.cpu_count() or 1
        self.num_workers  = min(4, available_cores, len(self.files))

    
    #print month summary
    def _print_month_summary(self, stats: dict):
        """Prints per-month cleaning statistics to console."""
        label      = stats["month"]
        raw        = stats["raw_count"]
        clean      = stats["clean_count"]
        excluded   = stats["excluded_count"]
        retention  = (clean / raw * 100) if raw > 0 else 0
        sep        = "=" * 60

        print(f"\n{sep}")
        print(f"  CLEANED: {label}")
        print(sep)
        print(f"  Raw rows:      {raw:>12,}")
        print(f"  Clean rows:    {clean:>12,}")
        print(f"  Excluded rows: {excluded:>12,}")
        print(f"  Retention:     {retention:>11.2f}%")
        print(f"\n  --- Exclusion Breakdown ---")
        for reason, count in sorted(
            stats["exclusion_breakdown"].items(), key=lambda x: -x[1]
        ):
            print(f"    {reason:<40} {count:>10,}")

    def _save_cleaning_summary(self):
        """Writes full year cleaning quality report to logs."""
        path          = os.path.join(self.log_dir, "cleaning_summary.txt")
        total_raw     = sum(s["raw_count"]     for s in self.monthly_stats)
        total_clean   = sum(s["clean_count"]   for s in self.monthly_stats)
        total_excluded= sum(s["excluded_count"]for s in self.monthly_stats)
        retention     = (total_clean / total_raw * 100) if total_raw > 0 else 0

        agg_reasons = {}
        for s in self.monthly_stats:
            for reason, count in s["exclusion_breakdown"].items():
                agg_reasons[reason] = agg_reasons.get(reason, 0) + count

        with open(path, "w") as f:
            f.write("=" * 60 + "\n")
            f.write("TLC Yellow Taxi 2025 - Cleaning Summary\n")
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
                r = (s["clean_count"] / s["raw_count"] * 100) \
                    if s["raw_count"] > 0 else 0
                f.write(
                    f"  {s['month']:<12} {s['raw_count']:>12,} "
                    f"{s['clean_count']:>12,} {s['excluded_count']:>12,} "
                    f"{r:>11.2f}%\n"
                )

            f.write("\nEXCLUSION BREAKDOWN (all months combined):\n")
            for reason, count in sorted(
                agg_reasons.items(), key=lambda x: -x[1]
            ):
                f.write(f"  {reason:<40} {count:>12,}\n")

            f.write("\nFINAL CLEAN DATASET:\n")
            f.write(f"  Output:          data/processed/yellow_2025_clean.parquet\n")
            f.write(f"  Exclusion log:   data/logs/yellow_2025_exclusions.parquet\n")
            f.write(f"  Passenger range: 1-4 passengers only\n")
            f.write(f"  Date range:      2025-01-01 to 2025-12-31\n")

        print(f"  Cleaning summary saved -> {path}")

    
    def run_with_profiler(self):
        """
        Runs the full pipeline wrapped in cProfile.
        Saves performance report to data/logs/profile_report.txt
        """
        import cProfile
        import pstats

        print("Starting profiled pipeline run...")
        print("=" * 60)

        profiler = cProfile.Profile()
        profiler.enable()
        self.run()
        profiler.disable()

        stream = io.StringIO()
        stats  = pstats.Stats(profiler, stream=stream)
        stats.strip_dirs()
        stats.sort_stats("cumulative")
        stats.print_stats(30)

        print("\n" + "=" * 60)
        print("PROFILER REPORT - TOP 30 BOTTLENECKS BY CUMULATIVE TIME")
        print("=" * 60)
        print(stream.getvalue())

        with open("data/logs/profile_report.txt", "w") as f:
            stream2 = io.StringIO()
            stats2  = pstats.Stats(profiler, stream=stream2)
            stats2.strip_dirs()
            stats2.sort_stats("cumulative")
            stats2.print_stats(50)
            f.write(stream2.getvalue())

        print("Full profile report saved -> data/logs/profile_report.txt")


    def run(self):
        """
        Orchestrates the full cleaning pipeline:
        - Distributes months across worker processes in parallel
        - Appends results directly to final parquet files
        - Saves cleaning summary report
        """
        import time as time_module
        start = time_module.time()

        print("TLC Yellow Taxi 2025 - Cleaning Pipeline")
        print(f"Files to process: {len(self.files)}")
        print(f"Workers: {self.num_workers}")
        print(f"Strategy: {'Parallel' if self.num_workers > 1 else 'Sequential'}")

        # Build config dict to pass to worker processes
        # Avoids passing the full class instance across process boundaries
        config = {
            "VALID_VENDORS":       self.VALID_VENDORS,
            "VALID_RATE_CODES":    self.VALID_RATE_CODES,
            "VALID_PAYMENT_TYPES": self.VALID_PAYMENT_TYPES,
            "VALID_LOCATION_IDS":  self.VALID_LOCATION_IDS,
            "VALID_PASSENGERS":    self.VALID_PASSENGERS,
            "FREE_PAYMENT_TYPES":  self.FREE_PAYMENT_TYPES,
            "FINANCIAL_COLS":      self.FINANCIAL_COLS,
            "IMPUTE_MAP":          self.IMPUTE_MAP,
            "COLUMN_RENAME_MAP":   self.COLUMN_RENAME_MAP,
            "TRIP_KEY_COLS":       self.TRIP_KEY_COLS,
        }

        # Build args list — one tuple per month
        args_list = [
            (filepath, self.zone_lookup_path, config)
            for filepath in self.files
        ]

        # Output file paths
        clean_path     = os.path.join(
            self.processed_dir, "yellow_2025_clean.parquet"
        )
        exclusion_path = os.path.join(
            self.log_dir, "yellow_2025_exclusions.parquet"
        )

        clean_writer     = None
        exclusion_writer = None

        
        # process months — parallel with Pool or sequential fallback
        print("\nProcessing months...")

        if self.num_workers > 1:
            with multiprocessing.Pool(processes=self.num_workers) as pool:
                for result in pool.imap(process_month, args_list):
                    clean_df = result["clean_df"]
                    excluded_df = result["excluded_df"]
                    stats = result["stats"]

                    # Append clean month to final clean parquet
                    clean_table = pa.Table.from_pandas(clean_df, preserve_index=False)
                    if clean_writer is None:
                        clean_writer = pq.ParquetWriter(clean_path, clean_table.schema)
                    clean_writer.write_table(clean_table)

                    # Append excluded month to final exclusion parquet
                    excl_table = pa.Table.from_pandas(excluded_df, preserve_index=False)
                    if exclusion_writer is None:
                        exclusion_writer = pq.ParquetWriter(
                            exclusion_path, excl_table.schema
                        )
                    exclusion_writer.write_table(excl_table)

                    self.monthly_stats.append(stats)
                    self._print_month_summary(stats)
                    del clean_df, excluded_df, clean_table, excl_table

        else:
            # Single worker fallback — sequential processing
            for args in args_list:
                result      = process_month(args)
                clean_df    = result["clean_df"]
                excluded_df = result["excluded_df"]
                stats       = result["stats"]

                clean_table = pa.Table.from_pandas(clean_df, preserve_index=False)
                if clean_writer is None:
                    clean_writer = pq.ParquetWriter(clean_path, clean_table.schema)
                clean_writer.write_table(clean_table)

                excl_table = pa.Table.from_pandas(excluded_df, preserve_index=False)
                if exclusion_writer is None:
                    exclusion_writer = pq.ParquetWriter(
                        exclusion_path, excl_table.schema
                    )
                exclusion_writer.write_table(excl_table)
                self.monthly_stats.append(stats)
                self._print_month_summary(stats)
                del clean_df, excluded_df, clean_table, excl_table

        # Close ParquetWriters — finalizes and flushes both files
        if clean_writer:
            clean_writer.close()
        if exclusion_writer:
            exclusion_writer.close()

        # statistics summary
        total_clean    = sum(s["clean_count"]    for s in self.monthly_stats)
        total_excluded = sum(s["excluded_count"] for s in self.monthly_stats)

        print(f"\nClean data saved    -> {clean_path}")
        print(f"Final clean rows    -> {total_clean:,}")
        print(f"Exclusion log saved -> {exclusion_path}")
        print(f"Total excluded rows -> {total_excluded:,}")

        # Save cleaning summary report
        self._save_cleaning_summary()

        elapsed     = time_module.time() - start
        mins, secs  = divmod(int(elapsed), 60)
        print(f"\nTotal pipeline time -> {mins}m {secs}s")
        print("\nPipeline complete.")


#entry point for script execution

if __name__ == "__main__":
    # Required on Windows for multiprocessing
    multiprocessing.freeze_support()

    cleaner = TLCCleaner(
        data_dir      = "data/raw",
        processed_dir = "data/processed",
        log_dir       = "data/logs"
    )
    cleaner.run_with_profiler()


    

    
    

