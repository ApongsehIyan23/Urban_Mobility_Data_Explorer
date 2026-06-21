import os
import time
import sqlite3
import multiprocessing
import pandas as pd
import pyarrow.parquet as pq
from database import open_connection

PAYMENT_LABELS = {
    0: "Flex Fare",
    1: "Credit Card",
    2: "Cash",
    3: "No Charge",
    4: "Dispute",
    5: "Unknown",
    6: "Voided Trip"
}

FARE_BUCKET_ORDER = {
    "$0-$10": 1, "$10-$20": 2, "$20-$30": 3, "$30-$40": 4,
    "$40-$50": 5, "$50-$75": 6, "$75-$100": 7, "$100+": 8
}

CLEAN_PARQUET_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "etl", "data", "processed", "yellow_2025_clean.parquet"
)

ZONE_LOOKUP_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "etl", "data", "raw", "taxi_zone_lookup.csv"
)

BATCH_SIZE  = 1_000_000
MAX_WORKERS = min(4, os.cpu_count() or 1)


def process_batch(batch) -> dict:
    df = batch.to_pandas()

    df["fare_bucket"] = pd.cut(
        df["fare_amount"],
        bins=[0, 10, 20, 30, 40, 50, 75, 100, float("inf")],
        labels=["$0-$10", "$10-$20", "$20-$30", "$30-$40",
                "$40-$50", "$50-$75", "$75-$100", "$100+"],
        right=False
    ).astype(str)

    by_zone = df.groupby("pu_location_id").agg(
        count        = ("fare_amount",           "count"),
        sum_revenue  = ("total_amount",          "sum"),
        sum_fare     = ("fare_amount",            "sum"),
        sum_distance = ("trip_distance",          "sum"),
        sum_duration = ("trip_duration_minutes",  "sum"),
        sum_tip_pct  = ("tip_percentage",         "sum"),
        sum_speed    = ("speed_mph",              "sum"),
    ).reset_index()

    df["hour"] = pd.to_datetime(df["pickup_datetime"]).dt.hour
    by_hour = df.groupby("hour").agg(
        count        = ("fare_amount",           "count"),
        sum_fare     = ("fare_amount",            "sum"),
        sum_duration = ("trip_duration_minutes",  "sum"),
        sum_speed    = ("speed_mph",              "sum"),
    ).reset_index()

    by_weekend = df.groupby("is_weekend").agg(
        count        = ("fare_amount",           "count"),
        sum_fare     = ("fare_amount",            "sum"),
        sum_distance = ("trip_distance",          "sum"),
        sum_duration = ("trip_duration_minutes",  "sum"),
        sum_tip_pct  = ("tip_percentage",         "sum"),
        sum_speed    = ("speed_mph",              "sum"),
    ).reset_index()

    by_payment = df.groupby("payment_type").agg(
        count = ("fare_amount", "count")
    ).reset_index()

    by_fare = df.groupby("fare_bucket").agg(
        count = ("fare_amount", "count")
    ).reset_index()

    del df
    return {
        "by_zone":    by_zone.assign(count=by_zone["count"].astype(int)),
        "by_hour":    by_hour.assign(count=by_hour["count"].astype(int)),
        "by_weekend": by_weekend.assign(count=by_weekend["count"].astype(int)),
        "by_payment": by_payment.assign(count=by_payment["count"].astype(int)),
        "by_fare":    by_fare.assign(count=by_fare["count"].astype(int)),
    }


