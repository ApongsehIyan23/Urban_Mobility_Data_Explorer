# NYC  Urban Mobility Data Explorer
A full-stack web application analyzing NYC Yellow Taxi trip patterns using real-world data from the NYC 
Taxi & Limousine Commission (TLC). This project demonstrates data engineering, algorithm design, database management, API development, and frontend visualization skills.

**Video Walkthrough:** [Add YouTube link here]

**Team Participation Sheet:** (https://docs.google.com/spreadsheets/d/1vuZ_eRbSjXdiTRSMfGrG0e3FUks0LY68ZRaSe1h4wl4/edit?gid=0#gid=0)

**GitHub Repository:** https://github.com/ApongsehIyan23/Urban_Mobility_Data_Explorer

---

## Team — Execution Trio

| Name |  Role |
|---|---|---|
| Apongseh Iyan Foghang | Data Pipeline & ETL |
| Henriette Iraguha | Database Design & Backend API |
| Luigi Birasa Ntore | Frontend Dashboard |

---

## Project Overview

This application processes the full year of 2025 NYC Yellow Taxi trip data — 34.5 million raw records across 12 months. After a 14-rule cleaning pipeline the data is sampled and stored in a normalized SQLite database. A Flask REST API serves 8 endpoints to an interactive frontend dashboard built with Chart.js and Leaflet.js.

---

## Features

- **Full Year Data** — 12 months of 2025 NYC Yellow Taxi trips (34.5M raw records)
- **14-Rule Cleaning Pipeline** — transparent data validation with exclusion logging
- **6 Derived Features** — trip duration, speed, fare per mile, tip percentage, time of day, is weekend
- **Custom MinHeap Algorithm** — top K zone selection in O(n log k) without built-in sorting
- **Normalized SQLite Database** — 2 tables with foreign keys and 6 indexes
- **8 REST API Endpoints** — dynamic filtering by borough, hour, and time of day
- **Interactive Dashboard** — 3 themed sections with charts, map and data tables
- **Choropleth Map** — zone-level trip density visualization using Leaflet.js
- **Statistical Sampling** — DuckDB-powered 20% sample for fast API responses

---

## Project Structure
Urban_Mobility_Data_Explorer/

├── etl/

│   ├── data/

│   │   ├── raw/                         ← downloaded data files go here

│   │   ├── processed/                   ← cleaned parquet output

│   │   └── logs/                        ← cleaning logs and exclusion reports

│   ├── src/

│   │   └── cleaner.py                   ← 14-rule data cleaning pipeline

│   ├── download_trip_data.sh            ← downloads all data files

│   └── requirements.txt

├── scripts/

│   ├── data/

│   │   └── mobility.db                  ← generated SQLite database

│   ├── database.py                      ← database schema and connection

│   ├── insertionDB.py                   ← batch data insertion pipeline

│   ├── sample_data.py                   ← DuckDB  sampling script

│   ├── convert_geojs.py                 ← shapefile to GeoJSON conversion

│   ├── urbanAPI.py                      ← Flask REST API with 8 endpoints

│   └── zone_rank.py                     ← custom MinHeap algorithm

├── frontend/

│   ├── index.html                       ← dashboard structure

│   ├── style.css                        ← styling and responsive layout

│   └── app.js                           ← chart and map logic

├── docs/

│   ├── architecture_diagram.png         ← system architecture diagram

│   └── Technical_Report.pdf            ← technical documentation

├── .gitignore

├── README.md

├── AI_usage_log.md

└── VIDEO_SCRIPT.md

---

## Prerequisites

- Python 3.8+
- pip package manager
- Modern web browser
- Git Bash (Windows) or Terminal (Mac/Linux)
- Minimum 20GB free disk space
- Minimum 8GB RAM

---

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/ApongsehIyan23/Urban_Mobility_Data_Explorer.git
cd Urban_Mobility_Data_Explorer
```

### 2. Install Backend Dependencies

```bash
pip install flask flask-cors pandas geopandas pyarrow duckdb
```

### 3. Install ETL Dependencies

```bash
pip install -r etl/requirements.txt
```

---

## Data Setup

Large data files are NOT included in this repository. Follow these steps to download and process the data.

### Step 1 — Download Raw Data

```bash
cd etl
bash download_trip_data.sh
```
This downloads:
- 12 monthly NYC Yellow Taxi parquet files (2025)
- taxi_zone_lookup.csv
- taxi_zones.zip

Files are saved to `etl/data/raw/`. Total download size is approximately 8GB.

### Step 2 — Run Data Cleaning Pipeline

```bash
time python -u src/cleaner.py 2>&1 | tee data/logs/cleaning_run.txt
```

This takes approximately 3-5 minutes and processes all 12 months. Output:
- `etl/data/processed/yellow_2025_clean.parquet` — 34.5M clean records
- `etl/data/logs/cleaning_summary.txt` — cleaning statistics
- `etl/data/logs/exclusions_2025_all.csv` — all excluded records with reasons

### Step 3 — Extract and Convert Zone Shapefile

```bash
cd etl/data/raw
unzip taxi_zones.zip
cd ../../..
python scripts/convert_geojs.py
```

Generates `etl/data/raw/taxi_zones.geojson` for the map visualization.

### Step 4 — Create Data Sample

```bash
cd scripts
python sample_data.py
```

Creates a 20% statistical sample — approximately 6.9 million records saved to `scripts/data/sampled_trips.parquet`. This sample preserves the statistical distribution of the full dataset while ensuring fast API responses.

### Step 5 — Create Database and Insert Data

```bash
python insertionDB.py
```

This takes approximately 15-20 minutes and:
- Creates `scripts/data/mobility.db`
- Inserts all 265 taxi zones
- Inserts 6.9 million trip records in batches of 500,000
- Computes 3 additional derived features per batch
- Optimizes the database with ANALYZE

---

## Running the Application

### Step 1 — Start the Backend API

Open a terminal and run:

```bash
cd scripts
python urbanAPI.py
```

The API runs on `http://localhost:5000`

### Step 2 — Start the Frontend

Open a second terminal and run:

```bash
cd frontend
python -m http.server 8000
```

Open your browser and go to:
http://localhost:8000

---

## API Endpoints

| Endpoint | Method | Description | Parameters |
|---|---|---|---|
| `/api/zones` | GET | All 265 NYC taxi zones | — |
| `/api/trips` | GET | Filtered trip records | borough, hour, time_of_day, limit |
| `/api/stats/summary` | GET | Overall dashboard statistics | — |
| `/api/insights/hourly` | GET | Trip counts and fares by hour | borough, time_of_day |
| `/api/insights/top-zones` | GET | Top K busiest pickup zones via MinHeap | k |
| `/api/insights/borough-summary` | GET | Aggregate stats per borough | borough, hour, time_of_day |
| `/api/insights/weekend-vs-weekday` | GET | Weekend vs weekday comparison | — |
| `/api/geojson` | GET | GeoJSON with trip counts for map | — |

All endpoints return data in this format:
```json
{
  "status": "success",
  "data": [...]
}
```

---

## Data Cleaning Pipeline

The cleaning pipeline applies 14 validation rules across all 12 months:

1. Invalid passenger count (must be 1-4)
2. Out of range timestamps (must be within 2025)
3. Invalid trip duration (dropoff must be after pickup)
4. Invalid distance (must be > 0)
5. Distance outliers (must be ≤ 150 miles)
6. Invalid fare amount (must be > 0 for paid trips)
7. Fare outliers (must be ≤ $500)
8. Invalid total amount
9. Negative financial fields (extra, tax, surcharges)
10. Invalid vendor ID
11. Invalid rate code ID
12. Invalid pickup location ID
13. Invalid dropoff location ID
14. Invalid payment type

**Results:**
- Raw records: 48,722,602
- Clean records: 34,512,168
- Overall retention: ~70%

---

## Derived Features

| Feature | Formula | Insight |
|---|---|---|
| trip_duration_minutes | dropoff - pickup in minutes | Reveals congestion patterns |
| fare_per_mile | fare_amount / trip_distance | Reveals economic patterns |
| time_of_day | based on pickup hour | Morning/Afternoon/Evening/Night |
| speed_mph | distance / (duration / 60) | Shows traffic behavior by time |
| tip_percentage | tip_amount / fare_amount × 100 | Tipping behavior by borough |
| is_weekend | 1 if Saturday or Sunday | Weekend vs weekday patterns |

---

## Database Design

**Normalized Schema:**
taxi_zones (265 rows)              taxi_trips (6.9M rows)

─────────────────────              ──────────────────────

location_id (PK)      ←────────── pickup_location_id (FK)

borough                            dropoff_location_id (FK)

zone_name                          vendor_id

service_zone                       pickup_datetime

dropoff_datetime

passenger_count

trip_distance

fare_amount

tip_amount

total_amount

trip_duration_minutes

fare_per_mile

speed_mph

tip_percentage

time_of_day

is_weekend

**Indexes:**
- `idx_trips_pickup_datetime` — time-based filtering
- `idx_trips_pickup_location` — pickup zone filtering
- `idx_trips_dropoff_location` — dropoff zone filtering
- `idx_trips_time_of_day` — time of day grouping
- `idx_trips_is_weekend` — weekend vs weekday comparison
- `idx_trips_pickup_borough` — borough aggregations

---

## Algorithm — Custom MinHeap

The `/api/insights/top-zones` endpoint uses a custom MinHeap implementation to find the top K busiest pickup zones without any built-in sorting functions.

- **No heapq, no sorted(), no sort_values()**
- **Time complexity:** O(n log k) where n = 263 zones, k = top zones requested
- **Space complexity:** O(k) — only K items stored in memory at once
- **2x faster** than SQL ORDER BY for top-K selection

---

## Technology Stack

**Backend:**
- Python 3.8+
- Flask — REST API server
- pandas — data processing
- geopandas — spatial data conversion
- pyarrow — parquet file handling
- DuckDB — fast statistical sampling
- SQLite — database

**Frontend:**
- HTML5 / CSS3
- Vanilla JavaScript
- Chart.js — data visualizations
- Leaflet.js — interactive map

---

## Troubleshooting

**ModuleNotFoundError:**
```bash
pip install flask flask-cors pandas geopandas pyarrow duckdb
```

**Database not found:**
```bash
cd scripts
python insertionDB.py
```

**GeoJSON file not found:**
```bash
cd etl/data/raw
unzip taxi_zones.zip
cd ../../..
python scripts/convert_zones.py
```

**CORS errors:**
- Make sure Flask is running on port 5000
- Make sure flask-cors is installed

**API endpoints slow:**
- Make sure you ran `sample_data.py` before `insertionDB.py`
- Database should have ~6.9 million rows not 34 million

**Map not loading:**
- Check that `etl/data/raw/taxi_zones.geojson` exists
- Run `python scripts/convert_zones.py` if missing

---

## Data Source

NYC Taxi and Limousine Commission (TLC)
https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page

