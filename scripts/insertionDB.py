import os
import sys
import pandas as pd
import pyarrow.parquet as pq

# Add path so as to  import database.py
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import create_tables

# Path to the cleaned data
CLEANED_DATA_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "data", "sampled_trips.parquet"
)

# Path to the zone lookup 
ZONE_LOOKUP_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "etl", "data", "raw", "taxi_zone_lookup.csv"
)

BATCH_SIZE = 500_000


def add_extra_features(df):
    
    df["speed_mph"] = (
        df["trip_distance"] / (df["trip_duration_minutes"] / 60)
    ).round(4)
    df["speed_mph"] = df["speed_mph"].where(df["trip_duration_minutes"] > 0)

    df["tip_percentage"] = (
        df["tip_amount"] / df["fare_amount"] * 100
    ).round(4)
    df["tip_percentage"] = df["tip_percentage"].where(df["fare_amount"] > 0)

    df["pickup_datetime"] = pd.to_datetime(df["pickup_datetime"])
    df["is_weekend"] = df["pickup_datetime"].dt.dayofweek.isin([5, 6]).astype(int)

    df["pickup_datetime"] = df["pickup_datetime"].dt.strftime("%Y-%m-%d %H:%M:%S")

    return df

#reads and inserts zones 
def insert_zones(conn):

    print("Inserting zones...")

    zone_df = pd.read_csv(ZONE_LOOKUP_PATH)

    zone_df = zone_df.rename(columns={
        "LocationID":   "location_id",
        "Borough":      "borough",
        "Zone":         "zone_name",
        "service_zone": "service_zone"
    })

    zone_df = zone_df[["location_id", "borough", "zone_name", "service_zone"]]

    cursor = conn.cursor()

    for _, row in zone_df.iterrows():
        cursor.execute("""
            INSERT OR IGNORE INTO taxi_zones
            (location_id, borough, zone_name, service_zone)
            VALUES (?, ?, ?, ?)
        """, (
            int(row["location_id"]),
            str(row["borough"]),
            str(row["zone_name"]),
            str(row["service_zone"])
        ))

    conn.commit()
    print(f"Zones inserted successfully — {len(zone_df)} zones loaded.")

# reads and insert trips 
def insert_trips(conn):
    print("Inserting trips in batches...")
    print(f"Batch size: {BATCH_SIZE:,} rows per batch")

    parquet_file = pq.ParquetFile(CLEANED_DATA_PATH)

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
        "pu_borough",
        "pu_zone",
        "pu_service_zone",
        "do_borough",
        "do_zone",
        "do_service_zone",
        "trip_duration_minutes",
        "fare_per_mile",
        "time_of_day",
        "speed_mph",
        "tip_percentage",
        "is_weekend"
    ]

    batch_number = 0
    total_inserted = 0

    for batch in parquet_file.iter_batches(batch_size=BATCH_SIZE):
        batch_number += 1
        df = batch.to_pandas()

        df = add_extra_features(df)

        df = df[COLUMNS_TO_INSERT]

        df.to_sql(
            name="taxi_trips",
            con=conn,
            if_exists="append",
            index=False,
        )

        total_inserted += len(df)
        print(f"Batch {batch_number} inserted — {total_inserted:,} rows so far")

        del df

    print(f"\nAll trips inserted successfully — {total_inserted:,} total rows.")


def run_insertion():
   
    print("Urban Mobility Database — Insertion Pipeline")
    print("=" * 50)

    create_tables()

    import sqlite3
    raw_conn = sqlite3.connect(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "mobility.db")
)

    insert_zones(raw_conn)

    insert_trips(raw_conn)

    print("Optimizing database...")
    raw_conn.execute("ANALYZE")
    raw_conn.commit()
    print("Database optimized.")

    raw_conn.close()
    print("=" * 50)
    print("Insertion pipeline complete.")

if __name__ == "__main__":
    run_insertion()