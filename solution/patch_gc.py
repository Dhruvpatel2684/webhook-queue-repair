"""
Solution: Patches the 5 bugs in the MVCC garbage collector.

Bug 1 (snapshot_tracker.py): compute_watermark() only considers committed
       transactions. Must include active transactions too.

Bug 2 (visibility_checker.py): _is_below_watermark() uses <= instead of <.
       Versions at exactly the watermark must be protected.

Bug 3 (visibility_checker.py): _build_version_chain() sorts ascending instead
       of descending. Chain must be newest-first so chain[0] is current.

Bug 4 (gc_planner.py): _get_bytes_per_version() reads from [gc] section (256)
       instead of [gc.measured] section (112).

Bug 5 (gc_planner.py): _compute_total_reclaimable() uses len(gc_candidates)
       which counts keys, not sum of version list lengths.
"""

import os

RUNTIME_DIR = os.path.dirname(os.path.abspath(__file__))
RUNTIME_DIR = os.path.join(os.path.dirname(RUNTIME_DIR), "environment", "runtime")


def patch_snapshot_tracker():
    """Fix Bug 1: Include active transactions in watermark computation."""
    filepath = os.path.join(RUNTIME_DIR, "snapshot_tracker.py")
    with open(filepath, "r") as f:
        content = f.read()

    content = content.replace(
        'if t["status"] == "committed"',
        'if t["status"] in ("committed", "active")',
    )

    with open(filepath, "w") as f:
        f.write(content)


def patch_visibility_checker():
    """Fix Bug 2: Use strict less-than for watermark boundary.
       Fix Bug 3: Sort version chain descending (newest first)."""
    filepath = os.path.join(RUNTIME_DIR, "visibility_checker.py")
    with open(filepath, "r") as f:
        content = f.read()

    # Bug 2: Change <= to < in watermark check
    content = content.replace(
        'return version["commit_ts"] <= self._watermark',
        'return version["commit_ts"] < self._watermark',
    )

    # Bug 3: Sort descending instead of ascending
    content = content.replace(
        'versions.sort(key=lambda v: v["commit_ts"])',
        'versions.sort(key=lambda v: v["commit_ts"], reverse=True)',
    )

    with open(filepath, "w") as f:
        f.write(content)


def patch_gc_planner():
    """Fix Bug 4: Read bytes_per_version from gc.measured section.
       Fix Bug 5: Sum version list lengths instead of counting keys."""
    filepath = os.path.join(RUNTIME_DIR, "gc_planner.py")
    with open(filepath, "r") as f:
        content = f.read()

    # Bug 4: Change config section from "gc" to "gc.measured"
    content = content.replace(
        'return int(self._config.get("gc", "bytes_per_version"))',
        'return int(self._config.get("gc.measured", "bytes_per_version"))',
    )

    # Bug 5: Sum all version lists instead of counting keys
    content = content.replace(
        "total_versions = len(self._gc_candidates)",
        "total_versions = sum(len(v) for v in self._gc_candidates.values())",
    )

    with open(filepath, "w") as f:
        f.write(content)


if __name__ == "__main__":
    patch_snapshot_tracker()
    patch_visibility_checker()
    patch_gc_planner()
    print("All 5 bugs patched successfully.")
