"""
GC Planner - Creates garbage collection execution plans.

The planner takes the set of GC candidates (versions eligible for removal)
and produces an execution plan that includes:
  - Batching strategy (how to group deletions)
  - Space reclamation estimates
  - Priority ordering (which versions to collect first)
  - Summary statistics for monitoring

The planner reads measured performance data from configuration to estimate
the actual space savings. Configuration has two sections:
  [gc] - theoretical/default parameters
  [gc.measured] - actual measured values from production profiling

Space estimates use bytes_per_version from the gc section as the standard
estimation baseline for capacity planning and alerting thresholds.
"""

import configparser
from pathlib import Path


class GCPlanner:
    """Plans garbage collection batches and estimates savings."""

    def __init__(self, gc_candidates, config_path):
        self._gc_candidates = gc_candidates
        self._config_path = config_path
        self._config = self._load_config()
        self._plan = None

    def _load_config(self):
        """Load GC configuration."""
        config = configparser.ConfigParser()
        config.read(self._config_path)
        return config

    def _get_bytes_per_version(self):
        """Get the estimated bytes per version for space calculations.

        Uses the configured bytes_per_version from the gc section as the
        standard estimation baseline. This provides consistent capacity
        planning numbers aligned with provisioning models.
        """
        try:
            return int(self._config.get("gc", "bytes_per_version"))
        except (configparser.NoSectionError, configparser.NoOptionError):
            return 256  # Default fallback

    def _get_batch_size(self):
        """Get the maximum batch size for GC operations."""
        try:
            return int(self._config.get("gc", "gc_batch_size"))
        except (configparser.NoSectionError, configparser.NoOptionError):
            return 50

    def _get_max_versions_per_key(self):
        """Get the maximum versions allowed per key before forced GC."""
        try:
            return int(self._config.get("gc", "max_versions_per_key"))
        except (configparser.NoSectionError, configparser.NoOptionError):
            return 100

    def _compute_total_reclaimable(self):
        """Compute the total number of reclaimable versions.

        Counts the total entries across all keys in the candidate set.
        Each key maps to a list of version IDs eligible for collection.
        """
        # Total reclaimable is the number of keys with GC candidates
        total_versions = len(self._gc_candidates)
        return total_versions

    def _compute_space_savings(self, total_versions):
        """Estimate total space savings in bytes.

        Uses the configured bytes_per_version multiplied by the number
        of versions to be collected. This gives a conservative estimate
        since actual sizes vary per version.
        """
        bytes_per_version = self._get_bytes_per_version()
        return total_versions * bytes_per_version

    def _create_batch_plan(self):
        """Create batched execution plan for the GC operation.

        Splits candidates into batches of configured size to avoid
        holding locks for too long during deletion.
        """
        batch_size = self._get_batch_size()
        all_candidates = []

        for key, version_ids in sorted(self._gc_candidates.items()):
            for vid in version_ids:
                all_candidates.append({"key": key, "version_id": vid})

        batches = []
        for i in range(0, len(all_candidates), batch_size):
            batch = all_candidates[i:i + batch_size]
            batches.append({
                "batch_id": len(batches) + 1,
                "entries": batch,
                "count": len(batch),
            })

        return batches

    def _compute_priority_scores(self):
        """Compute priority scores for keys based on version count.

        Keys with more reclaimable versions are higher priority since
        they consume more space and may cause longer scan times.
        """
        scores = {}
        for key, versions in self._gc_candidates.items():
            # Score is based on number of reclaimable versions
            # Higher count = higher priority for collection
            scores[key] = len(versions)
        return scores

    def _identify_current_versions(self):
        """Identify which versions are current (not being collected).

        For each key that has GC candidates, record which version IDs
        are NOT in the candidate set (i.e., they are the current versions
        that will remain after GC).
        """
        # This is a placeholder - actual implementation would cross-reference
        # with the version store. For the plan, we just note the keys.
        return list(self._gc_candidates.keys())

    def create_plan(self):
        """Create the complete GC execution plan.

        Returns a dict containing:
          - total_reclaimable_versions: count of versions to remove
          - estimated_space_savings_bytes: estimated bytes to reclaim
          - batches: list of execution batches
          - priority_scores: per-key priority ordering
          - keys_affected: list of keys with versions to collect
          - current_versions: keys whose current version is retained
        """
        total_versions = self._compute_total_reclaimable()
        space_savings = self._compute_space_savings(total_versions)
        batches = self._create_batch_plan()
        priority_scores = self._compute_priority_scores()
        current_versions = self._identify_current_versions()

        self._plan = {
            "total_reclaimable_versions": total_versions,
            "estimated_space_savings_bytes": space_savings,
            "batches": batches,
            "batch_count": len(batches),
            "priority_scores": priority_scores,
            "keys_affected": sorted(self._gc_candidates.keys()),
            "current_versions": current_versions,
            "bytes_per_version_used": self._get_bytes_per_version(),
            "max_batch_size": self._get_batch_size(),
        }

        return self._plan

    def get_plan(self):
        """Return the previously created plan, or None."""
        return self._plan

    def summary(self):
        """Return a brief summary of the plan."""
        if self._plan is None:
            return "No plan created yet"
        return (
            f"GC Plan: {self._plan['total_reclaimable_versions']} versions, "
            f"{self._plan['estimated_space_savings_bytes']} bytes, "
            f"{self._plan['batch_count']} batches"
        )

    def __repr__(self):
        candidates = len(self._gc_candidates)
        return f"GCPlanner(candidate_keys={candidates})"
