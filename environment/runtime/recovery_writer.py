"""Recovery Writer — produces output JSON files with recovery results."""

import hashlib
import json
import os


def compute_state_digest(pages, committed_txns, replayed_writes):
    """Compute a 16-character hex digest representing the recovery state.

    The digest incorporates page contents, committed transaction list,
    and the replay count to provide an integrity check.
    """
    hasher = hashlib.md5()

    # Hash sorted page state
    for page_id in sorted(pages.keys()):
        hasher.update(f"{page_id}={pages[page_id]}".encode())

    # Hash sorted committed transaction list
    for txn_id in sorted(committed_txns):
        hasher.update(txn_id.encode())

    # Hash the replay count
    hasher.update(str(replayed_writes).encode())

    return hasher.hexdigest()[:16]


def write_recovered_state(output_dir, pages, committed_txns, replayed_writes,
                          recovery_lsn_start, recovery_lsn_end):
    """Write the recovered_state.json output file."""
    os.makedirs(output_dir, exist_ok=True)

    state_digest = compute_state_digest(pages, committed_txns, replayed_writes)

    state = {
        "pages": pages,
        "committed_txns": sorted(committed_txns),
        "replayed_writes": replayed_writes,
        "recovery_lsn_start": recovery_lsn_start,
        "recovery_lsn_end": recovery_lsn_end,
        "state_digest": state_digest,
    }

    output_path = os.path.join(output_dir, "recovered_state.json")
    with open(output_path, "w") as f:
        json.dump(state, f, indent=2)

    return state


def write_recovery_report(output_dir, total_records, transaction_report,
                          checkpoint_lsn, pages_recovered, high_conflict_pages):
    """Write the recovery_report.json output file."""
    os.makedirs(output_dir, exist_ok=True)

    report = {
        "total_records_processed": total_records,
        "transactions": transaction_report,
        "checkpoint_lsn": checkpoint_lsn,
        "pages_recovered": pages_recovered,
        "high_conflict_pages": sorted(high_conflict_pages),
    }

    output_path = os.path.join(output_dir, "recovery_report.json")
    with open(output_path, "w") as f:
        json.dump(report, f, indent=2)

    return report
