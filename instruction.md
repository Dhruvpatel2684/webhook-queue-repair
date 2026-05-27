# Cache Eviction Engine Repair

## Overview

Global system-wide tooling for multi-tier cache management. This engine evaluates cache entries across multiple storage tiers, computes eviction priority scores, and produces a deterministic eviction plan. The system processes access logs, filters entries by tier membership, scores each entry for eviction candidacy, and outputs structured JSON results for downstream cache controllers.

## System Architecture

The cache eviction engine consists of four coordinating modules:

### Analyzer (`/app/runtime/analyzer.py`)

The access log analyzer loads structured JSON access log files from the data directory. It validates each record against the expected schema, converts raw data into typed `CacheEntry` objects, and computes aggregate access cost metrics. Invalid records are logged and skipped without halting the overall process.

### Tier Filter (`/app/runtime/tier_filter.py`)

The tier filter determines which cache entries belong to active tiers as defined in the configuration. Entries associated with unrecognized or disabled tiers are excluded from eviction evaluation. The filter also enforces structural constraints: entries with expired TTLs or sizes exceeding the configured maximum are rejected.

### Evictor (`/app/runtime/evictor.py`)

The eviction engine computes a composite score for each cache entry and schedules eviction decisions. The scoring formula considers three factors:

- **Inverse access frequency**: Less frequently accessed entries receive higher scores
- **Size pressure**: Larger entries increase cache pressure and score higher
- **TTL discount**: Entries with more remaining time-to-live receive a small score reduction

Entries are processed in time windows. Each entry's score is compared against the configured eviction threshold to produce an "evict" or "retain" decision. The hit count for each entry is derived from its access frequency normalized by a factor of 10.

### Orchestrator (`/app/runtime/run_cache.py`)

The orchestrator coordinates the full workflow: loads configuration, initializes each module, passes data through the processing stages, and writes output files. It is responsible for deterministic ordering of the final eviction plan.

## Configuration

The engine reads its configuration from `/app/runtime/config.ini`, which contains multiple sections:

### `[cache]` Section

General cache settings including the list of active tiers, default TTL values, maximum entry sizes, and the evaluation mode.

### `[cache.policy]` Section

Eviction policy parameters. Use the cache.policy section for eviction constraints that govern threshold values and evaluation windows. This section defines:

- `eviction_threshold`: Score above which entries are marked for eviction
- `max_windows`: Maximum number of processing windows
- `time_budget`: Maximum processing time in seconds

### `[cache.logging]` Section

Logging configuration for the engine's diagnostic output.

## Input Data

Access log files are stored in `/app/runtime/data/` with the naming pattern `access_log_*.json`. Each file contains a JSON array of cache entry records.

### Entry Schema

Each record in the access log files must contain the following fields:

| Field | Type | Description |
|-------|------|-------------|
| `entry_key` | string | Unique identifier within the tier |
| `tier_name` | string | Cache tier where the entry resides |
| `access_frequency` | integer | Number of accesses in the observation window |
| `last_access_ts` | integer | Unix timestamp of most recent access |
| `size_bytes` | integer | Size of the cached object in bytes |
| `ttl_remaining` | integer | Seconds until natural expiration |
| `estimated_cost` | float | Cost to regenerate this entry |

### Data Files

- `/app/runtime/data/access_log_hot.json` - High-frequency access entries (20 entries)
- `/app/runtime/data/access_log_warm.json` - Moderate-frequency access entries (20 entries)
- `/app/runtime/data/access_log_cold.json` - Low-frequency and persistent entries (18 entries)

## Expected Output

The engine produces two output files in `/app/runtime/output/`:

### Eviction Plan (`/app/runtime/output/eviction_plan.json`)

A JSON array of eviction decisions, one per evaluated entry:

```json
{
  "entry_key": "cache-001",
  "tier_name": "l1",
  "eviction_score": 12.917,
  "time_window": 1,
  "hit_count": 20,
  "decision": "evict"
}
```

The eviction plan must be deterministically sorted. Entries with equal eviction_score are ordered by tier_name, then entry_key.

### Cache Report (`/app/runtime/output/cache_report.json`)

A JSON object containing summary statistics:

```json
{
  "total_entries": 58,
  "entries_evaluated": 58,
  "tiers_processed": ["l1", "l2", "l3", "persistent"],
  "total_windows": 3,
  "eviction_rate": 0.45,
  "entries_per_tier": {"l1": 15, "l2": 14, "l3": 16, "persistent": 4}
}
```

## Execution Constraints

- The engine must process all entries without crashing
- All configured tiers must be represented in the output
- Hit counts must accurately reflect normalized access frequency
- The eviction rate must fall within reasonable bounds for the configured threshold
- Output ordering must be fully deterministic across runs

## Running the Engine

Execute from the application root:

```bash
cd /app
python3 -m runtime.run_cache
```

The engine reads configuration from `/app/runtime/config.ini`, loads access logs from `/app/runtime/data/`, and writes results to `/app/runtime/output/`.

## Validation

The test suite validates engine output at three difficulty levels:

1. **Structural checks**: Output files exist with correct schemas
2. **Correctness checks**: Tier coverage, reasonable hit counts, proper eviction rates
3. **Comprehensive checks**: Full entry coverage, deterministic ordering, complete accuracy

Run validation:

```bash
cd /app
python3 -m runtime.run_cache
pytest /tests/test_cache.py -v
```

## Your Task

The cache eviction engine contains bugs that cause incorrect output. Your goal is to identify and fix the issues so that all validation tests pass. The engine runs without crashing, but produces results that fail the medium and hard test tiers.

Examine the configuration, data flow between modules, and output generation logic. Pay attention to how configuration values are read, how data is accumulated across processing passes, and how the final output is structured.

## File Reference

| File | Purpose |
|------|---------|
| `/app/runtime/config.ini` | Engine configuration |
| `/app/runtime/models.py` | Data model definitions |
| `/app/runtime/analyzer.py` | Access log loading and validation |
| `/app/runtime/tier_filter.py` | Tier membership filtering |
| `/app/runtime/evictor.py` | Eviction scoring and scheduling |
| `/app/runtime/run_cache.py` | Orchestrator and entry point |
| `/app/runtime/data/` | Input access log files |
| `/app/runtime/output/` | Generated output files |
| `/tests/test_cache.py` | Validation test suite |
