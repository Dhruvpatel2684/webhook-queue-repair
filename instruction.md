# CQRS Event Projection System Repair

## Overview

You are given a CQRS (Command Query Responsibility Segregation) event projection system that reads event streams from JSONL files, processes them through a series of stages, and builds materialized views as JSON output files.

The system is currently producing incorrect results. Your task is to identify and fix the bugs causing the projection output to be inaccurate.

## System Architecture

The projection system consists of several cooperating modules:

- **Event Loading**: Reads events from multiple JSONL stream files in `/app/runtime/data/streams/`
- **Window Processing**: Segments events into overlapping sliding windows based on sequence numbers
- **Deduplication**: Removes duplicate events using hash-based identification
- **Projection Building**: Applies configured rules to aggregate event data into materialized views
- **Output Writing**: Produces JSON files with the computed projections and processing metadata

## Configuration

The system is configured through two files:

- `/app/runtime/config/engine.ini` - Processing parameters (window size, overlap, dedup settings)
- `/app/runtime/config/projections.yaml` - Projection rules defining how events map to views

## Input Format

Each event stream is a JSONL file where each line is a JSON object with:
- `stream_id`: Identifier for the event stream
- `seq`: Sequence number (integer, monotonically increasing within a stream)
- `timestamp`: ISO 8601 timestamp with timezone offset
- `version`: Event schema version (integer)
- `event_type`: The type of domain event
- `payload`: Dictionary containing event-specific data fields

## Output Schema

The system produces two files in `/app/runtime/output/`:

### projections.json

A JSON object where keys are `"view_key:field_name"` and values contain:
```json
{
  "view_key": "string",
  "field": "string",
  "value": 0.0,
  "merge_mode": "sum|max|last_write|min|count",
  "priority": 0,
  "source_stream": "string",
  "source_event_type": "string",
  "last_updated_seq": 0,
  "update_count": 0
}
```

### metadata.json

Processing statistics:
```json
{
  "total_events_loaded": 0,
  "events_after_dedup": 0,
  "windows_processed": 0,
  "projections_created": 0,
  "streams_processed": [],
  "errors": []
}
```

## Running the System

Execute the projection system:
```bash
python3 -m runtime.run_projection
```

This must be run from the `/app` directory.

## Observed Symptoms

The system runs without crashing but produces incorrect output:

- Projections contain incorrect aggregated values that do not match what would be expected from the source events
- Some events appear to be missing or duplicated in the final projections
- Ordering inconsistencies in the output suggest temporal processing issues
- Certain view keys contain values from unexpected sources
- Aggregate totals do not reconcile with the raw event data

## Global System-Wide Tooling

The following global system-wide tools are available in the environment:

- `python3` (3.11)
- `uv` (for installing and running additional Python packages)
- Standard Unix utilities

## Debugging Guidance

- Trace the event processing lifecycle from source files through to output
- Verify data integrity at each stage of the processing workflow
- Compare intermediate results against source data to isolate where values diverge
- Pay attention to how events flow between processing stages
- Consider edge cases in how events are grouped, identified, and aggregated
- Check that configuration is being interpreted correctly by the processing logic

## Constraints

- All source code is in `/app/runtime/`
- Do not modify configuration files or input data
- The fix should address the root causes in the processing logic
- After fixing, re-run the system to regenerate output
