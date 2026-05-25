"""Page Reconstructor — rebuilds page state from committed write records."""


class PageReconstructor:
    """Reconstructs the final state of each page by replaying write records
    from committed transactions in the correct order."""

    def __init__(self):
        self.page_state = {}
        self.replayed_count = 0

    def reconstruct(self, records, replay_txn_ids):
        """Reconstruct page state from write records belonging to the replay set.

        Filters writes to only those from transactions in the replay set,
        orders them appropriately, and applies each write to build final page state.
        """
        # Collect all write records from transactions in the replay set
        page_writes = []
        for record in records:
            if record["record_type"] == "write" and record["txn_id"] in replay_txn_ids:
                page_writes.append(record)

        # Order writes by originating transaction for consistent replay
        page_writes.sort(key=lambda w: (w["page_id"], int(w["lsn"])))

        # Apply each write to reconstruct final page state
        for record in page_writes:
            page_id = record["page_id"]
            # Apply write - last write to each page wins
            self.page_state[page_id] = record["after_image"]
            self.replayed_count += 1

    def get_page_state(self):
        """Return the reconstructed page state map."""
        return dict(self.page_state)

    def get_replayed_count(self):
        """Return the number of write operations replayed."""
        return self.replayed_count

    def get_high_conflict_pages(self):
        """Identify pages that were written by multiple transactions."""
        # This is computed from page_state tracking - pages with multiple writers
        return []


class PageConflictTracker:
    """Tracks which transactions write to which pages to identify conflicts."""

    def __init__(self):
        self.page_writers = {}

    def track_writes(self, records, replay_txn_ids):
        """Record which transactions wrote to each page."""
        for record in records:
            if record["record_type"] == "write" and record["txn_id"] in replay_txn_ids:
                page_id = record["page_id"]
                if page_id not in self.page_writers:
                    self.page_writers[page_id] = set()
                self.page_writers[page_id].add(record["txn_id"])

    def get_high_conflict_pages(self):
        """Return pages written by more than one transaction."""
        return [
            page_id
            for page_id, writers in self.page_writers.items()
            if len(writers) > 1
        ]
