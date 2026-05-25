# WAL Replay Engine — Debugging Task

## Overview
A write-ahead log replay engine processes WAL segments from a database crash recovery scenario. It identifies committed transactions, reconstructs page state by replaying writes, and produces a recovery report.

## System Environment
- **Language**: Python 3.11
- **Runtime**: `/app/runtime/` (source modules, configuration, WAL segments, output)
- **Global system-wide tooling**: `uv` and `pytest` are available
- **No external packages required** — stdlib only

## Key Files
| File | Purpose |
|------|---------|
| `/app/runtime/run_recovery.py` | Entry point (correct) |
| `/app/runtime/wal_loader.py` | Loads WAL segment JSONL files (correct) |
| `/app/runtime/txn_tracker.py` | Tracks transaction states and committed set |
| `/app/runtime/page_reconstructor.py` | Reconstructs page state from write records |
| `/app/runtime/checkpoint_handler.py` | Determines replay boundary from checkpoint |
| `/app/runtime/recovery_writer.py` | Writes output JSON files (correct) |
| `/app/runtime/recovery.ini` | Recovery configuration parameters |

## What's Wrong

The engine runs without errors but produces incorrect recovery output:

- **Page contents are wrong** — some pages show stale data that doesn't match what the committed transactions wrote. The final state of several pages doesn't reflect the most recent committed write.

- **Wrong transactions included in replay** — the recovery seems to be replaying writes from transactions that should not be part of the recovery set. Some aborted transaction data appears in the recovered state.

- **Recovery boundary is off** — writes that should already be durable (from before the last checkpoint) are being unnecessarily re-applied, and the reported recovery LSN range seems incorrect.

## Output Schema

### `/app/runtime/output/recovered_state.json`
| Field | Type | Description |
|-------|------|-------------|
| `pages` | object | Map of page_id to recovered page content |
| `pages.<page_id>` | string | Final recovered value for this page |
| `committed_txns` | array | List of transaction IDs that were committed |
| `replayed_writes` | int | Number of write operations replayed |
| `recovery_lsn_start` | int | First LSN in the replay window |
| `recovery_lsn_end` | int | Last LSN replayed |
| `state_digest` | string | 16-char hex integrity hash |

### `/app/runtime/output/recovery_report.json`
| Field | Type | Description |
|-------|------|-------------|
| `total_records_processed` | int | Total WAL records read |
| `transactions` | object | Per-transaction outcome |
| `transactions.<txn_id>.status` | string | "committed", "aborted", or "in_progress" |
| `transactions.<txn_id>.write_count` | int | Number of writes by this transaction |
| `checkpoint_lsn` | int | LSN of the last checkpoint |
| `pages_recovered` | int | Number of distinct pages reconstructed |
| `high_conflict_pages` | array | Pages written by multiple transactions |

## Your Task
Identify and fix the defects in the recovery logic. The entry point, WAL loader, recovery writer, configuration file, and WAL segment files are all correct and should not be modified.

After fixing, re-run:
```bash
python3 -m runtime.run_recovery
```
