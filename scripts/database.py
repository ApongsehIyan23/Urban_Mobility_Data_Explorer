import sqlite3
import os

# Path to the database file
UMD_PATH = os.path.join(os.path.dirname(__file__), "data", "mobility.db")

#create a connection to sqlite
def open_connection():
    os.makedirs(os.path.dirname(UMD_PATH), exist_ok=True)
    conn = sqlite3.connect(UMD_PATH)
    conn.row_factory = sqlite3.Row
    return conn

#creates zones and trips tables if theu don't exist 
def create_tables():
   
    conn = open_connection()
    cursor = conn.cursor()

# Enable foreign key  in SQLite
    cursor.execute("PRAGMA foreign_keys = ON")

#Zones table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS taxi_zones (
            location_id   INTEGER PRIMARY KEY,
            borough       TEXT NOT NULL,
            zone_name     TEXT NOT NULL,
            service_zone  TEXT NOT NULL
        )
    """)

   #table for trips
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS taxi_trips (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            vendor_id               INTEGER,
            pickup_datetime         TEXT NOT NULL,
            dropoff_datetime        TEXT NOT NULL,
            passenger_count         INTEGER,
            trip_distance           REAL,
            ratecode_id             INTEGER,
            pu_location_id          INTEGER NOT NULL,
            do_location_id          INTEGER NOT NULL,
            payment_type            INTEGER,
            fare_amount             REAL,
            tip_amount              REAL,
            tolls_amount            REAL,
            total_amount            REAL,
            congestion_surcharge    REAL,
            airport_fee             REAL,
            pu_borough              TEXT,
            pu_zone                 TEXT,
            pu_service_zone         TEXT,
            do_borough              TEXT,
            do_zone                 TEXT,
            do_service_zone         TEXT,
            trip_duration_minutes   REAL,
            fare_per_mile           REAL,
            time_of_day             TEXT,
            speed_mph               REAL,
            tip_percentage          REAL,
            is_weekend              INTEGER,

            FOREIGN KEY (pu_location_id) REFERENCES zones(location_id),
            FOREIGN KEY (do_location_id) REFERENCES zones(location_id)
        )
    """)

#indexes
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_pickup_datetime
        ON taxi_trips(pickup_datetime)
    """)

    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_pu_location
        ON taxi_trips(pu_location_id)
    """)

   
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_do_location
        ON taxi_trips(do_location_id)
    """)

   
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_time_of_day
        ON taxi_trips(time_of_day)
    """)

    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_is_weekend
        ON taxi_trips(is_weekend)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_pu_borough
        ON taxi_trips(pu_borough)
    """)

    conn.commit()
    conn.close()
    print("Database tables and indexes created successfully.")

#database reset 
def reset_tables():
    
    conn = open_connection()
    cursor = conn.cursor()

    cursor.execute("DROP TABLE IF EXISTS taxi_trips")
    cursor.execute("DROP TABLE IF EXISTS taxi_zones")

    conn.commit()
    conn.close()
    print("All tables reset.")


if __name__ == "__main__":
    create_tables()