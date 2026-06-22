import json
import os
import sqlite3
from flask import Flask, jsonify, request
from flask_cors import CORS
from database import open_connection, UMD_PATH
from zone_rank import get_top_zones

app = Flask(__name__)
CORS(app, origins="*")

GEOJSON_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "etl", "data", "raw", "taxi_zones.geojson"
)

try:
    with open(GEOJSON_PATH, "r") as f:
        GEOJSON_CACHE = json.load(f)
except FileNotFoundError:
    GEOJSON_CACHE = None

def parse_int_param(value, name, default=None, min_val=None, max_val=None):
    if value is None:
        return default, None
    try:
        parsed = int(value)
        if min_val is not None and parsed < min_val:
            return None, (jsonify({"status": "error", "message": f"'{name}' must be >= {min_val}"}), 400)
        if max_val is not None and parsed > max_val:
            return None, (jsonify({"status": "error", "message": f"'{name}' must be <= {max_val}"}), 400)
        return parsed, None
    except ValueError:
        return None, (jsonify({"status": "error", "message": f"'{name}' must be a valid integer"}), 400)



@app.route("/api/zones", methods=["GET"])
def find_zones():
    conn   = open_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT location_id, borough, zone_name, service_zone
        FROM taxi_zones
        ORDER BY borough, zone_name
    """)
    zones = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({"status": "success", "count": len(zones), "data": zones})


@app.route("/api/trips", methods=["GET"])
def find_trips():
    borough     = request.args.get("borough")
    time_of_day = request.args.get("time_of_day")

    hour, err = parse_int_param(request.args.get("hour"), "hour", min_val=0, max_val=23)
    if err: return err

    limit, err = parse_int_param(request.args.get("limit"), "limit", default=50, min_val=1, max_val=200)
    if err: return err

    offset, err = parse_int_param(request.args.get("offset"), "offset", default=0, min_val=0)
    if err: return err

    query = """
        SELECT
            t.vendor_id, t.pickup_datetime, t.dropoff_datetime,
            t.passenger_count, t.trip_distance, t.fare_amount,
            t.tip_amount, t.total_amount, t.trip_duration_minutes,
            t.fare_per_mile, t.speed_mph, t.tip_percentage,
            t.time_of_day, t.is_weekend, t.payment_type,
            pu.borough AS pu_borough, pu.zone_name AS pu_zone,
            do.borough AS do_borough, do.zone_name AS do_zone
        FROM taxi_trips t
        JOIN taxi_zones pu ON t.pu_location_id = pu.location_id
        JOIN taxi_zones do ON t.do_location_id = do.location_id
    """
    params     = []
    conditions = []

    if borough:
        conditions.append("pu.borough = ?")
        params.append(borough)
    if hour is not None:
        conditions.append("CAST(strftime('%H', t.pickup_datetime) AS INTEGER) = ?")
        params.append(hour)
    if time_of_day:
        conditions.append("t.time_of_day = ?")
        params.append(time_of_day)
    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " LIMIT ? OFFSET ?"
    params.append(limit)
    params.append(offset)

    conn   = open_connection()
    cursor = conn.cursor()
    cursor.execute(query, params)
    trips  = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return jsonify({
        "status": "success",
        "count":  len(trips),
        "offset": offset,
        "limit":  limit,
        "data":   trips
    })



@app.route("/api/insights/hourly", methods=["GET"])
def find_hourly_insights():
    borough     = request.args.get("borough")
    time_of_day = request.args.get("time_of_day")

    if not borough and not time_of_day:
        conn   = open_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM summary_hourly ORDER BY hour")
        data = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return jsonify({"status": "success", "data": data})

    query = """
        SELECT
            CAST(strftime('%H', t.pickup_datetime) AS INTEGER) AS hour,
            COUNT(*)                             AS trip_count,
            ROUND(AVG(t.fare_amount), 2)         AS avg_fare,
            ROUND(AVG(t.trip_duration_minutes), 2) AS avg_duration,
            ROUND(AVG(t.speed_mph), 2)           AS avg_speed
        FROM taxi_trips t
        JOIN taxi_zones pu ON t.pu_location_id = pu.location_id
    """
    params     = []
    conditions = []

    if borough:
        conditions.append("pu.borough = ?")
        params.append(borough)
    if time_of_day:
        conditions.append("t.time_of_day = ?")
        params.append(time_of_day)
    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " GROUP BY hour ORDER BY hour"

    conn   = open_connection()
    cursor = conn.cursor()
    cursor.execute(query, params)
    data   = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({"status": "success", "data": data})


@app.route("/api/insights/top-zones", methods=["GET"])
def find_top_pickup_zones():
    conn   = open_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT rank, location_id, zone_name AS zone, borough, trip_count
        FROM summary_top_zones
        ORDER BY rank
    """)
    data = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({
        "status":    "success",
        "algorithm": "MinHeap O(n log k)",
        "count":     len(data),
        "data":      data
    })


