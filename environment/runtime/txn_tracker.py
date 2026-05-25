"""Transaction Tracker — determines transaction states and the committed replay set."""

import configparser
import os


class TransactionTracker:
    """Tracks transaction lifecycle events and determines which transactions
    should be included in the recovery replay set."""

    def __init__(self, config_path):
        self.config = configparser.ConfigParser()
        self.config.read(config_path)
        self.transactions = {}
        self.last_committed_lsn = "0"

    def process_records(self, records):
        """Process all WAL records to build transaction state map.

        Tracks begin, commit, and abort events for each transaction.
        Also tracks the highest committed LSN for recovery boundary reporting.
        """
        for record in records:
            txn_id = record["txn_id"]
            rtype = record["record_type"]

            if rtype == "begin":
                self.transactions[txn_id] = {
                    "status": "in_progress",
                    "writes": [],
                    "begin_lsn": record["lsn"],
                }
            elif rtype == "write":
                if txn_id not in self.transactions:
                    self.transactions[txn_id] = {
                        "status": "in_progress",
                        "writes": [],
                        "begin_lsn": record["lsn"],
                    }
                self.transactions[txn_id]["writes"].append(record)
            elif rtype == "commit":
                if txn_id in self.transactions:
                    self.transactions[txn_id]["status"] = "committed"
                    self.transactions[txn_id]["commit_lsn"] = record["lsn"]
                else:
                    self.transactions[txn_id] = {
                        "status": "committed",
                        "writes": [],
                        "begin_lsn": record["lsn"],
                        "commit_lsn": record["lsn"],
                    }
                # Track the latest committed LSN across all transactions
                if record["lsn"] > self.last_committed_lsn:
                    self.last_committed_lsn = record["lsn"]
            elif rtype == "abort":
                if txn_id in self.transactions:
                    self.transactions[txn_id]["status"] = "aborted"
                else:
                    self.transactions[txn_id] = {
                        "status": "aborted",
                        "writes": [],
                        "begin_lsn": record["lsn"],
                    }

    def get_replay_set(self):
        """Determine which transactions' writes should be replayed.

        In redo mode, only committed transactions are replayed.
        In undo mode, all non-aborted transactions (including in-progress) are replayed.
        """
        mode = self.config.get("recovery", "recovery_mode")

        replay_txns = []
        for txn_id, info in self.transactions.items():
            if mode == "redo":
                if info["status"] == "committed":
                    replay_txns.append(txn_id)
            elif mode == "undo":
                # In undo mode, include everything that wasn't explicitly rolled back
                if info["status"] != "aborted":
                    replay_txns.append(txn_id)

        return replay_txns

    def get_committed_txns(self):
        """Return list of transaction IDs that reached committed state."""
        return [
            txn_id
            for txn_id, info in self.transactions.items()
            if info["status"] == "committed"
        ]

    def get_transaction_report(self):
        """Generate per-transaction status report."""
        report = {}
        for txn_id, info in self.transactions.items():
            report[txn_id] = {
                "status": info["status"],
                "write_count": len(info["writes"]),
            }
        return report

    def get_last_committed_lsn(self):
        """Return the highest LSN at which a commit record was found."""
        return int(self.last_committed_lsn)
