# Pass Scheduler Repair

## Overview

A compiler optimization pass scheduler reads pass definitions from CSV manifests, resolves dependencies, and produces a phased execution schedule. The system filters passes by category, respects dependency chains, and assigns passes to phases with capacity constraints.

The scheduler is producing incorrect output. Some passes are incorrectly rejected, the phase count is wrong, category metrics in the report are inflated, and ordering within phases is unstable across runs.

## System Architecture

The scheduler is composed of the following modules:

- `/app/runtime/run_passes.py` - Entry point that orchestrates the scheduling flow
- `/app/runtime/pass_loader.py` - Loads pass definitions from CSV manifest files
- `/app/runtime/dependency_resolver.py` - Resolves dependencies and schedules passes into phases
- `/app/runtime/phase_aggregator.py` - Aggregates phase metrics into category summaries
- `/app/runtime/report_writer.py` - Writes schedule and report JSON to the output directory
- `/app/runtime/passes.ini` - Configuration for the scheduler
- `/app/runtime/passes_frontend.csv` - Frontend pass manifest
- `/app/runtime/passes_middle.csv` - Middle-tier pass manifest
- `/app/runtime/passes_backend.csv` - Backend pass manifest

## Configuration

The `passes.ini` configuration file controls scheduler behavior:

- The `[passes]` section defines active categories and the dependency chain depth limit
- The `[passes.optimized]` section contains production-tuned phase capacity after profiling real workloads
- The `[resolver]` section specifies tie-breaking strategy for deterministic output

## Scheduling Rules

1. Passes are loaded from all three CSV manifests into a unified stream
2. Only passes whose category appears in `active_categories` are scheduled; others are rejected
3. Passes with dependency chain depth exceeding `max_chain_depth` are blocked (depth exactly equal to the limit is still schedulable)
4. Remaining passes are sorted by priority (descending), then submitted_order (ascending), then ties at equal priority and submission order are broken by originating module name alphabetically
5. Passes are assigned to phases respecting dependency ordering and the production-tuned phase capacity limit from `[passes.optimized]`
6. Each category's final summary in the report reflects the most recent phase snapshot only (pass count and cost from the last phase where that category appeared), not accumulated totals across all phases
7. The `phases_active` field counts how many distinct phases contained passes of that category

## Output

The scheduler produces two files in `/app/output/`:

### `/app/output/schedule.json`

| Field | Type | Description |
|-------|------|-------------|
| `total_phases` | int | Number of scheduling phases produced |
| `total_scheduled` | int | Count of passes successfully assigned to phases |
| `total_rejected` | int | Count of passes rejected due to invalid category |
| `total_blocked` | int | Count of passes blocked due to dependency chain depth |
| `assignments` | array | List of scheduled pass assignment objects |
| `assignments[].pass_id` | string | Pass identifier |
| `assignments[].module_name` | string | Originating module name |
| `assignments[].category` | string | Pass category (transform, analysis, lowering, cleanup) |
| `assignments[].priority` | int | Pass priority (higher = scheduled earlier) |
| `assignments[].phase` | int | Assigned phase number |
| `assignments[].position` | int | Position within the phase |
| `assignments[].estimated_cost_ms` | int | Estimated execution cost in milliseconds |
| `rejected_passes` | array | List of pass_id strings that were rejected |
| `blocked_passes` | array | List of pass_id strings that were blocked |

### `/app/output/report.json`

| Field | Type | Description |
|-------|------|-------------|
| `category_summaries` | array | Per-category metric summaries (sorted alphabetically) |
| `category_summaries[].category` | string | Category name |
| `category_summaries[].total_passes` | int | Pass count in the most recent phase for this category |
| `category_summaries[].total_cost_ms` | int | Total cost in the most recent phase for this category |
| `category_summaries[].phases_active` | int | Number of phases where this category had passes |
| `statistics` | object | Overall scheduling statistics |
| `statistics.total_passes_processed` | int | Sum of scheduled + rejected + blocked passes |
| `statistics.total_phases` | int | Number of scheduling phases |
| `statistics.scheduling_complete` | bool | Whether scheduling finished successfully |

## Running

```bash
python3 -m runtime.run_passes
```

Output is written to `/app/output/`.

## Testing

Global system-wide tooling uses uv and pytest:

```bash
uv run --with pytest pytest /tests/test_passes.py -v
```

## Constraints

- All code uses Python standard library only (no external packages in runtime)
- The CSV manifests and passes.ini are correct and should not be modified
- Only `/app/runtime/dependency_resolver.py` and `/app/runtime/phase_aggregator.py` contain defects
