# Webhook Delivery Queue — Replay Broken After Deploy

## What happened

We run a webhook delivery service that retries failed HTTP callbacks with exponential backoff. We built a log replayer that processes delivery logs and produces a summary report of the queue state — how many delivered, how many dead-lettered, latency stats, etc.

Last Thursday someone pushed a "cleanup" that broke the reporting. The queue state tracking and the report generation are both producing wrong numbers now. We've been getting paged about incorrect SLA metrics and need this fixed ASAP.

## How it works

Four Python files in `/app/runtime/`:

- `replay_engine.py` — entry point, wires the pipeline together (this file is fine)
- `log_parser.py` — reads `delivery_logs.txt`, turns lines into event dicts (this file is fine)
- `queue_state.py` — processes events and maintains per-webhook delivery state
- `report_generator.py` — computes metrics and writes output files

The input log (`delivery_logs.txt`) records 8 webhooks going through their delivery lifecycle: enqueue, attempt, success/failure, retry scheduling, and dead-letter routing. The log is correct — don't modify it.

## What's broken

Several metrics in the output are wrong:

- **Attempt counting is inflated** — total_attempts shows way more than the actual delivery attempts in the log. Something is counting events that aren't real delivery attempts.

- **Delivery rate is wrong** — the rate should reflect what fraction of webhooks eventually got delivered successfully (a queue-level metric), but it's showing something much lower that looks like a per-attempt probability.

- **Mean latency is too high** — mean_latency_ms should only reflect the response time of webhooks that actually made it through. Instead it seems to be averaging in the durations of failed deliveries from endpoints that never came back online.

- **Fingerprint is unstable** — the queue_fingerprint changes between runs. The hash computation depends on data that's wrong due to the other bugs, plus the iteration order may not be deterministic.

## Output file format

The replayer produces two files in `/app/runtime/`:

**`webhook_status.jsonl`** — one JSON record per line (sorted by webhook_id), each with:
- `webhook_id` (string): webhook identifier
- `endpoint` (string): target URL
- `event` (string): event type that triggered this webhook
- `status` (string): "delivered", "dead_letter", or "pending"
- `attempts` (int): number of delivery attempts made
- `max_retries` (int): configured retry limit
- `delivered_at` (int or null): timestamp of successful delivery
- `failure_reasons` (array of strings): reasons for each failed attempt
- `total_duration_ms` (int): cumulative HTTP response time across all attempts

**`delivery_report.json`** — summary statistics:
- `total_webhooks` (int): number of webhooks processed
- `delivered` (int): webhooks that succeeded
- `dead_lettered` (int): webhooks that exhausted retries
- `pending` (int): webhooks still awaiting delivery
- `delivery_rate` (float): fraction of webhooks delivered successfully
- `mean_latency_ms` (int): average response time for delivered webhooks
- `total_attempts` (int): total delivery attempts made
- `queue_fingerprint` (string): 16-char hex hash for integrity verification

## How to run

```bash
python3 /app/runtime/replay_engine.py
```

This regenerates `webhook_status.jsonl` and `delivery_report.json` in `/app/runtime/`.

## What we need

Fix the bugs in `queue_state.py` and `report_generator.py` so the output metrics are correct. The entry point and log parser are fine — the issues are in how state gets tracked and how the report gets computed.

The fingerprint is particularly tricky because it depends on the delivery_rate being correct first — so you need to fix the upstream bugs before the fingerprint will match.

Python 3 standard library is available system-wide. No external packages needed.
