"""
Data Loader Module
Reads sensor CSV files and produces a unified event stream.
Each sensor file contains readings from a geographic cluster (north, south, east).
"""

import csv
import os
import glob

DATA_DIR = os.path.dirname(os.path.abspath(__file__))


def load_sensor_file(filepath):
    """Load a single sensor CSV file into a list of reading dicts."""
    readings = []
    source_name = os.path.basename(filepath).replace(".csv", "")
    with open(filepath, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            readings.append({
                "timestamp": int(row["timestamp"]),
                "zone_id": row["zone_id"],
                "sensor_id": row["sensor_id"],
                "reading_type": row["reading_type"],
                "value": float(row["value"]),
                "quality": float(row["quality"]),
                "source": source_name,
            })
    return readings


def load_all_readings():
    """Load readings from all sensor CSV files in the data directory."""
    all_readings = []
    pattern = os.path.join(DATA_DIR, "sensors_*.csv")
    for filepath in sorted(glob.glob(pattern)):
        readings = load_sensor_file(filepath)
        all_readings.extend(readings)
    # Sort by timestamp for temporal processing
    all_readings.sort(key=lambda r: r["timestamp"])
    return all_readings
