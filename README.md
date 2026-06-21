# NYC Urban Mobility Data Explorer

A full-stack web application analyzing NYC Yellow Taxi trip patterns using real-world data from the NYC Taxi & Limousine Commission (TLC). This project demonstrates data engineering, algorithm design, database management, API development, and frontend visualization skills.

**Video Walkthrough:** [Add YouTube link here]

**Team Participation Sheet:** https://docs.google.com/spreadsheets/d/1vuZ_eRbSjXdiTRSMfGrG0e3FUks0LY68ZRaSe1h4wl4/edit?gid=0#gid=0

**GitHub Repository:** https://github.com/ApongsehIyan23/Urban_Mobility_Data_Explorer

---

## Team — Execution Trio

| Name | Role |
|---|---|
| Apongseh Iyan Foghang | Data Pipeline & ETL |
| Henriette Iraguha | Database Design & Backend API |
| Luigi Birasa Ntore | Frontend Dashboard |

---

## Project Overview

This application processes the full year of 2025 NYC Yellow Taxi trip data — 34.5 million raw records across 12 months. After a 14-rule cleaning pipeline the data is inserted into a normalized SQLite database. A separate summary computation pipeline pre-aggregates all analytics into 8 small summary tables for instant API responses. A Flask REST API serves 10 endpoints to an interactive frontend dashboard built with Chart.js and Leaflet.js.

---

## Features

- **Full Year Data** — 12 months of 2025 NYC Yellow Taxi trips (34.5M raw records)
- **14-Rule Cleaning Pipeline** — transparent data validation with exclusion logging
- **6 Derived Features** — trip duration, speed, fare per mile, tip percentage, time of day, is weekend
- **Custom MinHeap Algorithm** — top K zone selection in O(n log k) without built-in sorting
- **Normalized SQLite Database** — 2 main tables with foreign keys and 6 indexes
- **Pre-computed Summary Tables** — 8 summary tables built from pandas for instant API responses
- **10 REST API Endpoints** — dynamic filtering by borough, hour, and time of day
- **Interactive Dashboard** — 3 themed sections with charts, map and data tables
- **Choropleth Map** — zone-level trip density visualization using Leaflet.js
- **Multiprocessing Pipeline** — parallel batch processing for fast data insertion and summary computation

---

## Project Structure

Urban_Mobility_Data_Explorer/

├── etl/

│   ├── data/

│   │   ├── raw/                      ← downloaded data files go here

│   │   ├── processed/                ← cleaned parquet output

│   │   └── logs/                     ← cleaning logs and exclusion reports

│   ├── src/

│   │   └── cleaner.py                ← 14-rule data cleaning pipeline

│   ├── download_trip_data.sh         ← downloads all data files

│   └── requirements.txt

├── scripts/

│   ├── data/

│   │   └── mobility.db               ← generated SQLite database

│   ├── database.py                   ← database schema and connection

│   ├── insertionDB.py                ← multiprocessing batch insertion

│   ├── compute_summaries.py          ← pre-computes 8 summary tables

│   ├── convert_geojs.py              ← shapefile to GeoJSON conversion

│   ├── urbanAPI.py                   ← Flask REST API with 10 endpoints

│   └── zone_rank.py                  ← custom MinHeap algorithm

├── frontend/

│   ├── index.html

│   ├── style.css

│   └── app.js

├── docs/

│   ├── architecture_diagram.png

│   └── Technical_Report.pdf

├── .gitignore

├── README.md


## Prerequisites

- Python 3.8+
- pip package manager
- Modern web browser
- Minimum 20GB free disk space
- Minimum 8GB RAM recommended

## Installation & Setup

### 1. Install Dependencies

```bash
pip install flask flask-cors pandas geopandas pyarrow
pip install -r etl/requirements.txt
```

### 2. Download Raw Data

```bash
cd etl
bash download_trip_data.sh
```

Downloads 12 monthly parquet files, taxi_zone_lookup.csv and taxi_zones.zip to `etl/data/raw/`

### 3. Clean the Data

```bash
time python -u src/cleaner.py 2>&1 | tee data/logs/cleaning_run.txt
```

Generates `etl/data/processed/yellow_2025_clean.parquet` — 34.5M clean records (~20-25 minutes)

