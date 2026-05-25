# Webhook Delivery Queue — Production Metrics Incident

## Incident Summary

Our webhook delivery service processes retry-based HTTP callbacks with exponential backoff. On Monday, SRE flagged an anomaly in the delivery dashboard: success rates looked implausibly low, attempt counters didn't match what we see in the raw logs, and the queue integrity fingerprint was drifting between deploys.

We've traced the issue to the replay pipeline that reconstructs queue state from delivery logs. The pipeline consists of four Python modules — the log parser and replay engine are functioning correctly, but the state tracker and report generator are producing incorrect metrics.

## Architecture

Four files in `/app/runtime/`:

- `replay_engine.py` — orchestration layer, wires pipeline together (verified correct)
- `log_parser.py` — ingests `delivery_logs.txt` into event stream (verified correct)
- `queue_state.py` — maintains per-webhook state through the delivery lifecycle
- `report_generator.py` — computes aggregate metrics and writes output artifacts

The delivery log captures the full lifecycle of 8 webhooks: enqueue, attempt, success/failure, retry scheduling, and dead-letter routing. The log data is authoritative — do not modify it.

## Observed Symptoms

1. **Attempt counter divergence** — `total_attempts` in the report is significantly higher than the number of actual HTTP delivery attempts visible in the log. The counter appears to be accumulating events that aren't delivery attempts.

2. **Delivery rate suppressed** — The reported rate is far lower than what our endpoint monitoring shows. We know 5 out of 8 webhooks were delivered successfully, but the metric doesn't reflect that ratio.

3. **Latency skew** — `mean_latency_ms` is higher than expected. Dead-lettered endpoints that timed out repeatedly seem to be dragging the average up, even though latency should only reflect successful deliveries.

4. **Fingerprint instability** — `queue_fingerprint` doesn't match our reference value. This is likely downstream of the other metric errors since the fingerprint incorporates the delivery rate.

## Output Specification

The pipeline produces two files in `/app/runtime/`:

**`webhook_status.jsonl`** — one JSON record per line (sorted by webhook_id):
- `webhook_id`, `endpoint`, `event`, `status`, `attempts`, `max_retries`, `delivered_at`, `failure_reasons`, `total_duration_ms`

**`delivery_report.json`** — aggregate metrics:
- `total_webhooks` (int): webhooks processed
- `delivered` (int): successful deliveries
- `dead_lettered` (int): exhausted retries
- `pending` (int): still awaiting delivery
- `delivery_rate` (float): fraction of webhooks delivered successfully
- `mean_latency_ms` (int): average response time for delivered webhooks
- `total_attempts` (int): total delivery attempts made
- `queue_fingerprint` (string): 16-char hex integrity hash

## Execution

```bash
python3 /app/runtime/replay_engine.py
```

## Objective

Fix the bugs in `queue_state.py` and `report_generator.py` so all output metrics are correct. The replay engine and log parser are not broken.
