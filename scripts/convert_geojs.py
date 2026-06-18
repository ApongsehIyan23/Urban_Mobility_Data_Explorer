"""
Converts taxi_zones shapefile to GeoJSON for use with Leaflet.js map.
Run this once after downloading the data files.
"""
import geopandas as gpd
import os

SHAPEFILE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "etl", "data", "raw", "taxi_zones", "taxi_zones.shp"
)

GEOJSON_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "etl", "data", "raw", "taxi_zones.geojson"
)

def convert():
    print("Converting shapefile to GeoJSON...")
    zones = gpd.read_file(SHAPEFILE_PATH)
    zones = zones.to_crs("EPSG:4326")
    zones.to_file(GEOJSON_PATH, driver="GeoJSON")
    print(f"Done. Saved to {GEOJSON_PATH}")


if __name__ == "__main__":
    convert()