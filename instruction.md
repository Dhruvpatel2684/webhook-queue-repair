# Job Scheduler Engine — Debugging Task

## Overview
A priority-based job scheduler processes job manifests from multiple workload queues, applies scheduling policies with resource pool constraints, and produces execution plans with per-pool resource allocation reports. Jobs are assigned to scheduling rounds based on priority and concurrency limits.

## System Environment
- **Language**: Python 3.11
- **Runtime**: `/app/runtime/` (source modules, configuration, job manifests, output)
- **Global system-wide tooling**: `uv` and `pytest` are available
- **No external packages required** — stdlib only

## Processing Stages
1. **Job Loading** — Queue CSV files (`queue_batch.csv`, `queue_realtime.csv`, `queue_maintenance.csv`) are loaded and merged into a unified time-sorted job stream. This stage is correct.

2. **Configuration** — `scheduler.ini` provides resource pool validation and scheduling parameters. The `[scheduler.production]` section contains production-tuned concurrency limits that should be used for round sizing.

3. **Priority Scheduling** — Jobs are filtered to valid resource pools, then sorted by priority descending. Ties at the same priority and submission time are broken by queue_name alphabetically for deterministic scheduling. Jobs are assigned to rounds with at most max_concurrent jobs per round.

4. **Round Aggregation** — Scheduled jobs are grouped by round. Each pool's final summary reflects only the most recent round snapshot (the current allocation state). Queue diversity is tracked across all rounds.

5. **Report Generation** — Output files are written with job assignments and pool statistics. A digest hash verifies end-to-end integrity.

## Problem
The scheduler runs without errors but produces incorrect output:

- **Jobs are being rejected incorrectly** — 11 jobs targeting pool_network are rejected as invalid when they should be accepted. The pool appears to be missing from the valid set.

- **Too few scheduling rounds** — The scheduler produces only 3 rounds when more should be needed. The concurrency limit per round appears too high.

- **Pool job counts are inflated** — Per-pool `job_count` values are much higher than expected for a single scheduling round. The aggregation seems to be combining data from multiple rounds.

- **Schedule digest is wrong** — The integrity hash doesn't match expected values because it depends on all the above metrics being correct.

## Expected Correct Output

### `/app/runtime/output/schedule.json`
Should contain 54 scheduled jobs (0 rejected) across 7 scheduling rounds, with at most 8 jobs per round.

### `/app/runtime/output/pool_report.json`
Should show 4 pools, 54 scheduled, 0 rejected, and pool job counts reflecting only the final scheduling round (small counts of 1-2 per pool).

## Output Schema

### `/app/runtime/output/schedule.json`
| Field | Type | Description |
|-------|------|-------------|
| `total_scheduled` | int | Total number of jobs assigned to rounds |
| `total_rejected` | int | Jobs rejected due to invalid pool |
| `total_rounds` | int | Number of scheduling rounds produced |
| `assignments` | array | List of job assignment objects |
| `assignments[].job_id` | string | Job identifier |
| `assignments[].queue_name` | string | Source queue for the job |
| `assignments[].priority` | int | Job priority (higher = more urgent) |
| `assignments[].resource_pool` | string | Target resource pool |
| `assignments[].round` | int | Assigned scheduling round number |
| `rejected` | array | List of rejected job objects |
| `rejected[].job_id` | string | Job identifier |
| `rejected[].queue_name` | string | Source queue |
| `rejected[].resource_pool` | string | Invalid pool that caused rejection |
| `rejected[].reason` | string | Rejection reason |

### `/app/runtime/output/pool_report.json`
| Field | Type | Description |
|-------|------|-------------|
| `total_pools` | int | Number of resource pools in report |
| `total_scheduled` | int | Total jobs scheduled |
| `total_rejected` | int | Total jobs rejected |
| `schedule_digest` | string | 16-char hex integrity hash |
| `pools` | array | Per-pool summary objects (sorted by pool_id) |
| `pools[].pool_id` | string | Resource pool identifier |
| `pools[].job_count` | int | Jobs assigned to this pool in the most recent round |
| `pools[].avg_cpu` | float | Average CPU units per job in the most recent round |
| `pools[].avg_memory_mb` | float | Average memory per job in the most recent round |
| `pools[].avg_runtime_sec` | float | Average estimated runtime per job in the most recent round |
| `pools[].queue_diversity` | int | Number of distinct source queues across all rounds |

## Key Files
| File | Purpose |
|------|---------|
| `/app/runtime/run_scheduler.py` | Entry point — orchestrates loading, scheduling, aggregation, and output (correct) |
| `/app/runtime/job_loader.py` | Reads queue CSVs into unified stream (correct) |
| `/app/runtime/priority_scheduler.py` | Pool filtering, concurrency loading, and priority-based round assignment |
| `/app/runtime/round_aggregator.py` | Round grouping and per-pool summary computation |
| `/app/runtime/report_writer.py` | Output file generation and digest computation (correct) |
| `/app/runtime/scheduler.ini` | Configuration with pool lists and concurrency parameters |
| `/app/runtime/queue_batch.csv` | Batch analytics job manifests |
| `/app/runtime/queue_realtime.csv` | Realtime ingest job manifests |
| `/app/runtime/queue_maintenance.csv` | System maintenance job manifests |

## Your Task
Identify and fix the defects in `/app/runtime/priority_scheduler.py` and `/app/runtime/round_aggregator.py`. The entry point, job loader, report writer, configuration file, and queue data files are all correct and should not be modified.

After fixing the bugs, re-run the scheduler:
```bash
python3 -m runtime.run_scheduler
```

The output files in `/app/runtime/output/` should then match the expected values described above.
