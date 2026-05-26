# MVCC Garbage Collector Repair

## System Overview

You are debugging an MVCC (Multi-Version Concurrency Control) garbage collector for a versioned key-value store. The system maintains multiple versions of each key and must determine which old versions are safe to reclaim without breaking active transactions.

The garbage collection system operates in stages:

1. **Version Store** loads committed version records from `versions_committed.jsonl`
2. **Snapshot Tracker** loads active transaction data and computes the GC watermark
3. **Visibility Checker** determines which versions are candidates for collection
4. **GC Planner** creates an execution plan with space reclamation estimates
5. **GC Reporter** assembles the final output report

## File Layout

All source files are located at absolute paths under `/app/`:

| File | Path | Purpose |
|------|------|---------|
| Entry point | `/app/run_gc.py` | Orchestrates the GC process |
| Version store | `/app/version_store.py` | Loads and indexes version data |
| Snapshot tracker | `/app/snapshot_tracker.py` | Tracks active transaction snapshots |
| Visibility checker | `/app/visibility_checker.py` | Determines version GC eligibility |
| GC planner | `/app/gc_planner.py` | Plans collection batches and estimates savings |
| GC reporter | `/app/gc_reporter.py` | Generates structured output report |
| Configuration | `/app/gc_config.ini` | GC parameters (multiple sections) |
| Version data | `/app/versions_committed.jsonl` | Committed version records |
| Transaction data | `/app/active_transactions.json` | Active transaction snapshots |

## Output Schema

The system writes `/app/gc_output.json` with this structure:

| Section | Field | Type | Description |
|---------|-------|------|-------------|
| `state` | `total_keys` | int | Number of distinct keys in store |
| `state` | `total_versions` | int | Total version records loaded |
| `state` | `active_transactions` | int | Number of active transactions |
| `state` | `watermark` | int | Computed GC watermark timestamp |
| `gc_plan` | `total_reclaimable_versions` | int | Count of versions to collect |
| `gc_plan` | `estimated_space_savings_bytes` | int | Estimated bytes to reclaim |
| `gc_plan` | `batches` | list | Execution batch details |
| `gc_plan` | `keys_affected` | list | Keys with reclaimable versions |
| `gc_plan` | `bytes_per_version_used` | int | Bytes estimate used per version |
| `gc_candidates` | `total_candidate_versions` | int | Actual candidate version count |
| `gc_candidates` | `by_key` | dict | Per-key candidate breakdown |
| `digest` | - | str | SHA-256 integrity hash of plan |

## Observed Symptoms

The garbage collector produces incorrect results in several ways:

1. **Incorrect watermark computation** - The GC watermark does not account for all transactions that may still be reading old versions. Some transactions that hold snapshots are being ignored when determining the safe collection boundary, causing versions that are still needed to be marked for collection.

2. **Boundary condition error in eligibility check** - Versions at the exact watermark boundary are being incorrectly treated as eligible for collection. The watermark represents a timestamp where at least one transaction may still be reading, so versions at that exact boundary must be protected.

3. **Version chain ordering defect** - The version chain for each key is not ordered correctly, which causes the wrong version to be treated as the "current" (most recent) version. This results in the oldest version being skipped during candidate analysis rather than being considered for collection.

4. **Inflated space savings estimate** - The estimated space reclamation uses an incorrect parameter value. The configuration file contains both theoretical and measured values from production profiling, and the wrong set of parameters is being used for the estimate.

5. **Undercounted reclaimable versions** - The count of total reclaimable versions is incorrect. The counting logic determines the number of keys that have reclaimable versions rather than the actual total number of individual versions to be collected.

## MVCC Invariants

For reference, the core MVCC garbage collection rules are:

- A version V of key K is safe to GC if there exists a newer version of K AND no active transaction can still observe V as the current version of K
- The GC watermark represents the system-wide minimum snapshot timestamp below which old (superseded) versions are invisible to all active readers
- All transactions that might still issue reads must be considered when computing the watermark
- The watermark boundary itself must be treated as potentially visible (conservative approach)
- Version chains must be ordered newest-first so that chain[0] is always the current version
