# CRDT Merge Engine - Debugging Task

## Overview
A merge engine processes operation logs from three distributed replicas (alpha, beta, gamma) and produces a converged state using CRDT semantics. It handles LWW (Last-Writer-Wins) registers and OR-set (Observed-Remove Set) data structures, plus generates a conflict report for high-contention keys.

## System Environment
- **Language**: Python 3.11
- **Runtime**: `/app/runtime/` (source modules, configuration, operation logs, output)
- **Global system-wide tooling**: `uv` and `pytest` are available
- **No external packages required** - stdlib only

## Key Files
| File | Purpose |
|------|---------|
| `/app/runtime/run_merge.py` | Entry point (correct) |
| `/app/runtime/op_loader.py` | Loads operation logs from JSONL files (correct) |
| `/app/runtime/lww_register.py` | Merges register operations using LWW semantics |
| `/app/runtime/orset_merger.py` | Merges set operations using OR-Set semantics |
| `/app/runtime/conflict_detector.py` | Identifies high-contention keys |
| `/app/runtime/state_writer.py` | Writes output JSON files (correct) |
| `/app/runtime/merge_config.ini` | Merge configuration parameters |

## What's Wrong

The engine runs without errors but the output is incorrect:

- **Register values are wrong for some keys** - for example, `user:1001:name` should resolve to a specific value but the merge picks the wrong winner in some cases. The issue appears related to how operations are compared during the merge.

- **Set element counts are incorrect** - some OR-sets have too few elements. Elements that should be present after the merge are missing, and elements that were removed still appear in some sets.

- **Conflict report has too many entries** - the conflict detector is flagging keys as high-conflict when they shouldn't be.

## Expected Output

When working correctly, the engine should produce:

- `/app/runtime/output/merged_state.json` - merged register values and set contents
- `/app/runtime/output/conflict_report.json` - high-contention key report

## Output Schema

### `/app/runtime/output/merged_state.json`
| Field | Type | Description |
|-------|------|-------------|
| `registers` | object | Map of key to register state |
| `registers.<key>.value` | string | The winning value for this register |
| `registers.<key>.timestamp` | string | Timestamp of the winning write |
| `registers.<key>.replica` | string | Replica that produced the winning write |
| `sets` | object | Map of key to set elements |
| `sets.<key>` | array | List of element objects in the set |
| `sets.<key>[].value` | string | Element value |
| `sets.<key>[].element_id` | string | Unique element tag |
| `state_digest` | string | 16-char hex integrity hash of merged state |
| `total_registers` | int | Count of register keys |
| `total_sets` | int | Count of set keys |

### `/app/runtime/output/conflict_report.json`
| Field | Type | Description |
|-------|------|-------------|
| `high_conflict_entries` | array | Keys exceeding the conflict threshold |
| `high_conflict_entries[].key` | string | The contended key |
| `high_conflict_entries[].write_count` | int | Number of distinct replicas that wrote |
| `high_conflict_entries[].replicas` | array | Sorted list of writing replicas |
| `high_conflict_entries[].severity` | string | Always "high" |
| `total_conflicts` | int | Count of high-conflict entries |

## Your Task
Identify and fix the defects in the merge logic. The entry point, operation loader, state writer, configuration file, and operation log files are all correct and should not be modified.

After fixing the bugs, re-run:
```bash
cd /app
python3 -m runtime.run_merge
```
