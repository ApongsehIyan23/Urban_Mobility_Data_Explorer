import sqlite3
import os

# Path to the database file
UMD_PATH = os.path.join(os.path.dirname(__file__), "data", "mobility.db")


def open_connection():
    os.makedirs(os.path.dirname(UMD_PATH), exist_ok=True)
    conn = sqlite3.connect(UMD_PATH)
    conn.row_factory = sqlite3.Row

    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")   
    conn.execute("PRAGMA cache_size = -64000")    
    conn.execute("PRAGMA temp_store = MEMORY")       
    conn.execute("PRAGMA synchronous = NORMAL")      

    return conn


def create_tables():
    conn = open_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS taxi_zones (
            location_id INTEGER PRIMARY KEY,
            borough TEXT NOT NULL,
            zone_name TEXT NOT NULL,
            service_zone TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS taxi_trips (
            vendor_id INTEGER NOT NULL,
            pickup_datetime TEXT NOT NULL,
            dropoff_datetime TEXT NOT NULL,
            passenger_count  INTEGER NOT NULL,
            trip_distance    REAL NOT NULL,
            ratecode_id      INTEGER,
            pu_location_id   INTEGER NOT NULL,
            do_location_id   INTEGER NOT NULL,
            payment_type     INTEGER NOT NULL,
            fare_amount      REAL NOT NULL,
            tip_amount       REAL NOT NULL,
            tolls_amount     REAL NOT NULL,
            total_amount     REAL NOT NULL,
            congestion_surcharge REAL,
            airport_fee          REAL,
            cbd_congestion_fee   REAL,
            trip_duration_minutes REAL NOT NULL,
            fare_per_mile  REAL,
            speed_mph      REAL,
            tip_percentage REAL,
            time_of_day    TEXT NOT NULL,
            is_weekend     INTEGER NOT NULL,
            
            FOREIGN KEY (pu_location_id) REFERENCES taxi_zones(location_id),
            FOREIGN KEY (do_location_id) REFERENCES taxi_zones(location_id)
        )
    """)

    conn.commit()
    conn.close()
    print("Tables created successfully.")


def create_indexes():
    """
    Creates indexes on taxi_trips after all data has been inserted.
    """
    conn = open_connection()

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_pickup_datetime
        ON taxi_trips(pickup_datetime)
    """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_pu_location_id
        ON taxi_trips(pu_location_id)
    """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_do_location_id
        ON taxi_trips(do_location_id)
    """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_time_of_day
        ON taxi_trips(time_of_day)
    """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_is_weekend
        ON taxi_trips(is_weekend)
    """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_payment_type
        ON taxi_trips(payment_type)
    """)

    conn.commit()
    conn.close()
    print("Indexes created successfully.")


def reset_tables():
    """
    Drops all tables in correct dependency order.
    Child tables (with foreign keys) dropped before parent tables.
    """
    conn = open_connection()

    conn.execute("DROP TABLE IF EXISTS taxi_trips")
    conn.execute("DROP TABLE IF EXISTS taxi_zones")

    conn.commit()
    conn.close()
    print("All tables reset.")


if __name__ == "__main__":
    create_tables()