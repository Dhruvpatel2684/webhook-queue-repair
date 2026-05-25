# Webhook Delivery Queue — Dependency Replay Broken After Refactor

## What happened

We operate a webhook delivery service that guarantees causal ordering between related events. When an order goes through our system, we fire webhooks like `order.created`, `order.payment_captured`, `order.shipped`, etc. Some of these have hard dependencies — you can't notify a customer about shipment tracking until the shipment webhook itself has been delivered.

We built a replay analyzer that processes delivery logs and produces a dependency analysis report. The report tells us which webhooks can be safely retried in parallel (without violating ordering guarantees) and what priority ordering to use when scheduling delivery. The ops team uses this to plan batch replays after outages.

Two weeks ago we refactored the dependency graph module to "simplify" the independence checking and priority computation. Since then the parallel replay recommendations have been wrong — we scheduled a batch replay based on the tool's output and ended up delivering dependent webhooks out of order, causing data consistency issues downstream.

## Architecture

Four Python files in `/app/runtime/`:

- `log_parser.py` — reads `delivery_logs.txt`, produces structured event records (this file is correct)
- `queue_state.py` — builds the dependency graph and provides ordering analysis methods
- `report_generator.py` — uses the graph analysis to compute scheduling metrics and write output
- `replay_engine.py` — entry point that wires everything together (this file is correct)

The delivery log records 12 webhooks with their dependency declarations and delivery outcomes. The log is correct — do not modify it.

## What's broken

The dependency analysis is producing wrong results in several ways:

- **Independent pair count is inflated** — the report claims far more webhook pairs are safe for parallel delivery than actually are. The independence check is not accounting for all ordering constraints between webhooks.

- **Parallel replay set is wrong** — the recommended parallel batch contains webhooks that actually have ordering constraints between them. Replaying this set concurrently caused the out-of-order delivery incident. The set should only contain webhooks where truly no ordering relationship exists between any pair.

- **Priority ordering is off** — the scheduling priority doesn't properly reflect how critical each webhook is to the overall delivery pipeline. Webhooks that gate long chains of dependents should be prioritized higher, but the current ranking doesn't capture that.

- **Fingerprint mismatch** — the integrity fingerprint depends on the independence count and parallel set, so it's wrong as a consequence of the upstream bugs.

## Output file format

The replayer produces two files in `/app/runtime/`:

**`webhook_status.jsonl`** — one JSON record per line (sorted by webhook_id), each with:
- `webhook_id`, `endpoint`, `event`, `priority`, `status`, `attempts`, `delivered_at`, `failure_reasons`, `total_duration_ms`

**`delivery_report.json`** — dependency analysis and metrics:
- `total_webhooks` (int): number of webhooks in the system
- `delivered` (int): successfully delivered count
- `dead_lettered` (int): permanently failed count
- `pending` (int): still awaiting delivery
- `total_attempts` (int): total delivery attempts across all webhooks
- `total_edges` (int): number of dependency relationships declared
- `independent_pair_count` (int): pairs of webhooks with no ordering constraint
- `parallel_replay_set` (list): webhooks safe for concurrent replay
- `parallel_replay_size` (int): size of the parallel set
- `priority_order` (list): webhooks sorted by scheduling priority
- `scheduling_priorities` (dict): priority score for each webhook
- `ordering_violations` (int): causal violations in the observed delivery order
- `queue_fingerprint` (string): 16-char hex integrity hash

## How to run

```bash
python3 /app/runtime/replay_engine.py
```

This regenerates both output files in `/app/runtime/`.

## What we need

Fix the dependency analysis logic in `queue_state.py` so the independence checking, priority computation, and parallel set determination are all correct. The entry point and log parser are fine. The report generator just calls into the graph methods — if the underlying analysis is correct, the report will be correct.

The fingerprint depends on the independence count and parallel set being right, so you need to fix those first.

Standard library Python 3 only. No external packages needed.
