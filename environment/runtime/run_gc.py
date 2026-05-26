#!/usr/bin/env python3
"""
MVCC Garbage Collector - Entry Point

Orchestrates the garbage collection pipeline for a versioned key-value store.
The GC process identifies old versions that are no longer visible to any active
transaction and produces a collection plan with space reclamation estimates.

Pipeline stages:
  1. Load committed version data from the version store
  2. Load and analyze active transaction snapshots
  3. Compute the visibility watermark (safe GC boundary)
  4. Build version chains per key and determine GC candidates
  5. Plan the collection batch and estimate space savings
  6. Write the GC report to output
"""

import json
import os
import sys
from pathlib import Path

from version_store import VersionStore
from snapshot_tracker import SnapshotTracker
from visibility_checker import VisibilityChecker
from gc_planner import GCPlanner
from gc_reporter import GCReporter


def resolve_runtime_path(filename):
    """Resolve a file path relative to this script's directory."""
    base_dir = Path(__file__).parent
    return base_dir / filename


def validate_inputs(version_store, snapshot_tracker):
    """Perform pre-GC validation of loaded data."""
    if version_store.total_versions() == 0:
        return False, "No versions loaded from store"
    if snapshot_tracker.transaction_count() == 0:
        return False, "No active transactions found"
    return True, "OK"


def build_gc_context(version_store, snapshot_tracker):
    """Assemble the context object passed through the pipeline."""
    return {
        "total_keys": version_store.total_keys(),
        "total_versions": version_store.total_versions(),
        "transaction_count": snapshot_tracker.transaction_count(),
        "watermark": snapshot_tracker.compute_watermark(),
        "store": version_store,
        "tracker": snapshot_tracker,
    }


def run_gc_pipeline():
    """Execute the full GC pipeline and return the result."""
    # Stage 1: Load version data
    versions_path = resolve_runtime_path("versions_committed.jsonl")
    version_store = VersionStore(str(versions_path))
    version_store.load()

    # Stage 2: Load active transactions
    transactions_path = resolve_runtime_path("active_transactions.json")
    snapshot_tracker = SnapshotTracker(str(transactions_path))
    snapshot_tracker.load()

    # Validate inputs before proceeding
    valid, reason = validate_inputs(version_store, snapshot_tracker)
    if not valid:
        return {"error": reason, "gc_plan": None}

    # Stage 3: Compute watermark and build context
    context = build_gc_context(version_store, snapshot_tracker)
    watermark = context["watermark"]

    # Stage 4: Determine GC candidates via visibility analysis
    config_path = resolve_runtime_path("gc_config.ini")
    checker = VisibilityChecker(version_store, watermark, str(config_path))
    gc_candidates = checker.find_gc_candidates()

    # Stage 5: Plan the GC batch
    planner = GCPlanner(gc_candidates, str(config_path))
    gc_plan = planner.create_plan()

    # Stage 6: Generate report
    reporter = GCReporter(context, gc_candidates, gc_plan)
    report = reporter.generate()

    # Write output
    output_path = resolve_runtime_path("gc_output.json")
    with open(output_path, "w") as f:
        json.dump(report, f, indent=2)

    return report


def main():
    """Main entry point with error handling."""
    try:
        result = run_gc_pipeline()
        if result.get("error"):
            print(f"GC pipeline error: {result['error']}", file=sys.stderr)
            sys.exit(1)
        print(json.dumps(result, indent=2))
    except FileNotFoundError as e:
        print(f"Required input file not found: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"GC pipeline failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
