"""WAL Replay Recovery Engine — Entry Point

Orchestrates the crash recovery process:
1. Load WAL segments
2. Find checkpoint boundary
3. Filter records for replay window
4. Track transaction states
5. Reconstruct page state
6. Write recovery output
"""

import os
import sys
import configparser

from runtime.wal_loader import load_wal_segments
from runtime.checkpoint_handler import find_last_checkpoint, filter_records_after_checkpoint
from runtime.txn_tracker import TransactionTracker
from runtime.page_reconstructor import PageReconstructor, PageConflictTracker
from runtime.recovery_writer import write_recovered_state, write_recovery_report


def main():
    # Determine paths relative to this file
    runtime_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(runtime_dir, "recovery.ini")

    # Load configuration
    config = configparser.ConfigParser()
    config.read(config_path)

    segment_dir = os.path.join(runtime_dir, config.get("segments", "segment_dir"))
    segment_pattern = config.get("segments", "segment_pattern")
    output_dir = os.path.join(runtime_dir, config.get("output", "output_dir"))

    # Step 1: Load all WAL segments
    all_records = load_wal_segments(segment_dir, segment_pattern)
    total_records = len(all_records)

    # Step 2: Find the last checkpoint
    checkpoint_lsn = find_last_checkpoint(all_records)

    # Step 3: Filter records to those needing replay (after checkpoint)
    replay_candidates = filter_records_after_checkpoint(all_records, checkpoint_lsn)

    # Step 4: Track transaction states
    tracker = TransactionTracker(config_path)
    tracker.process_records(replay_candidates)

    # Get the set of transactions to replay
    replay_txn_ids = tracker.get_replay_set()
    committed_txns = tracker.get_committed_txns()

    # Step 5: Reconstruct page state
    reconstructor = PageReconstructor()
    reconstructor.reconstruct(replay_candidates, replay_txn_ids)

    # Track page conflicts
    conflict_tracker = PageConflictTracker()
    conflict_tracker.track_writes(replay_candidates, replay_txn_ids)

    # Step 6: Compute recovery boundaries
    replay_lsns = [int(r["lsn"]) for r in replay_candidates if r["record_type"] != "checkpoint"]
    recovery_lsn_start = min(replay_lsns) if replay_lsns else 0
    recovery_lsn_end = tracker.get_last_committed_lsn()

    # Step 7: Write output
    pages = reconstructor.get_page_state()
    replayed_writes = reconstructor.get_replayed_count()
    high_conflict_pages = conflict_tracker.get_high_conflict_pages()

    write_recovered_state(
        output_dir, pages, committed_txns, replayed_writes,
        recovery_lsn_start, recovery_lsn_end
    )

    transaction_report = tracker.get_transaction_report()
    write_recovery_report(
        output_dir, total_records, transaction_report,
        checkpoint_lsn, len(pages), high_conflict_pages
    )

    print(f"Recovery complete. Processed {total_records} records.")
    print(f"Checkpoint LSN: {checkpoint_lsn}")
    print(f"Transactions replayed: {len(replay_txn_ids)}")
    print(f"Pages recovered: {len(pages)}")
    print(f"Output written to: {output_dir}")


if __name__ == "__main__":
    main()
