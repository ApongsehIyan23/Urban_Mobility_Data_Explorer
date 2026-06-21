import os
import sqlite3
import multiprocessing
import pandas as pd
import pyarrow.parquet as pq

from database import open_connection, create_tables, create_indexes


CLEANED_DATA_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "etl", "data", "processed", "yellow_2025_clean.parquet"
)

ZONE_LOOKUP_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "etl", "data", "raw", "taxi_zone_lookup.csv"
)

DB_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "data", "mobility.db"
)

#increased batch size to 1M and added workers to 4 for multiprocessing
BATCH_SIZE  = 1_000_000
MAX_WORKERS = min(4, os.cpu_count() or 1)


COLUMNS_TO_INSERT = [
    "vendor_id",
    "pickup_datetime",
    "dropoff_datetime",
    "passenger_count",
    "trip_distance",
    "ratecode_id",
    "pu_location_id",
    "do_location_id",
    "payment_type",
    "fare_amount",
    "tip_amount",
    "tolls_amount",
    "total_amount",
    "congestion_surcharge",
    "airport_fee",
    "cbd_congestion_fee",
    "trip_duration_minutes",
    "fare_per_mile",
    "speed_mph",
    "tip_percentage",
    "time_of_day",
    "is_weekend",
]



def process_batch(batch) -> pd.DataFrame:
    """
    converts a pyarrow batch to a pandas dataframe
    """
    df = batch.to_pandas()
    df = df[COLUMNS_TO_INSERT]
    return df


def insert_zones(conn: sqlite3.Connection):
    """ Zone Insertion """
    print("Inserting zones...")

    zone_df = pd.read_csv(ZONE_LOOKUP_PATH)
    zone_df = zone_df.rename(columns={
        "LocationID":   "location_id",
        "Borough":      "borough",
        "Zone":         "zone_name",
        "service_zone": "service_zone"
    })
    zone_df = zone_df[["location_id", "borough", "zone_name", "service_zone"]]

    records = [
        (int(row.location_id), str(row.borough),
         str(row.zone_name), str(row.service_zone))
        for row in zone_df.itertuples(index=False)
    ]

    conn.cursor().executemany("""
        INSERT OR IGNORE INTO taxi_zones
        (location_id, borough, zone_name, service_zone)
        VALUES (?, ?, ?, ?)
    """, records)

    conn.commit()
    print(f"Zones inserted successfully - {len(records)} zones loaded.")



def insert_trips(conn: sqlite3.Connection):
    """
    Inserts all 34M cleaned trip records from the clean parquet file.
    """
    print("Inserting trips...")
    print(f"Batch size:  {BATCH_SIZE:,} rows")
    print(f"Workers:     {MAX_WORKERS}")

    conn.execute("PRAGMA synchronous = OFF")

    parquet_file  = pq.ParquetFile(CLEANED_DATA_PATH)
    batches       = list(parquet_file.iter_batches(batch_size=BATCH_SIZE))
    total_batches = len(batches)
    total_inserted = 0

    print(f"Total batches to process: {total_batches}")

    with multiprocessing.Pool(processes=MAX_WORKERS) as pool:
        for batch_number, df in enumerate(
            pool.imap(process_batch, batches), start=1
        ):
            # Explicit transaction per batch
            df.to_sql(
                name      = "taxi_trips",
                con       = conn,
                if_exists = "append",
                index     = False,
            )

            total_inserted += len(df)
            print(
                f"Batch {batch_number}/{total_batches} inserted "
                f"- {total_inserted:,} rows so far")
            del df

    # Restore safe synchronous mode after bulk load
    conn.execute("PRAGMA synchronous = NORMAL")
    print(f"\nAll trips inserted successfully - {total_inserted:,} total rows.")


def run_insertion():
    print("Urban Mobility Database - Insertion Pipeline")
    print("=" * 50)

    create_tables()

    conn = open_connection()
    insert_zones(conn)
    insert_trips(conn)

    # Step 5 — Update SQLite query planner statistics
    print("Running ANALYZE...")
    conn.execute("ANALYZE")
    conn.commit()
    print("ANALYZE complete.")

    conn.close()

    # Step 6 — Build indexes after all data is loaded
   
    print("Building indexes...")
    create_indexes()

    print("=" * 50)
    print("Insertion pipeline complete.")


if __name__ == "__main__":
    multiprocessing.freeze_support()  # required on Windows
    run_insertion()