"""
Sample Data Script
Creates a smaller working dataset using DuckDB for faster API responses.
Run this once after insertionDB.py to create a sampled database.
"""

import duckdb
import os

FULL_DATA = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "etl", "data", "processed", "yellow_2025_clean.parquet"
).replace("\\", "/")

SAMPLED_DATA = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "data", "sampled_trips.parquet"
).replace("\\", "/")


def create_sample():
    print("Creating 5% sample of cleaned data...")

    total = duckdb.execute(
        f"SELECT COUNT(*) FROM read_parquet('{FULL_DATA}')"
    ).fetchone()[0]
    print(f"Full dataset: {total:,} rows")

    duckdb.execute(f"""
        COPY (
            SELECT * FROM read_parquet('{FULL_DATA}')
            USING SAMPLE 20 PERCENT
        ) TO '{SAMPLED_DATA}' (FORMAT PARQUET)
    """)

    sampled = duckdb.execute(
        f"SELECT COUNT(*) FROM read_parquet('{SAMPLED_DATA}')"
    ).fetchone()[0]

    print(f"Sampled dataset: {sampled:,} rows")
    print(f"Saved to: {SAMPLED_DATA}")
    print("Done. Now reset database and run insertionDB.py pointing to sampled file.")


if __name__ == "__main__":
    create_sample()