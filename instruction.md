# Multi-Tenant Rate Limiting Engine

## Overview

This system implements a multi-tenant rate limiting engine that processes API request logs, classifies them by service tier, applies token bucket throttling with sliding window tracking, and produces deterministic throttle plans and aggregate reports.

The engine is designed as Global system-wide tooling for managing request throughput across multiple service tiers with independent capacity enforcement per client.

## Architecture

The engine consists of six core modules operating in sequence:

1. **Ingester** (`/app/runtime/ingester.py`): Loads JSON request log files from `/app/runtime/data/`, validates entries, deduplicates by request ID, and produces structured `RequestEntry` objects.

2. **Classifier** (`/app/runtime/classifier.py`): Groups validated requests by their service tier based on the configured tier list. Only requests matching a configured tier are included in throttle evaluation.

3. **Throttler** (`/app/runtime/throttler.py`): Implements token bucket capacity enforcement with sliding window decay. Computes per-client token consumption within discrete time windows and issues allow/throttle decisions.

4. **Reporter** (`/app/runtime/reporter.py`): Generates aggregate metrics including throttle rate, per-tier request counts, and window coverage statistics.

5. **Models** (`/app/runtime/models.py`): Defines the data structures used across all modules including `RequestEntry`, `ThrottleDecision`, and `LimiterReport`.

6. **Utilities** (`/app/runtime/utils.py`): Provides shared helper functions for hashing, time window computation, burst factor calculation, and numeric formatting.

## Configuration

The engine reads its configuration from `/app/runtime/config.ini`. Key parameters:

- `service_tiers`: Comma-separated list of recognized tier names
- `bucket_capacity`: Maximum tokens available per client per window
- `refill_rate`: Tokens replenished per elapsed window
- `window_duration`: Duration of each discrete time window in seconds
- `evaluation_mode`: Controls filtering strictness (strict/lenient)
- `burst_allowance`: Multiplier threshold for burst detection
- `max_windows`: Maximum tracked window history

## Input Data

Request logs are stored as JSON arrays in `/app/runtime/data/`. Each entry contains:

| Field | Type | Description |
|-------|------|-------------|
| `client_id` | string | Unique client identifier |
| `service_tier` | string | Assigned service tier name |
| `timestamp` | float | Unix epoch timestamp in seconds |
| `payload_size` | int | Request payload size in bytes |
| `endpoint` | string | Target API endpoint path |
| `request_id` | string | Unique request identifier (UUID format) |

## Output Schema

### Throttle Plan (`/app/runtime/output/throttle_plan.json`)

A JSON array of throttle decision objects, sorted by throttle score, then service tier, then client identifier. Each entry:

```json
{
  "client_id": "string",
  "service_tier": "string",
  "throttle_score": 0.0,
  "time_window": 0,
  "tokens_used": 0,
  "decision": "allow|throttle"
}
```

The `throttle_score` represents capacity utilization as a ratio in [0.0, 1.0]. The `decision` field is "throttle" when cumulative token consumption meets or exceeds bucket capacity, otherwise "allow".

### Limiter Report (`/app/runtime/output/limiter_report.json`)

A JSON object containing aggregate metrics:

```json
{
  "total_requests": 0,
  "requests_classified": 0,
  "tiers_active": ["tier1", "tier2"],
  "total_windows": 0,
  "throttle_rate": 0.0,
  "requests_per_tier": {"tier": 0}
}
```

## Execution

Run the engine from `/app`:

```bash
python3 -m runtime.run_limiter
```

The entry point is `/app/runtime/run_limiter.py` which orchestrates all modules in sequence.

## Token Bucket Algorithm

The throttling algorithm combines a token bucket with sliding window tracking:

1. Each request consumes tokens based on payload size: `tokens = (payload_size + overhead) // 100 + 1`
2. Token consumption accumulates per client per time window
3. Burst detection applies a logarithmic multiplier when window density exceeds thresholds
4. Sliding window decay reduces relevance of aged consumption data
5. Refill credits are applied for elapsed windows between observations
6. The final decision compares total consumption against the effective bucket capacity

## Service Tiers

The system supports four service tiers:
- `basic`: Standard rate limits
- `standard`: Standard rate limits
- `premium`: Standard rate limits
- `enterprise`: Standard rate limits

All tiers currently share the same capacity multiplier. Tier differentiation is reflected in classification grouping and report segmentation.

## Validation

The test suite validates output correctness across three levels:
- Structural validation (file existence, field presence)
- Value correctness (capacity bounds, throttle rates)
- Comprehensive accuracy (sort ordering, complete classification, exact counts)
