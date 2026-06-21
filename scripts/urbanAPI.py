import sqlite3
import json
import os
from flask import Flask, jsonify, request
from flask_cors import CORS
from zone_rank import get_top_zones

app = Flask(__name__)
CORS(app)

UMD_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "data", "mobility.db"
)

GEOJSON_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "etl", "data", "raw", "taxi_zones.geojson"
)


def open_db():
    conn = sqlite3.connect(UMD_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@app.route("/api/zones", methods=["GET"])
def find_zones():
    conn = open_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT location_id, borough, zone_name, service_zone
        FROM taxi_zones
        ORDER BY borough, zone_name
    """)
    zones = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({
        "status": "success",
        "count": len(zones),
        "data": zones
    })


@app.route("/api/trips", methods=["GET"])
def find_trips():
    borough     = request.args.get("borough")
    hour        = request.args.get("hour")
    time_of_day = request.args.get("time_of_day")
    limit       = request.args.get("limit", 500)

    query  = "SELECT * FROM taxi_trips WHERE id % 100 = 0"
    params = []

    if borough:
        query += " AND pu_borough = ?"
        params.append(borough)

    if hour:
        query += " AND CAST(strftime('%H', pickup_datetime) AS INTEGER) = ?"
        params.append(int(hour))

    if time_of_day:
        query += " AND time_of_day = ?"
        params.append(time_of_day)

    query += " LIMIT ?"
    params.append(int(limit))

    conn = open_db()
    cursor = conn.cursor()
    cursor.execute(query, params)
    trips = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return jsonify({
        "status": "success",
        "count": len(trips),
        "data": trips
    })


@app.route("/api/insights/hourly", methods=["GET"])
def find_hourly_insights():
    borough     = request.args.get("borough")
    time_of_day = request.args.get("time_of_day")

    query = """
        SELECT
            CAST(strftime('%H', pickup_datetime) AS INTEGER) AS hour,
            COUNT(*) * 10 AS trip_count,
            ROUND(AVG(fare_amount), 2) AS avg_fare,
            ROUND(AVG(trip_duration_minutes), 2) AS avg_duration
            ROUND(AVG(speed_mph), 2) AS avg_speed
        FROM taxi_trips
        WHERE id % 10 = 0
    """
    params = []

    if borough:
        query += " AND pu_borough = ?"
        params.append(borough)

    if time_of_day:
        query += " AND time_of_day = ?"
        params.append(time_of_day)

    query += " GROUP BY hour ORDER BY hour"

    conn = open_db()
    cursor = conn.cursor()
    cursor.execute(query, params)
    hourly = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return jsonify({
        "status": "success",
        "data": hourly
    })


@app.route("/api/insights/top-zones", methods=["GET"])
def find_top_pickup_zones():
    top_k = request.args.get("k", 15)
    top_zones = get_top_zones(k=int(top_k))
    return jsonify({
        "status": "success",
        "algorithm": "MinHeap O(n log k)",
        "count": len(top_zones),
        "data": top_zones
    })


@app.route("/api/insights/borough-summary", methods=["GET"])
def find_borough_summary():
    borough     = request.args.get("borough")
    hour        = request.args.get("hour")
    time_of_day = request.args.get("time_of_day")

    query = """
        SELECT
            pu_borough AS borough,
            COUNT(*) * 10 AS total_trips,
            ROUND(AVG(fare_amount), 2) AS avg_fare,
            ROUND(AVG(trip_distance), 2) AS avg_distance,
            ROUND(AVG(trip_duration_minutes), 2) AS avg_duration,
            ROUND(AVG(tip_percentage), 2) AS avg_tip_percentage,
            ROUND(AVG(speed_mph), 2) AS avg_speed
        FROM taxi_trips
        WHERE pu_borough IS NOT NULL
        AND id % 10 = 0
    """
    params = []

    if borough:
        query += " AND pu_borough = ?"
        params.append(borough)

    if hour:
        query += " AND CAST(strftime('%H', pickup_datetime) AS INTEGER) = ?"
        params.append(int(hour))

    if time_of_day:
        query += " AND time_of_day = ?"
        params.append(time_of_day)

    query += " GROUP BY pu_borough ORDER BY total_trips DESC"

    conn = open_db()
    cursor = conn.cursor()
    cursor.execute(query, params)
    summary = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return jsonify({
        "status": "success",
        "data": summary
    })


@app.route("/api/geojson", methods=["GET"])
def find_geojson():
    try:
        conn = open_db()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT pu_location_id AS location_id,
                   COUNT(*) * 10 AS trip_count
            FROM taxi_trips
            WHERE id % 10 = 0
            GROUP BY pu_location_id
        """)

        trip_counts = {}
        for row in cursor.fetchall():
            trip_counts[row["location_id"]] = row["trip_count"]
        conn.close()

        with open(GEOJSON_PATH, "r") as geo_file:
            geojson = json.load(geo_file)

        for feature in geojson["features"]:
            location_id = feature["properties"].get("LocationID")
            feature["properties"]["trip_count"] = trip_counts.get(location_id, 0)

        return jsonify(geojson)

    except FileNotFoundError:
        return jsonify({"error": "GeoJSON file not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/stats/summary", methods=["GET"])
def find_summary_stats():
    conn = open_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            COUNT(*) * 10 AS total_trips,
            ROUND(AVG(fare_amount), 2) AS avg_fare,
            ROUND(AVG(trip_distance), 2) AS avg_distance,
            ROUND(AVG(trip_duration_minutes), 2) AS avg_duration,
            ROUND(AVG(speed_mph), 2) AS avg_speed
        FROM taxi_trips
        WHERE id % 10 = 0
    """)

    stats = dict(cursor.fetchone())

    cursor.execute("""
        SELECT CAST(strftime('%H', pickup_datetime) AS INTEGER) AS hour,
               COUNT(*) AS trip_count
        FROM taxi_trips
        WHERE id % 10 = 0
        GROUP BY hour
        ORDER BY trip_count DESC
        LIMIT 1
    """)
    stats["busiest_hour"] = cursor.fetchone()["hour"]

    cursor.execute("""
        SELECT pu_borough AS borough, COUNT(*) AS trip_count
        FROM taxi_trips
        WHERE pu_borough IS NOT NULL
        AND id % 10 = 0
        GROUP BY pu_borough
        ORDER BY trip_count DESC
        LIMIT 1
    """)
    stats["busiest_borough"] = cursor.fetchone()["borough"]

    conn.close()

    return jsonify({
        "status": "success",
        "data": stats
    })


@app.route("/api/insights/weekend-vs-weekday", methods=["GET"])
def find_weekend_vs_weekday():
    conn = open_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            CASE is_weekend
                WHEN 1 THEN 'Weekend'
                ELSE 'Weekday'
            END AS day_type,
            COUNT(*) * 10 AS total_trips,
            ROUND(AVG(fare_amount), 2) AS avg_fare,
            ROUND(AVG(trip_distance), 2) AS avg_distance,
            ROUND(AVG(trip_duration_minutes), 2) AS avg_duration,
            ROUND(AVG(tip_percentage), 2) AS avg_tip_percentage,
            ROUND(AVG(speed_mph), 2) AS avg_speed
        FROM taxi_trips
        WHERE id % 10 = 0
        GROUP BY is_weekend
    """)

    comparison = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return jsonify({
        "status": "success",
        "data": comparison
    })


if __name__ == "__main__":
    app.run(debug=True, port=5000)