def combine_partials(partial_results: list, zone_lookup: dict) -> dict:
    zone_acc    = {}
    hour_acc    = {}
    weekend_acc = {}
    payment_acc = {}
    fare_acc    = {}

    for partial in partial_results:
        for _, row in partial["by_zone"].iterrows():
            loc = int(row["pu_location_id"])
            if loc not in zone_acc:
                zone_acc[loc] = {k: 0 for k in
                    ["count", "sum_revenue", "sum_fare", "sum_distance",
                     "sum_duration", "sum_tip_pct", "sum_speed"]}
            z = zone_acc[loc]
            z["count"]        += row["count"]
            z["sum_revenue"]  += row["sum_revenue"]
            z["sum_fare"]     += row["sum_fare"]
            z["sum_distance"] += row["sum_distance"]
            z["sum_duration"] += row["sum_duration"]
            z["sum_tip_pct"]  += row["sum_tip_pct"]
            z["sum_speed"]    += row["sum_speed"]

        for _, row in partial["by_hour"].iterrows():
            h = int(row["hour"])
            if h not in hour_acc:
                hour_acc[h] = {"count": 0, "sum_fare": 0,
                               "sum_duration": 0, "sum_speed": 0}
            hour_acc[h]["count"]        += row["count"]
            hour_acc[h]["sum_fare"]     += row["sum_fare"]
            hour_acc[h]["sum_duration"] += row["sum_duration"]
            hour_acc[h]["sum_speed"]    += row["sum_speed"]

        for _, row in partial["by_weekend"].iterrows():
            w = int(row["is_weekend"])
            if w not in weekend_acc:
                weekend_acc[w] = {
                    "count": 0, "sum_fare": 0, "sum_distance": 0,
                    "sum_duration": 0, "sum_tip_pct": 0, "sum_speed": 0
                }
            weekend_acc[w]["count"]        += row["count"]
            weekend_acc[w]["sum_fare"]     += row["sum_fare"]
            weekend_acc[w]["sum_distance"] += row["sum_distance"]
            weekend_acc[w]["sum_duration"] += row["sum_duration"]
            weekend_acc[w]["sum_tip_pct"]  += row["sum_tip_pct"]
            weekend_acc[w]["sum_speed"]    += row["sum_speed"]

        for _, row in partial["by_payment"].iterrows():
            p = int(row["payment_type"])
            payment_acc[p] = payment_acc.get(p, 0) + row["count"]

        for _, row in partial["by_fare"].iterrows():
            b = str(row["fare_bucket"])
            fare_acc[b] = fare_acc.get(b, 0) + row["count"]

    # ---- Zone counts ----
    zone_counts = [
        {"location_id": loc, "trip_count": int(z["count"])}
        for loc, z in zone_acc.items()
    ]

    # ---- Borough summary (weighted averages via Python) ----
    borough_acc = {}
    for loc, z in zone_acc.items():
        info    = zone_lookup.get(loc, {})
        borough = info.get("borough", "Unknown")
        if borough not in borough_acc:
            borough_acc[borough] = {k: 0 for k in
                ["count", "sum_revenue", "sum_fare", "sum_distance",
                 "sum_duration", "sum_tip_pct", "sum_speed"]}
        b = borough_acc[borough]
        for k in z:
            b[k] += z[k]

    borough_summary = []
    for borough, b in sorted(borough_acc.items(), key=lambda x: -x[1]["count"]):
        n = int(b["count"])
        borough_summary.append({
            "borough":      borough,
            "total_trips":  n,
            "avg_fare":     round(b["sum_fare"]     / n, 2),
            "avg_distance": round(b["sum_distance"] / n, 2),
            "avg_duration": round(b["sum_duration"] / n, 2),
            "avg_tip_pct":  round(b["sum_tip_pct"]  / n, 2),
            "avg_speed":    round(b["sum_speed"]    / n, 2),
        })

    # ---- Top 15 zones ----
    sorted_zones = sorted(zone_acc.items(), key=lambda x: -x[1]["count"])[:15]
    top_zones = []
    for rank, (loc, z) in enumerate(sorted_zones, start=1):
        info = zone_lookup.get(loc, {})
        top_zones.append({
            "rank":        rank,
            "location_id": loc,
            "zone_name":   info.get("zone_name", "Unknown"),
            "borough":     info.get("borough",   "Unknown"),
            "trip_count":  int(z["count"]),
        })

    # ---- Hourly summary ----
    hourly_summary = []
    for h in sorted(hour_acc.keys()):
        a = hour_acc[h]
        n = int(a["count"])
        hourly_summary.append({
            "hour":         h,
            "trip_count":   n,
            "avg_fare":     round(a["sum_fare"]     / n, 2),
            "avg_duration": round(a["sum_duration"] / n, 2),
            "avg_speed":    round(a["sum_speed"]    / n, 2),
        })
    busiest_hour = max(hour_acc.items(), key=lambda x: x[1]["count"])[0]

    # ---- Weekend vs weekday ----
    weekend_summary = []
    for w in sorted(weekend_acc.keys()):
        a = weekend_acc[w]
        n = int(a["count"])
        weekend_summary.append({
            "day_type":     "Weekend" if w == 1 else "Weekday",
            "total_trips":  n,
            "avg_fare":     round(a["sum_fare"]     / n, 2),
            "avg_distance": round(a["sum_distance"] / n, 2),
            "avg_duration": round(a["sum_duration"] / n, 2),
            "avg_tip_pct":  round(a["sum_tip_pct"]  / n, 2),
            "avg_speed":    round(a["sum_speed"]    / n, 2),
        })

    # ---- Payment breakdown ----
    total_trips = int(sum(payment_acc.values()))
    payment_summary = sorted(
        [
            {
                "payment_type": p,
                "label":        PAYMENT_LABELS.get(p, "Unknown"),
                "trip_count":   int(c),
                "percentage":   round(c / total_trips * 100, 2),
            }
            for p, c in payment_acc.items()
        ],
        key=lambda x: -x["trip_count"]
    )

    # ---- Fare distribution ----
    fare_summary = sorted(
        [{"fare_bucket": b, "trip_count": int(c)} for b, c in fare_acc.items()],
        key=lambda x: FARE_BUCKET_ORDER.get(x["fare_bucket"], 9)
    )

    # ---- Global stats ----
    total_revenue   = sum(z["sum_revenue"] for z in zone_acc.values())
    total_sum_fare  = sum(z["sum_fare"]    for z in zone_acc.values())
    total_sum_dist  = sum(z["sum_distance"]for z in zone_acc.values())
    total_sum_dur   = sum(z["sum_duration"]for z in zone_acc.values())
    total_sum_speed = sum(z["sum_speed"]   for z in zone_acc.values())
    busiest_borough = max(borough_acc.items(), key=lambda x: x[1]["count"])[0]

    global_stats = {
        "total_trips":     total_trips,
        "total_revenue":   round(total_revenue,              2),
        "avg_fare":        round(total_sum_fare  / total_trips, 2),
        "avg_distance":    round(total_sum_dist  / total_trips, 2),
        "avg_duration":    round(total_sum_dur   / total_trips, 2),
        "avg_speed":       round(total_sum_speed / total_trips, 2),
        "busiest_hour":    busiest_hour,
        "busiest_borough": busiest_borough,
    }

    return {
        "stats":    global_stats,
        "hourly":   hourly_summary,
        "borough":  borough_summary,
        "weekend":  weekend_summary,
        "top_zones":top_zones,
        "payment":  payment_summary,
        "fare":     fare_summary,
        "zones":    zone_counts,
    }


