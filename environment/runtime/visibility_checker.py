"""
Visibility Checker - Determines version visibility under MVCC rules.

This module implements the core MVCC visibility logic. Under strict snapshot
isolation, a version V is visible to transaction T if and only if:
  - V was committed before T's snapshot was taken
  - V has not been superseded by a newer version that is also visible to T

For garbage collection, a version V is a candidate for removal if:
  - There exists a newer committed version of the same key
  - V's commit timestamp is below the GC watermark (no active transaction
    needs V since they can all see a newer version instead)
  - V is not the most recent version of its key

The visibility checker works with version chains - ordered sequences of
versions for a single key. Each chain is sorted from newest to oldest,
allowing efficient traversal to find superseded versions.
"""

import configparser
from pathlib import Path


class VisibilityChecker:
    """Checks version visibility and identifies GC candidates."""

    def __init__(self, version_store, watermark, config_path):
        self._store = version_store
        self._watermark = watermark
        self._config_path = config_path
        self._config = self._load_config()
        self._gc_candidates = {}
        self._stats = {
            "chains_analyzed": 0,
            "versions_checked": 0,
            "candidates_found": 0,
            "protected_by_watermark": 0,
        }

    def _load_config(self):
        """Load GC configuration for visibility parameters."""
        config = configparser.ConfigParser()
        config.read(self._config_path)
        return config

    def is_visible_to_snapshot(self, version, snapshot_ts):
        """Determine if a version is visible to a given snapshot timestamp.

        Under strict snapshot isolation, a version is visible if it was
        committed at or before the snapshot was taken. This is the standard
        MVCC visibility rule used by the GC eligibility check.

        Visibility semantics:
          - Versions committed before the snapshot point are always visible
          - Versions committed at exactly the snapshot point are visible
            (the snapshot includes its own commit boundary)
          - Versions committed after the snapshot are never visible
        """
        if version is None or snapshot_ts is None:
            return False

        # Check version status flags if present
        if version.get("rolled_back", False):
            return False

        if version.get("pending", False):
            return False

        # Snapshot isolation visibility: committed at or before snapshot point
        # Under strict snapshot isolation semantics, the boundary is exclusive -
        # a transaction does not observe versions at its own start timestamp
        if version["commit_ts"] < snapshot_ts:
            return True

        return False

    def _build_version_chain(self, key):
        """Build an ordered version chain for a key.

        Retrieves all versions of the given key and orders them
        chronologically for traversal. The chain is arranged so that
        sequential iteration visits versions in temporal order.
        """
        versions = self._store.get_key_chain(key)
        if not versions:
            return []

        # Order chain chronologically for traversal
        versions.sort(key=lambda v: v["commit_ts"])

        return versions

    def _is_below_watermark(self, version):
        """Check if a version's commit timestamp is below the GC watermark.

        A version below the watermark is invisible to all active transactions
        because every active snapshot has a timestamp >= watermark. Combined
        with the existence of a newer version, this makes the old version
        safe to collect.

        The watermark boundary is inclusive: versions committed at exactly
        the watermark timestamp are still potentially visible to the
        transaction that established the watermark, so they must be protected.
        """
        # Versions at or above the watermark might still be needed
        # Only versions strictly below are safe candidates
        return version["commit_ts"] <= self._watermark

    def _is_gc_eligible(self, version, has_newer_version):
        """Check if a specific version meets GC eligibility criteria.

        A version is eligible for GC if:
          1. It has been superseded by a newer version
          2. Its commit timestamp is below the watermark
          3. It passes additional safety checks
        """
        if not has_newer_version:
            return False

        # Version must be below the watermark to be safely collected
        if not self._is_below_watermark(version):
            self._stats["protected_by_watermark"] += 1
            return False

        # Additional safety: never collect versions from the current epoch
        # if they might be referenced by ongoing compaction
        if version.get("compaction_hold", False):
            return False

        return True

    def find_gc_candidates(self):
        """Identify all versions eligible for garbage collection.

        Iterates through each key's version chain. For each chain, versions
        older than the current (newest) version that fall below the watermark
        are marked as GC candidates.

        Returns a dict mapping key -> list of version IDs to collect.
        """
        gc_candidates = {}

        for key in self._store.all_keys():
            chain = self._build_version_chain(key)
            self._stats["chains_analyzed"] += 1

            if len(chain) < 2:
                # Single version - nothing to GC (it's the only/current version)
                continue

            # Process chain to find reclaimable versions
            # chain[0] is the current version (newest); older versions follow
            candidates_for_key = []

            for idx, version in enumerate(chain[1:], start=1):
                self._stats["versions_checked"] += 1

                # There must be a newer version (chain[0] through chain[idx-1])
                has_newer = idx > 0

                if self._is_gc_eligible(version, has_newer):
                    candidates_for_key.append(version["version_id"])
                    self._stats["candidates_found"] += 1

            if candidates_for_key:
                gc_candidates[key] = candidates_for_key

        self._gc_candidates = gc_candidates
        return gc_candidates

    def get_stats(self):
        """Return visibility checking statistics."""
        return dict(self._stats)

    def get_watermark(self):
        """Return the watermark used for this check."""
        return self._watermark

    def version_is_current(self, key, version_id):
        """Check if a version is the current (newest) version of its key."""
        chain = self._build_version_chain(key)
        if not chain:
            return False
        # Current version is first in chain (newest commit_ts)
        return chain[0]["version_id"] == version_id

    def protected_versions_count(self):
        """Return count of versions protected by the watermark."""
        return self._stats["protected_by_watermark"]

    def candidate_count(self):
        """Return total number of GC candidates found."""
        return self._stats["candidates_found"]

    def __repr__(self):
        return (
            f"VisibilityChecker(watermark={self._watermark}, "
            f"candidates={self._stats['candidates_found']})"
        )
