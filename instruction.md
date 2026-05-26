# Packet Fragment Reassembly -- Debugging Task

## Overview
A network packet fragment reassembly engine processes captured fragments from multiple data streams, groups them into logical flows, validates integrity, and reconstructs complete packets.

## System Environment
- **Language**: Python 3.11
- **Runtime**: `/app/runtime/` (source modules, configuration, capture files, output)
- **Global system-wide tooling**: `uv` and `pytest` are available
- **No external packages required** -- stdlib only

## Key Files
| File | Purpose |
|------|---------|
| `/app/runtime/run_reassembly.py` | Entry point (correct) |
| `/app/runtime/capture_loader.py` | Loads capture JSONL files (correct) |
| `/app/runtime/flow_grouper.py` | Groups fragments into logical flows |
| `/app/runtime/fragment_sorter.py` | Orders fragments within each flow |
| `/app/runtime/checksum_validator.py` | Validates fragment integrity |
| `/app/runtime/reassembler.py` | Reassembles packets from ordered fragments |
| `/app/runtime/report_writer.py` | Writes output JSON files (correct) |
| `/app/runtime/reassembly.ini` | Reassembly configuration parameters |

## What's Wrong

The engine runs without errors but produces incorrect output:

- **Some flows have fragments in wrong order** -- for flows with many fragments, the ordering appears garbled in the middle. Shorter flows seem fine.

- **Checksum validation is rejecting valid fragments** -- fragments that should pass integrity checks are being flagged as corrupted when their payload data is correct.

- **Retransmitted fragments not handled correctly** -- when a fragment is retransmitted (same position, newer data), the reconstructed packet shows stale data from the original transmission.

- **Flow boundaries are wrong** -- some fragments that belong to separate logical flows are being grouped together, inflating per-flow fragment counts.

- **Completeness detection is unreliable** -- some flows are marked as complete when they shouldn't be, and the total reassembled byte count seems inflated.

## Output Schema

### `/app/runtime/output/reassembly_state.json`
| Field | Type | Description |
|-------|------|-------------|
| `flows` | object | Map of flow_id to reassembled flow data |
| `flows.<flow_id>.fragments_count` | int | Number of fragments in this flow |
| `flows.<flow_id>.reassembled_bytes` | int | Total bytes in reassembled packet |
| `flows.<flow_id>.status` | string | "complete", "incomplete", or "corrupted" |
| `flows.<flow_id>.payload_preview` | string | First 32 chars of reassembled payload |
| `total_flows` | int | Number of distinct flows |
| `total_fragments_processed` | int | Total fragments across all flows |
| `checksum_failures` | int | Fragments that failed integrity check |
| `state_digest` | string | 16-char hex integrity hash |

### `/app/runtime/output/reassembly_report.json`
| Field | Type | Description |
|-------|------|-------------|
| `complete_flows` | int | Flows successfully reassembled |
| `incomplete_flows` | int | Flows missing fragments |
| `corrupted_flows` | int | Flows with checksum failures |
| `retransmission_count` | int | Detected retransmitted fragments |
| `total_bytes_reassembled` | int | Sum of reassembled bytes across all flows |
| `flow_details` | array | Per-flow summary objects |
| `flow_details[].flow_id` | string | Flow identifier |
| `flow_details[].fragment_count` | int | Fragments in this flow |
| `flow_details[].status` | string | Flow completion status |
| `flow_details[].checksum_ok` | bool | Whether all fragments passed checksum |

## Your Task
Identify and fix the defects in the reassembly logic. The entry point, capture loader, report writer, configuration, and capture files are all correct and should not be modified.

After fixing, re-run:
```bash
python3 -m runtime.run_reassembly
```