@app.route("/api/insights/borough-summary", methods=["GET"])
def find_borough_summary():
    borough     = request.args.get("borough")
    time_of_day = request.args.get("time_of_day")

    hour, err = parse_int_param(request.args.get("hour"), "hour", min_val=0, max_val=23)
    if err: return err

    if not borough and not time_of_day and hour is None:
        conn   = open_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM summary_borough ORDER BY total_trips DESC")
        data = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return jsonify({"status": "success", "data": data})

    query = """
        SELECT
            pu.borough                              AS borough,
            COUNT(*)                                AS total_trips,
            ROUND(AVG(t.fare_amount), 2)            AS avg_fare,
            ROUND(AVG(t.trip_distance), 2)          AS avg_distance,
            ROUND(AVG(t.trip_duration_minutes), 2)  AS avg_duration,
            ROUND(AVG(t.tip_percentage), 2)         AS avg_tip_percentage,
            ROUND(AVG(t.speed_mph), 2)              AS avg_speed
        FROM taxi_trips t
        JOIN taxi_zones pu ON t.pu_location_id = pu.location_id
    """
    params     = []
    conditions = []

    if borough:
        conditions.append("pu.borough = ?")
        params.append(borough)
    if hour is not None:
        conditions.append("CAST(strftime('%H', t.pickup_datetime) AS INTEGER) = ?")
        params.append(hour)
    if time_of_day:
        conditions.append("t.time_of_day = ?")
        params.append(time_of_day)
    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " GROUP BY pu.borough ORDER BY total_trips DESC"

    conn   = open_connection()
    cursor = conn.cursor()
    cursor.execute(query, params)
    data   = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({"status": "success", "data": data})


@app.route("/api/geojson", methods=["GET"])
def find_geojson():
    if GEOJSON_CACHE is None:
        return jsonify({"error": "GeoJSON file not found"}), 404

    try:
        import copy

        conn   = open_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT location_id, trip_count FROM summary_zone_counts")
        trip_counts = {row["location_id"]: row["trip_count"] for row in cursor.fetchall()}
        conn.close()

        geojson = copy.deepcopy(GEOJSON_CACHE)
        for feature in geojson["features"]:
            location_id = feature["properties"].get("LocationID")
            feature["properties"]["trip_count"] = trip_counts.get(location_id, 0)

        return jsonify(geojson)

    except Exception as e:
        return jsonify({"error": str(e)}), 500




@app.route("/api/stats/summary", methods=["GET"])
def find_summary_stats():
    borough     = request.args.get("borough")
    time_of_day = request.args.get("time_of_day")

    hour, err = parse_int_param(request.args.get("hour"), "hour", min_val=0, max_val=23)
    if err: return err

    if not borough and not time_of_day and hour is None:
        conn   = open_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM summary_stats LIMIT 1")
        data = dict(cursor.fetchone())
        conn.close()
        return jsonify({"status": "success", "data": data})

    query = """
        SELECT
            COUNT(*)                               AS total_trips,
            ROUND(SUM(t.total_amount), 2)          AS total_revenue,
            ROUND(AVG(t.fare_amount), 2)           AS avg_fare,
            ROUND(AVG(t.trip_distance), 2)         AS avg_distance,
            ROUND(AVG(t.trip_duration_minutes), 2) AS avg_duration,
            ROUND(AVG(t.speed_mph), 2)             AS avg_speed
        FROM taxi_trips t
        JOIN taxi_zones pu ON t.pu_location_id = pu.location_id
    """
    params     = []
    conditions = []

    if borough:
        conditions.append("pu.borough = ?")
        params.append(borough)
    if hour is not None:
        conditions.append("CAST(strftime('%H', t.pickup_datetime) AS INTEGER) = ?")
        params.append(hour)
    if time_of_day:
        conditions.append("t.time_of_day = ?")
        params.append(time_of_day)
    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    conn   = open_connection()
    cursor = conn.cursor()
    cursor.execute(query, params)
    data = dict(cursor.fetchone())

    cursor.execute("""
        SELECT CAST(strftime('%H', t.pickup_datetime) AS INTEGER) AS hour,
               COUNT(*) AS trip_count
        FROM taxi_trips t
        JOIN taxi_zones pu ON t.pu_location_id = pu.location_id
        WHERE """ + " AND ".join(conditions) + """
        GROUP BY hour ORDER BY trip_count DESC LIMIT 1
    """, params) if conditions else cursor.execute("""
        SELECT CAST(strftime('%H', pickup_datetime) AS INTEGER) AS hour,
               COUNT(*) AS trip_count
        FROM taxi_trips
        GROUP BY hour ORDER BY trip_count DESC LIMIT 1
    """)
    data["busiest_hour"] = cursor.fetchone()["hour"]

    cursor.execute("""
        SELECT pu.borough, COUNT(*) AS trip_count
        FROM taxi_trips t
        JOIN taxi_zones pu ON t.pu_location_id = pu.location_id
        """ + ("WHERE " + " AND ".join(conditions) if conditions else "") + """
        GROUP BY pu.borough ORDER BY trip_count DESC LIMIT 1
    """, params)
    data["busiest_borough"] = cursor.fetchone()["borough"]

    conn.close()
    return jsonify({"status": "success", "data": data})



@app.route("/api/insights/weekend-vs-weekday", methods=["GET"])
def find_weekend_vs_weekday():
    conn   = open_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM summary_weekend_weekday")
    data = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({"status": "success", "data": data})



@app.route("/api/insights/payment-breakdown", methods=["GET"])
def find_payment_breakdown():
    conn   = open_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT payment_type, label, trip_count, percentage
        FROM summary_payment_breakdown
        ORDER BY trip_count DESC
    """)
    data = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({"status": "success", "data": data})



@app.route("/api/insights/fare-distribution", methods=["GET"])
def find_fare_distribution():
    conn   = open_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT fare_bucket, trip_count
        FROM summary_fare_distribution
        ORDER BY
            CASE fare_bucket
                WHEN '$0-$10'   THEN 1
                WHEN '$10-$20'  THEN 2
                WHEN '$20-$30'  THEN 3
                WHEN '$30-$40'  THEN 4
                WHEN '$40-$50'  THEN 5
                WHEN '$50-$75'  THEN 6
                WHEN '$75-$100' THEN 7
                ELSE 8
            END
    """)
    data = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({"status": "success", "data": data})



if __name__ == "__main__":
    app.run(debug=False, port=5000, threaded=True)