### 4. Convert Shapefile to GeoJSON

```bash
cd etl/data/raw
unzip taxi_zones.zip
cd ../../..
python scripts/convert_geojs.py
```

Generates `etl/data/raw/taxi_zones.geojson`

### 5. Create Database and Insert Data

```bash
cd scripts
python insertionDB.py
```

Generates `scripts/data/mobility.db` (~1-2 hours for 34.5M rows)

### 6. Compute Summary Tables

```bash
python compute_summaries.py
```

Pre-computes 8 summary tables for instant API responses (~10-15 minutes)

### 7. Start Backend API

```bash
python urbanAPI.py
```

Server runs on http://localhost:5000

### 8. Open Frontend

```bash
cd ../frontend
python -m http.server 8000
```

Navigate to http://localhost:8000

## API Endpoints

- `GET /api/zones` — All 265 NYC taxi zones
- `GET /api/trips` — Filtered trip records (params: borough, hour, time_of_day, limit)
- `GET /api/stats/summary` — Overall summary statistics
- `GET /api/insights/hourly` — Trip counts and averages by hour
- `GET /api/insights/top-zones` — Top K pickup zones via MinHeap
- `GET /api/insights/borough-summary` — Aggregate statistics by borough
- `GET /api/insights/weekend-vs-weekday` — Weekend vs weekday comparison
- `GET /api/geojson` — GeoJSON with trip counts for map visualization
- `GET /api/insights/payment-breakdown` — Payment method breakdown
- `GET /api/insights/fare-distribution` — Fare amount distribution

## Data Cleaning Pipeline

14-rule pipeline applied across all 12 months:

1. Invalid passenger count (must be 1-4)
2. Out of range timestamps (must be within 2025)
3. Invalid trip duration (dropoff before pickup)
4. Invalid distance (must be > 0)
5. Distance outliers (> 150 miles)
6. Invalid fare amount
7. Fare outliers (> $500)
8. Invalid total amount
9. Negative financial fields
10. Invalid vendor ID
11. Invalid rate code ID
12. Invalid pickup location ID
13. Invalid dropoff location ID
14. Invalid payment type

**Results:** 48,722,602 raw records → 34,512,168 clean records (~70% retention)

## Derived Features

- `trip_duration_minutes` — Reveals congestion patterns
- `speed_mph` — Shows traffic behavior by time
- `fare_per_mile` — Reveals economic patterns
- `time_of_day` — Categorizes trips (Morning/Afternoon/Evening/Night)
- `tip_percentage` — Tipping behavior by borough
- `is_weekend` — Weekend vs weekday flag

## Database Design

**Normalized Schema:**
- `taxi_zones` — Dimension table with 265 location records
- `taxi_trips` — Fact table with 34.5M records and foreign keys to taxi_zones

**Indexes:** pickup_datetime, pu_location_id, do_location_id, time_of_day, is_weekend, payment_type

**Summary Tables:** summary_stats, summary_hourly, summary_borough, summary_weekend_weekday, summary_top_zones, summary_payment_breakdown, summary_fare_distribution, summary_zone_counts

## Technology Stack

**Backend:**
- Python 3.8+
- Flask — API server
- Pandas — data processing and summary computation
- GeoPandas — spatial data
- PyArrow — parquet file handling
- Multiprocessing — parallel batch processing
- SQLite — database
- Custom MinHeap algorithm (no built-in sorting)

**Frontend:**
- HTML5/CSS3
- Vanilla JavaScript
- Chart.js — visualizations
- Leaflet.js — maps

## Troubleshooting

**ModuleNotFoundError**
```bash
pip install flask flask-cors pandas geopandas pyarrow
```

**Database not found**
```bash
cd scripts
python insertionDB.py
python compute_summaries.py
```

**CORS errors**
- Ensure flask-cors is installed
- Backend must be running on port 5000

**Map not loading**
- Check that `etl/data/raw/taxi_zones.geojson` exists
- Run `python scripts/convert_geojs.py` if missing

**API endpoints returning errors**
- Make sure both `insertionDB.py` and `compute_summaries.py` completed successfully
- Restart Flask server

## Data Source

NYC Taxi & Limousine Commission (TLC)
https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page

## License

Educational project for academic purposes.