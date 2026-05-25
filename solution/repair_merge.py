"""Repair script for CRDT merge engine.

Applies fixes to lww_register.py, orset_merger.py, and conflict_detector.py,
then re-runs the merge to produce correct output.
"""

import os
import sys


def apply_fixes():
    runtime_dir = "/app/runtime"

    # Fix 1: lww_register.py - timestamp comparison must use int()
    # Fix 4: lww_register.py - read from merge.priorities section
    lww_path = os.path.join(runtime_dir, "lww_register.py")
    with open(lww_path, "r") as f:
        content = f.read()

    content = content.replace(
        'if op["timestamp"] > current["timestamp"]:',
        'if int(op["timestamp"]) > int(current["timestamp"]):'
    )
    content = content.replace(
        'elif op["timestamp"] == current["timestamp"]:',
        'elif int(op["timestamp"]) == int(current["timestamp"]):'
    )
    content = content.replace(
        'priority_raw = config.get("merge", "replica_priority")',
        'priority_raw = config.get("merge.priorities", "replica_priority")'
    )

    with open(lww_path, "w") as f:
        f.write(content)

    # Fix 2: orset_merger.py - remove should match by value, not element_id
    # Fix 3: orset_merger.py - deduplication should use element_id, not value
    orset_path = os.path.join(runtime_dir, "orset_merger.py")
    with open(orset_path, "r") as f:
        content = f.read()

    content = content.replace(
        'sets[key] = [e for e in sets[key] if e["element_id"] != op["element_id"]]',
        'sets[key] = [e for e in sets[key] if e["value"] != op["value"]]'
    )
    content = content.replace(
        'if elem["value"] not in seen:\n                seen.add(elem["value"])',
        'if elem["element_id"] not in seen:\n                seen.add(elem["element_id"])'
    )

    with open(orset_path, "w") as f:
        f.write(content)

    # Fix 5: conflict_detector.py - use > instead of >=
    conflict_path = os.path.join(runtime_dir, "conflict_detector.py")
    with open(conflict_path, "r") as f:
        content = f.read()

    content = content.replace(
        "if write_count >= threshold:",
        "if write_count > threshold:"
    )

    with open(conflict_path, "w") as f:
        f.write(content)


if __name__ == "__main__":
    apply_fixes()

    sys.path.insert(0, "/app")
    from runtime.run_merge import main
    main()