def write_to_db(conn: sqlite3.Connection, results: dict):
    print("Writing to database...")

    s = results["stats"]
    conn.execute("""
        INSERT INTO summary_stats
        (total_trips, total_revenue, avg_fare, avg_distance,
         avg_duration, avg_speed, busiest_hour, busiest_borough)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (s["total_trips"], s["total_revenue"], s["avg_fare"],
          s["avg_distance"], s["avg_duration"], s["avg_speed"],
          s["busiest_hour"], s["busiest_borough"]))
    print(f"  Stats: {s['total_trips']:,} trips | revenue ${s['total_revenue']:,.2f}")

    conn.executemany(
        "INSERT INTO summary_hourly (hour, trip_count, avg_fare, avg_duration, avg_speed) VALUES (?, ?, ?, ?, ?)",
        [(r["hour"], r["trip_count"], r["avg_fare"], r["avg_duration"], r["avg_speed"])
         for r in results["hourly"]]
    )
    print(f"  Hourly: {len(results['hourly'])} rows")

    conn.executemany(
        "INSERT INTO summary_borough (borough, total_trips, avg_fare, avg_distance, avg_duration, avg_tip_pct, avg_speed) VALUES (?, ?, ?, ?, ?, ?, ?)",
        [(r["borough"], r["total_trips"], r["avg_fare"], r["avg_distance"],
          r["avg_duration"], r["avg_tip_pct"], r["avg_speed"])
         for r in results["borough"]]
    )
    print(f"  Borough: {len(results['borough'])} rows")

    conn.executemany(
        "INSERT INTO summary_weekend_weekday (day_type, total_trips, avg_fare, avg_distance, avg_duration, avg_tip_pct, avg_speed) VALUES (?, ?, ?, ?, ?, ?, ?)",
        [(r["day_type"], r["total_trips"], r["avg_fare"], r["avg_distance"],
          r["avg_duration"], r["avg_tip_pct"], r["avg_speed"])
         for r in results["weekend"]]
    )
    print(f"  Weekend/Weekday: {len(results['weekend'])} rows")

    conn.executemany(
        "INSERT INTO summary_top_zones (rank, location_id, zone_name, borough, trip_count) VALUES (?, ?, ?, ?, ?)",
        [(r["rank"], r["location_id"], r["zone_name"], r["borough"], r["trip_count"])
         for r in results["top_zones"]]
    )
    print(f"  Top zones: {len(results['top_zones'])} rows")

    conn.executemany(
        "INSERT INTO summary_payment_breakdown (payment_type, label, trip_count, percentage) VALUES (?, ?, ?, ?)",
        [(r["payment_type"], r["label"], r["trip_count"], r["percentage"])
         for r in results["payment"]]
    )
    print(f"  Payment breakdown: {len(results['payment'])} rows")

    conn.executemany(
        "INSERT INTO summary_fare_distribution (fare_bucket, trip_count) VALUES (?, ?)",
        [(r["fare_bucket"], r["trip_count"]) for r in results["fare"]]
    )
    print(f"  Fare distribution: {len(results['fare'])} rows")

    conn.executemany(
        "INSERT INTO summary_zone_counts (location_id, trip_count) VALUES (?, ?)",
        [(r["location_id"], r["trip_count"]) for r in results["zones"]]
    )
    print(f"  Zone counts: {len(results['zones'])} rows")

    conn.commit()
    print("All summary tables written.")


def create_summary_tables(conn: sqlite3.Connection):
    print("Creating summary tables...")
    tables = [
        "summary_stats", "summary_hourly", "summary_borough",
        "summary_weekend_weekday", "summary_top_zones",
        "summary_payment_breakdown", "summary_fare_distribution",
        "summary_zone_counts",
    ]
    for table in tables:
        conn.execute(f"DROP TABLE IF EXISTS {table}")

    conn.execute("""
        CREATE TABLE summary_stats (
            total_trips     INTEGER,
            total_revenue   REAL,
            avg_fare        REAL,
            avg_distance    REAL,
            avg_duration    REAL,
            avg_speed       REAL,
            busiest_hour    INTEGER,
            busiest_borough TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE summary_hourly (
            hour         INTEGER PRIMARY KEY,
            trip_count   INTEGER,
            avg_fare     REAL,
            avg_duration REAL,
            avg_speed    REAL
        )
    """)
    conn.execute("""
        CREATE TABLE summary_borough (
            borough      TEXT PRIMARY KEY,
            total_trips  INTEGER,
            avg_fare     REAL,
            avg_distance REAL,
            avg_duration REAL,
            avg_tip_pct  REAL,
            avg_speed    REAL
        )
    """)
    conn.execute("""
        CREATE TABLE summary_weekend_weekday (
            day_type     TEXT PRIMARY KEY,
            total_trips  INTEGER,
            avg_fare     REAL,
            avg_distance REAL,
            avg_duration REAL,
            avg_tip_pct  REAL,
            avg_speed    REAL
        )
    """)
    conn.execute("""
        CREATE TABLE summary_top_zones (
            rank        INTEGER PRIMARY KEY,
            location_id INTEGER,
            zone_name   TEXT,
            borough     TEXT,
            trip_count  INTEGER
        )
    """)
    conn.execute("""
        CREATE TABLE summary_payment_breakdown (
            payment_type INTEGER PRIMARY KEY,
            label        TEXT,
            trip_count   INTEGER,
            percentage   REAL
        )
    """)
    conn.execute("""
        CREATE TABLE summary_fare_distribution (
            fare_bucket TEXT PRIMARY KEY,
            trip_count  INTEGER
        )
    """)
    conn.execute("""
        CREATE TABLE summary_zone_counts (
            location_id INTEGER PRIMARY KEY,
            trip_count  INTEGER
        )
    """)
    conn.commit()
    print("Summary tables created.")


def run_summaries():
    print("Urban Mobility - Summary Computation Pipeline")
    print("=" * 50)

    start = time.time()

    zone_df     = pd.read_csv(ZONE_LOOKUP_PATH)
    zone_lookup = {
        int(row["LocationID"]): {
            "zone_name": row["Zone"],
            "borough":   row["Borough"]
        }
        for _, row in zone_df.iterrows()
    }
    print(f"Zone lookup loaded: {len(zone_lookup)} zones")

    parquet_file    = pq.ParquetFile(CLEAN_PARQUET_PATH)
    batches         = list(parquet_file.iter_batches(batch_size=BATCH_SIZE))
    total_batches   = len(batches)
    partial_results = []

    print(f"Total batches: {total_batches}")
    print(f"Workers: {MAX_WORKERS}")
    print("Processing batches...")

    with multiprocessing.Pool(processes=MAX_WORKERS) as pool:
        for i, partial in enumerate(pool.imap(process_batch, batches), start=1):
            partial_results.append(partial)
            print(f"  Batch {i}/{total_batches} done")

    print("Combining partial results...")
    results = combine_partials(partial_results, zone_lookup)

    conn = open_connection()
    create_summary_tables(conn)
    write_to_db(conn, results)
    conn.close()

    elapsed    = time.time() - start
    mins, secs = divmod(int(elapsed), 60)
    print("=" * 50)
    print(f"Complete in {mins}m {secs}s")
    print("=" * 50)


if __name__ == "__main__":
    multiprocessing.freeze_support()
    run_summaries()