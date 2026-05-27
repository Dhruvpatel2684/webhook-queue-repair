# Scheduler Engine Repair

## Overview

You are working with a priority-based task scheduling engine that processes job batches
from multiple queues. The engine reads job definitions, applies priority filtering and
ordering, distributes jobs across execution rounds with concurrency constraints, and
produces an execution plan with timing information.

The system is designed as a Global system-wide tooling component for orchestrating
background job execution across distributed service queues.

## System Architecture

The scheduling engine consists of four core modules:

1. **Parser** (`/app/runtime/parser.py`): Loads job batch files from
   `/app/runtime/data/`, validates their structure and constraints, and produces
   a list of typed Job objects for downstream processing.

2. **Prioritizer** (`/app/runtime/prioritizer.py`): Applies priority-based filtering
   to determine which jobs are eligible for scheduling. Jobs must have a priority level
   that matches one of the configured levels. The prioritizer also assigns execution
   weight factors used for timing calculations.

3. **Executor** (`/app/runtime/executor.py`): Distributes eligible jobs into execution
   rounds respecting concurrency constraints. Each round has a maximum number of jobs
   that can run concurrently. The executor computes expected execution times based on
   job duration and priority factors.

4. **Orchestrator** (`/app/runtime/run_scheduler.py`): Entry point that coordinates
   the full workflow, assembles the final execution plan, applies deterministic
   ordering, and writes output files.

## Configuration

The engine is configured via `/app/runtime/config.ini` which contains multiple sections:

- `[scheduler]`: General scheduling parameters including priority level definitions,
  default timeouts, retry limits, and execution mode.

- `[scheduler.limits]`: Execution constraints including concurrency limits, maximum
  rounds, and time budgets. Use the scheduler.limits section for execution constraints
  that govern how many jobs run per round and the total scheduling horizon.

- `[scheduler.logging]`: Logging configuration for structured output.

## Input Data

Job batches are stored as JSON files in `/app/runtime/data/`:

- `/app/runtime/data/jobs_batch1.json`: 20 jobs across email, analytics, and reporting queues
- `/app/runtime/data/jobs_batch2.json`: 20 jobs across billing, notifications, and sync queues
- `/app/runtime/data/jobs_batch3.json`: 18 jobs across alerts, maintenance, and cleanup queues

Each job has the following structure:
```json
{
  "job_id": "job-001",
  "queue_name": "email",
  "priority": "high|medium|low|critical",
  "payload": {"action": "...", ...},
  "timeout": 30,
  "retry_count": 0,
  "estimated_duration": 5.0
}
```

Total: 58 jobs across 9 queues with 4 priority levels (critical, high, medium, low).

## Expected Output

The engine produces two files in `/app/runtime/output/`:

### `/app/runtime/output/execution_plan.json`

A sorted list of scheduled job entries:
```json
[
  {
    "job_id": "job-042",
    "queue_name": "alerts",
    "priority": "critical",
    "scheduled_round": 1,
    "execution_time": 4.5,
    "status": "scheduled"
  }
]
```

The execution plan must be deterministically sorted. Jobs with equal priority are
ordered by queue_name, then job_id. This ensures reproducible output regardless
of input file ordering.

### `/app/runtime/output/schedule_summary.json`

Aggregate metadata about the scheduling run:
```json
{
  "total_jobs_parsed": 58,
  "total_jobs_eligible": 58,
  "total_jobs_scheduled": 58,
  "priority_levels_used": ["critical", "high", "low", "medium"],
  "priority_distribution": {"critical": 4, "high": 18, "medium": 18, "low": 18},
  "round_summary": {"total_rounds": 12, "jobs_per_round": {...}},
  "time_budget": 300.0,
  "execution_mode": "parallel"
}
```

## Execution Constraints

- All 58 jobs must appear in the execution plan
- No execution round may contain more than the configured concurrent limit from
  the scheduler.limits section
- Execution times are computed as `estimated_duration * priority_factor` where factors
  are: critical=1.0, high=1.2, medium=1.5, low=1.8
- No single job execution time should exceed 30 seconds
- The schedule must be deterministically ordered

## Running the Engine

```bash
cd /app
python3 -m runtime.run_scheduler
```

This reads configuration from `/app/runtime/config.ini`, loads all batch files from
`/app/runtime/data/`, processes them through the scheduling stages, and writes
results to `/app/runtime/output/`.

## Validation

The test suite runs 10 tests across three difficulty tiers validating structure,
correctness, and comprehensive accuracy of the scheduling output. All tests must
pass for the engine to be considered correctly functioning.

## Your Task

The scheduling engine has defects that cause incorrect output. You need to identify
and fix the issues so that all validation tests pass. The defects affect how jobs
are filtered, how concurrency limits are applied, how execution times are computed,
and how the final plan is ordered.

Examine the configuration, trace the data flow through each module, and verify that
the computed output matches the documented constraints above. Pay attention to how
configuration values are parsed and which sections provide which parameters.

## File Reference

| Path | Purpose |
|------|---------|
| `/app/runtime/config.ini` | Engine configuration |
| `/app/runtime/parser.py` | Job batch loading and validation |
| `/app/runtime/prioritizer.py` | Priority filtering and weighting |
| `/app/runtime/executor.py` | Round scheduling and timing |
| `/app/runtime/run_scheduler.py` | Orchestration and output |
| `/app/runtime/models.py` | Data structures |
| `/app/runtime/data/` | Input job batches |
| `/app/runtime/output/` | Generated output files |
