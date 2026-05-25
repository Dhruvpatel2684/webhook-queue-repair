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

1. Passes are loaded from all three CSV manifests
2. Only passes whose category appears in `active_categories` are scheduled; others are rejected
3. Passes with dependency chain depth exceeding `max_chain_depth` are blocked
4. Remaining passes are sorted by priority (descending), then submitted_order (ascending), then ties at equal priority and submission order are broken by originating module name alphabetically
5. Passes are assigned to phases respecting dependency ordering and phase capacity limits
6. Each category's final summary reflects the most recent phase snapshot, not accumulated totals

## Output

The scheduler produces two files in `/app/output/`:

- `schedule.json` - Contains phase assignments, rejected passes, and blocked passes
- `report.json` - Contains per-category summaries and overall statistics

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
