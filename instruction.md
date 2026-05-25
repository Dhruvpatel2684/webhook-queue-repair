# Geospatial Sensor Correlation Engine — Debugging Task

## Overview
A geospatial sensor correlation engine processes time-series readings from multiple sensor clusters, identifies cross-zone correlations (readings of the same type occurring close together in time across different zones), and produces summary reports with per-zone aggregation statistics.

## System Environment
- **Language**: Python 3.11
- **Runtime**: `/app/runtime/` (source modules, configuration, sensor data, output)
- **Global system-wide tooling**: `uv` and `pytest` are available
- **No external packages required** — stdlib only

## Processing Stages
1. **Data Loading** — Sensor CSV files (`sensors_north.csv`, `sensors_south.csv`, `sensors_east.csv`) are loaded and merged into a unified time-sorted reading stream. This stage is correct.

2. **Configuration** — `engine.ini` provides zone filtering and correlation parameters. The `[correlation.tuned]` section contains production-calibrated thresholds that should be used for scoring.

3. **Correlation Detection** — Readings of the same type from different zones within `max_time_gap` seconds are paired and scored. Correlation strength depends on temporal proximity and data quality. Results are sorted by strength descending, with ties broken by timestamp, then zone_id alphabetically.

4. **Zone Aggregation** — Readings are partitioned into fixed-size time windows (120 seconds). Each zone's final summary reflects only the most recent window snapshot (the last observation period for that zone). Types seen are accumulated across all windows.

5. **Report Generation** — Output files are written with correlation pairs and zone statistics. A digest hash verifies end-to-end integrity.

## Problem
The engine runs without errors but produces incorrect output:

- **Zone count is wrong** — Only 3 zones appear in the summary when 4 should be present. One zone's readings are being silently dropped during filtering.

- **Correlation count is too low** — The engine finds only 12 correlation pairs when significantly more should exist. The scoring threshold appears to be too restrictive.

- **Zone reading counts are inflated** — Per-zone `reading_count` values are much higher than expected for a single observation window. The aggregation seems to be combining data from multiple time periods.

- **Report digest is wrong** — The integrity hash doesn't match expected values because it depends on all the above metrics being correct.

## Expected Correct Output

### `/app/runtime/output/correlations.json`
Should contain 33 correlation pairs across all 4 active zones (zone_alpha, zone_beta, zone_gamma, zone_delta), with the strongest correlation at 93.5 strength.

### `/app/runtime/output/zone_summary.json`
Should show 4 zones, 54 total readings processed, 33 total correlations, and zone reading counts reflecting only the final time window (small counts of 1-2 per zone).

## Output Schema

### `/app/runtime/output/correlations.json`
| Field | Type | Description |
|-------|------|-------------|
| `correlation_count` | int | Total number of correlation pairs found |
| `pairs` | array | List of correlation pair objects |
| `pairs[].reading_type` | string | The shared reading type (temperature, humidity, pressure) |
| `pairs[].zone_a` | string | First zone in the pair (alphabetically first by zone_id when timestamps equal) |
| `pairs[].zone_b` | string | Second zone in the pair |
| `pairs[].sensor_a` | string | Sensor ID from zone_a |
| `pairs[].sensor_b` | string | Sensor ID from zone_b |
| `pairs[].timestamp_a` | int | Timestamp of reading from zone_a |
| `pairs[].timestamp_b` | int | Timestamp of reading from zone_b |
| `pairs[].time_delta` | int | Absolute time difference in seconds |
| `pairs[].strength` | float | Correlation strength score |
| `pairs[].source_a` | string | Source cluster name for zone_a reading |
| `pairs[].source_b` | string | Source cluster name for zone_b reading |

### `/app/runtime/output/zone_summary.json`
| Field | Type | Description |
|-------|------|-------------|
| `total_zones` | int | Number of zones in summary |
| `total_readings_processed` | int | Total sensor readings loaded |
| `total_correlations` | int | Number of correlation pairs found |
| `report_digest` | string | 16-char hex integrity hash |
| `zones` | array | Per-zone summary objects (sorted by zone_id) |
| `zones[].zone_id` | string | Zone identifier |
| `zones[].reading_count` | int | Readings in the most recent window for this zone |
| `zones[].mean_value` | float | Average reading value in the most recent window |
| `zones[].mean_quality` | float | Average quality score in the most recent window |
| `zones[].distinct_types` | int | Number of distinct reading types observed across all windows |

## Key Files
| File | Purpose |
|------|---------|
| `/app/runtime/run_correlation.py` | Entry point — orchestrates loading, correlation, aggregation, and output (correct) |
| `/app/runtime/data_loader.py` | Reads sensor CSVs into unified stream (correct) |
| `/app/runtime/correlation_engine.py` | Zone filtering, threshold loading, and cross-zone correlation detection |
| `/app/runtime/zone_aggregator.py` | Time-window partitioning and per-zone summary computation |
| `/app/runtime/report_writer.py` | Output file generation and digest computation (correct) |
| `/app/runtime/engine.ini` | Configuration with zone lists and threshold parameters |
| `/app/runtime/sensors_north.csv` | Sensor data from north cluster |
| `/app/runtime/sensors_south.csv` | Sensor data from south cluster |
| `/app/runtime/sensors_east.csv` | Sensor data from east cluster |

## Your Task
Identify and fix the defects in `/app/runtime/correlation_engine.py` and `/app/runtime/zone_aggregator.py`. The entry point, data loader, report writer, configuration file, and sensor data files are all correct and should not be modified.

After fixing the bugs, re-run the engine:
```bash
python3 -m runtime.run_correlation
```

The output files in `/app/runtime/output/` should then match the expected values described above.
