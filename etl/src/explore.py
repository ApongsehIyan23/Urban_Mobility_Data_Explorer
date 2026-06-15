import pandas as pd
import pyarrow.parquet as pq

# Load just January as our reference file
FILE = "data/raw/yellow_tripdata_2025-01.parquet"

# Read the full file
df = pd.read_parquet(FILE)

print("=" * 50)
print(f"Shape: {df.shape[0]:,} rows x {df.shape[1]} columns")
print("=" * 50)

print("\n--- Column Names & Data Types ---")
print(df.dtypes)

print("\n--- First 3 Rows ---")
print(df.head(3).to_string())

print("\n--- Missing Values ---")
nulls = df.isnull().sum()
print(nulls[nulls > 0])

print("\n--- Basic Statistics ---")
print(df.describe())
