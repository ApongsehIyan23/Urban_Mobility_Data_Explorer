# Urban Mobility Data Explorer

A full-stack data engineering project that processes, stores, and visualises **33.8 million NYC Yellow Taxi trips (January – December 2025)**. The dashboard reveals how, when, where, and how much New York City moves through an interactive web interface backed by a Python ETL pipeline, a normalised SQLite database, and a Flask REST API.

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

## Project Structure

```
Urban_Mobility_Data_Explorer/
├── etl/
│   ├── data/
│   │   ├── raw/               ← downloaded data files go here
│   │   ├── processed/         ← cleaned parquet output
│   │   └── logs/              ← cleaning logs and exclusion reports
│   ├── src/
│   │   └── cleaner.py         ← 14-rule data cleaning pipeline
│   ├── download_trip_data.sh  ← downloads all 12 monthly parquet files
│   └── requirements.txt
├── scripts/
│   ├── data/
│   │   └── mobility.db        ← generated SQLite database (auto-created)
│   ├── database.py            ← 3NF schema definition and connection utilities
│   ├── insertionDB.py         ← multiprocessing batch insertion (1M rows/batch)
│   ├── compute_summaries.py   ← pre-computes 8 summary tables via MinHeap + pandas
│   ├── convert_geojs.py       ← converts shapefile to GeoJSON format
│   ├── urbanAPI.py            ← Flask REST API with 10 endpoints
│   └── zone_rank.py           ← custom MinHeap O(n log k) algorithm
├── frontend/
│   ├── index.html             ← single-page dashboard
│   ├── style.css              ← styling
│   └── app.js                 ← Chart.js + Leaflet.js visualisations
├── docs/
│   ├── architecture_diagram.png
│   └── Technical_Report.pdf
├── .gitignore
└── README.md
```

---

## Prerequisites

Before running the project, ensure you have the following installed:

- **Python 3.10 or higher**
- **Git**
- **Bash** (Git Bash on Windows, Terminal on macOS/Linux)
- **A modern web browser** (Chrome, Firefox, or Edge)
- **pip package manager**
- **Modern web browser**
- **Minimum 10GB free disk space**
- **Minimum 8GB RAM recommended**

Disk space required: approximately **8 GB** for raw parquet files, cleaned parquet, and the SQLite database.



---

## Installation and Setup

### 1. Clone the Repository

```bash
git clone https://github.com/ApongsehIyan23/Urban_Mobility_Data_Explorer.git
cd Urban_Mobility_Data_Explorer
```

### 2. Create and Activate a Virtual Environment

**Windows (Git Bash):**
```bash
python -m venv venv
source venv/Scripts/activate
```

**macOS / Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r etl/requirements.txt
```

---

## Running the Pipeline

Run each step in order. Each step must complete successfully before moving to the next.

### Step 1 — Download the Raw Data

```bash
bash etl/download_trip_data.sh
```

This downloads all 12 monthly NYC TLC Yellow Taxi parquet files for 2025 and the taxi zone lookup CSV into `etl/data/raw/`. The script includes disk space checks and resume capability.

**Expected output:** 12 parquet files and `taxi_zone_lookup.csv` in `etl/data/raw/`

### Step 2 — Convert GeoJSON

```bash
python scripts/convert_geojs.py
```

Converts the taxi zones shapefile to GeoJSON format for use by the Leaflet.js choropleth map.

**Expected output:** `taxi_zones.geojson` in `etl/data/raw/`

### Step 3 — Run the ETL Pipeline

```bash
PYTHONIOENCODING=utf-8 python -u etl/src/cleaner.py
```

Applies 14 cleaning rules to all 12 monthly parquet files in parallel using multiprocessing. Generates derived features (`trip_duration_minutes`, `fare_per_mile`, `time_of_day`, `speed_mph`, `tip_percentage`, `is_weekend`).

**Expected output:**
- `etl/data/processed/yellow_2025_clean.parquet` (~1.6 GB, ~33.8 million rows)
- `etl/data/logs/yellow_2025_exclusions.parquet`
- `etl/data/logs/cleaning_summary.txt`

**Expected runtime:** approximately 3 minutes

### Step 4 — Create the Database and Insert Data

```bash
python scripts/insertionDB.py
```

Creates the 3NF SQLite database schema and loads all 33.8 million cleaned trip records using multiprocessing with 1-million-row batches. Builds 6 indexes after insertion.

**Expected output:** `scripts/data/mobility.db`

**Expected runtime:** approximately 20 minutes

### Step 5 — Pre-compute Summary Tables

```bash
python scripts/compute_summaries.py
```

Reads the cleaned parquet file in parallel batches, computes all aggregations using Python and the custom MinHeap algorithm, and writes 8 summary tables to the database. These tables power instant API responses.

**Expected output:** 8 summary tables written to `mobility.db` (~326 rows total)

**Expected runtime:** approximately 2 minutes

---

## Running the Application

### Start the Flask API

Open a terminal and run:

```bash
python scripts/urbanAPI.py
```

The API will start on `http://localhost:5000`. Keep this terminal open while using the dashboard.

