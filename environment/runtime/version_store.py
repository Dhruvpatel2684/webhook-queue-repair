"""
Version Store - Loads and indexes committed version data.

The version store reads committed version records from a JSONL file and
provides indexed access by key and version ID. Each version record contains:
  - key: The logical key this version belongs to
  - version_id: Unique identifier for this version
  - commit_ts: Timestamp when this version was committed
  - value_hash: Hash of the stored value (for dedup detection)
  - size_bytes: Size of the value payload

The store also builds per-key version chains used by the visibility checker
to determine which versions are candidates for garbage collection.
"""

import json
from collections import defaultdict
from pathlib import Path


class VersionStore:
    """Manages loading and indexing of committed version records."""

    def __init__(self, filepath):
        self._filepath = filepath
        self._versions = []
        self._by_key = defaultdict(list)
        self._by_id = {}
        self._loaded = False
        self._load_errors = []

    def load(self):
        """Load version records from the JSONL file.

        Each line is parsed independently; malformed lines are tracked
        but do not abort the load process.
        """
        path = Path(self._filepath)
        if not path.exists():
            raise FileNotFoundError(f"Version file not found: {self._filepath}")

        line_number = 0
        with open(self._filepath, "r") as f:
            for line in f:
                line_number += 1
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    record = json.loads(stripped)
                    self._validate_record(record, line_number)
                    self._versions.append(record)
                    self._by_key[record["key"]].append(record)
                    self._by_id[record["version_id"]] = record
                except (json.JSONDecodeError, KeyError, ValueError) as e:
                    self._load_errors.append({
                        "line": line_number,
                        "error": str(e),
                        "raw": stripped[:100]
                    })

        self._loaded = True

    def _validate_record(self, record, line_number):
        """Validate that a version record has all required fields."""
        required_fields = ["key", "version_id", "commit_ts", "value_hash", "size_bytes"]
        for field in required_fields:
            if field not in record:
                raise KeyError(f"Missing required field '{field}' at line {line_number}")

        if not isinstance(record["commit_ts"], (int, float)):
            raise ValueError(f"commit_ts must be numeric at line {line_number}")
        if not isinstance(record["size_bytes"], (int, float)):
            raise ValueError(f"size_bytes must be numeric at line {line_number}")

    def total_versions(self):
        """Return the total number of loaded version records."""
        return len(self._versions)

    def total_keys(self):
        """Return the number of distinct keys in the store."""
        return len(self._by_key)

    def get_versions_for_key(self, key):
        """Return all version records for a given key."""
        return list(self._by_key.get(key, []))

    def get_version_by_id(self, version_id):
        """Look up a single version record by its ID."""
        return self._by_id.get(version_id)

    def all_keys(self):
        """Return a sorted list of all keys in the store."""
        return sorted(self._by_key.keys())

    def all_versions(self):
        """Return all version records (unordered)."""
        return list(self._versions)

    def get_key_chain(self, key):
        """Return versions for a key, suitable for chain analysis.

        Returns a copy of the version list for the given key.
        Callers are responsible for sorting as needed.
        """
        versions = self._by_key.get(key, [])
        return [dict(v) for v in versions]

    def version_count_per_key(self):
        """Return a dict mapping key -> number of versions."""
        return {key: len(versions) for key, versions in self._by_key.items()}

    def load_errors(self):
        """Return any errors encountered during loading."""
        return list(self._load_errors)

    def is_loaded(self):
        """Check if the store has been loaded."""
        return self._loaded

    def size_summary(self):
        """Return aggregate size statistics."""
        if not self._versions:
            return {"total_bytes": 0, "avg_bytes": 0, "max_bytes": 0, "min_bytes": 0}

        sizes = [v["size_bytes"] for v in self._versions]
        return {
            "total_bytes": sum(sizes),
            "avg_bytes": sum(sizes) / len(sizes),
            "max_bytes": max(sizes),
            "min_bytes": min(sizes),
        }

    def keys_with_version_count_above(self, threshold):
        """Return keys that have more versions than the given threshold."""
        return [
            key for key, versions in self._by_key.items()
            if len(versions) > threshold
        ]

    def __repr__(self):
        status = "loaded" if self._loaded else "not loaded"
        return (
            f"VersionStore({status}, "
            f"versions={len(self._versions)}, "
            f"keys={len(self._by_key)})"
        )
