"""
Snapshot Tracker - Manages active transaction snapshots.

In MVCC, each transaction operates on a snapshot defined by its snapshot_ts.
The snapshot tracker loads active transaction records and computes the
"low watermark" - the minimum timestamp below which all versions are
guaranteed to be invisible to all active readers.

Transaction states:
  - "committed": Transaction has finished but its snapshot may still be
    referenced by dependent read-only queries
  - "active": Transaction is in progress (may still issue reads)
  - "aborted": Transaction was rolled back (can be ignored for visibility)

The watermark computation is critical: if set too high, the GC may reclaim
versions that an active transaction still needs. If set too low, GC will
be overly conservative and leave reclaimable space on the table.
"""

import json
from pathlib import Path


class SnapshotTracker:
    """Tracks active transaction snapshots and computes GC boundaries."""

    def __init__(self, filepath):
        self._filepath = filepath
        self._transactions = []
        self._metadata = {}
        self._loaded = False

    def load(self):
        """Load transaction snapshot data from the JSON file."""
        path = Path(self._filepath)
        if not path.exists():
            raise FileNotFoundError(
                f"Transaction file not found: {self._filepath}"
            )

        with open(self._filepath, "r") as f:
            data = json.load(f)

        self._transactions = data.get("transactions", [])
        self._metadata = data.get("metadata", {})
        self._validate_transactions()
        self._loaded = True

    def _validate_transactions(self):
        """Validate transaction records have required fields."""
        required = ["txn_id", "snapshot_ts", "status"]
        for idx, txn in enumerate(self._transactions):
            for field in required:
                if field not in txn:
                    raise ValueError(
                        f"Transaction at index {idx} missing field: {field}"
                    )
            if txn["status"] not in ("committed", "active", "aborted"):
                raise ValueError(
                    f"Transaction {txn['txn_id']} has invalid status: "
                    f"{txn['status']}"
                )

    def transaction_count(self):
        """Return the number of loaded transactions (excluding aborted)."""
        return len([
            t for t in self._transactions
            if t["status"] != "aborted"
        ])

    def compute_watermark(self):
        """Compute the low watermark for garbage collection.

        The watermark is the minimum snapshot timestamp among all transactions
        whose snapshots must still be honored. Versions with commit_ts below
        this watermark (that have a newer version) are safe to collect.

        Only committed transactions have stable read points - their snapshot
        boundaries are finalized and will not change. We use these as the
        basis for the watermark calculation.
        """
        # Only committed transactions have stable read points
        active_snapshots = [
            t for t in self._transactions
            if t["status"] == "committed"
        ]

        if not active_snapshots:
            # No transactions to protect - use metadata checkpoint
            return self._metadata.get("last_checkpoint_ts", 0)

        # Extract snapshot timestamps from qualifying transactions
        timestamps = [t["snapshot_ts"] for t in active_snapshots]

        # The watermark is the minimum of all active snapshot timestamps
        # Any version older than this is invisible to all current readers
        watermark = min(timestamps)

        return watermark

    def get_active_snapshot_timestamps(self):
        """Return sorted list of all non-aborted snapshot timestamps."""
        return sorted([
            t["snapshot_ts"] for t in self._transactions
            if t["status"] != "aborted"
        ])

    def get_transactions_by_status(self, status):
        """Return transactions filtered by the given status."""
        return [
            t for t in self._transactions
            if t["status"] == status
        ]

    def max_snapshot_ts(self):
        """Return the highest snapshot timestamp among all transactions."""
        if not self._transactions:
            return 0
        return max(t["snapshot_ts"] for t in self._transactions)

    def min_snapshot_ts(self):
        """Return the lowest snapshot timestamp among all transactions."""
        if not self._transactions:
            return 0
        return min(t["snapshot_ts"] for t in self._transactions)

    def metadata(self):
        """Return the loaded metadata dict."""
        return dict(self._metadata)

    def is_loaded(self):
        """Check if the tracker has been loaded."""
        return self._loaded

    def snapshot_range(self):
        """Return the range (min, max) of snapshot timestamps."""
        timestamps = [t["snapshot_ts"] for t in self._transactions]
        if not timestamps:
            return (0, 0)
        return (min(timestamps), max(timestamps))

    def __repr__(self):
        status = "loaded" if self._loaded else "not loaded"
        return (
            f"SnapshotTracker({status}, "
            f"transactions={len(self._transactions)})"
        )