To verify the API is running, open your browser and go to:
```
http://localhost:5000/api/stats/summary
```

You should see a JSON response with total trips, revenue, and other summary statistics.

### Open the Frontend Dashboard

In a second terminal (with the virtual environment activated), run:

```bash
start frontend/index.html
```

**macOS / Linux:**
```bash
open frontend/index.html
```

Or simply open `frontend/index.html` directly in your web browser.

**Note:** The API must be running before opening the dashboard.

---

## API Endpoints

The Flask API runs on `http://localhost:5000` and exposes 10 endpoints:

| Endpoint | Description | Filters |
|----------|-------------|---------|
| `GET /api/zones` | All 265 taxi zones | — |
| `GET /api/trips` | Paginated trip records | `borough`, `time_of_day`, `hour`, `limit`, `offset` |
| `GET /api/stats/summary` | Overall KPI statistics | `borough`, `time_of_day`, `hour` |
| `GET /api/insights/hourly` | Trip volume by hour (0–23) | `borough`, `time_of_day` |
| `GET /api/insights/borough-summary` | Stats per borough | `borough`, `time_of_day`, `hour` |
| `GET /api/insights/top-zones` | Top 15 busiest pickup zones (MinHeap) | `borough`, `time_of_day` |
| `GET /api/insights/weekend-vs-weekday` | Weekday vs weekend comparison | `borough`, `time_of_day` |
| `GET /api/insights/payment-breakdown` | Payment method distribution | `borough`, `time_of_day` |
| `GET /api/insights/fare-distribution` | Fare range histogram | `borough`, `time_of_day` |
| `GET /api/geojson` | GeoJSON with trip counts per zone | `borough`, `time_of_day` |

All filtered endpoints follow a dual-path pattern: no filters → instant pre-computed summary tables; filters applied → live query on the cleaned dataset.

---

## Dashboard Features

- **Sticky KPI strip** — total trips, revenue, avg fare, avg duration, avg speed, peak hour, top borough
- **Global filter bar** — filter all visuals by borough and time of day with a single Apply Filters click
- **Hourly line chart** — trip volume and average speed across 24 hours
- **Radar chart** — weekday vs weekend comparison across 5 metrics
- **Choropleth map** — Leaflet.js interactive map with trip density per zone
- **Polar area chart** — top 15 busiest pickup zones (powered by MinHeap algorithm)
- **Borough doughnut** — trip share across the five boroughs
- **Fare histogram** — distribution of fares across 8 price ranges
- **Payment doughnut** — credit card vs cash breakdown
- **Explore section** — paginated trip records table with sorting and real-time API filters

---

## Algorithm — MinHeap O(n log k)

The top 15 busiest pickup zones are identified using a **custom MinHeap** implemented in `zone_rank.py` — no built-in `heapq`, `sort_values`, or library functions used. The algorithm runs during `compute_summaries.py` to pre-compute `summary_top_zones` and again at query time when borough or time-of-day filters are applied.

**Time complexity:** O(n log k) where n = 263 zones, k = 15  
**Space complexity:** O(k) — only 15 items held in memory at any time

---

## Key Data Facts

- **Raw trips downloaded:** 48,722,602
- **Clean trips retained:** 33,858,070 (69.5% retention rate)
- **Total revenue (2025):** $983,484,978.67
- **Peak hour:** 18:00 (6 PM)
- **Dominant borough:** Manhattan (89% of all pickups)
- **Most common fare range:** $10–$20 (43.7% of trips)
- **Credit card payments:** 87.61%

---

## Troubleshooting

**API returns 500 errors:**  
Ensure `compute_summaries.py` has been run and the summary tables exist in `mobility.db`.

**Map not loading:**  
Verify `taxi_zones.geojson` exists in `etl/data/raw/`. Run `convert_geojs.py` if missing.

**Charts show no data:**  
Confirm the Flask API is running on port 5000 before opening the frontend.

**Windows encoding errors during ETL:**  
Prefix commands with `PYTHONIOENCODING=utf-8`.

**Slow filtered queries:**  
Filtered queries run on live data. Manhattan (89% of trips) will be slowest. Brooklyn, Queens, and Bronx filters are significantly faster.