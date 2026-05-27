"""Repair script for the multi-tier cache eviction engine.

Applies four patches to fix interacting bugs in the cache eviction system,
then re-runs the engine to produce corrected output.
"""

import subprocess
import sys


def read_file(path):
    with open(path, "r") as f:
        return f.read()


def write_file(path, content):
    with open(path, "w") as f:
        f.write(content)


def fix_tier_parsing():
    """Fix A: Strip whitespace from tier names during config parsing."""
    path = "/app/runtime/tier_filter.py"
    content = read_file(path)
    old = 'self._tiers = set(config.get("cache", "cache_tiers").split(","))'
    new = 'self._tiers = set(t.strip() for t in config.get("cache", "cache_tiers").split(","))'
    if old in content:
        content = content.replace(old, new)
        write_file(path, content)
        print("Fixed: tier whitespace stripping in tier_filter.py")
    else:
        print("Warning: tier parsing fix pattern not found")


def fix_eviction_threshold():
    """Fix B: Read eviction_threshold from cache.policy section."""
    path = "/app/runtime/evictor.py"
    content = read_file(path)
    old = 'self._threshold = config.getint("cache", "eviction_threshold")'
    new = 'self._threshold = config.getint("cache.policy", "eviction_threshold")'
    if old in content:
        content = content.replace(old, new)
        write_file(path, content)
        print("Fixed: eviction threshold reads from cache.policy section")
    else:
        print("Warning: eviction threshold fix pattern not found")


def fix_hit_count_accumulation():
    """Fix C: Use assignment instead of accumulation for hit counts."""
    path = "/app/runtime/evictor.py"
    content = read_file(path)
    old = 'results[entry.entry_key]["hit_count"] += hits'
    new = 'results[entry.entry_key]["hit_count"] = hits'
    if old in content:
        content = content.replace(old, new)
        write_file(path, content)
        print("Fixed: hit_count uses assignment instead of accumulation")
    else:
        print("Warning: hit count accumulation fix pattern not found")


def fix_sort_ordering():
    """Fix D: Add tier_name to eviction plan sort key."""
    path = "/app/runtime/run_cache.py"
    content = read_file(path)
    old = 'eviction_plan.sort(key=lambda e: (e["eviction_score"], e["entry_key"]))'
    new = 'eviction_plan.sort(key=lambda e: (e["eviction_score"], e["tier_name"], e["entry_key"]))'
    if old in content:
        content = content.replace(old, new)
        write_file(path, content)
        print("Fixed: sort key includes tier_name for deterministic ordering")
    else:
        print("Warning: sort ordering fix pattern not found")


def main():
    print("Applying cache eviction engine repairs...")
    print()

    fix_tier_parsing()
    fix_eviction_threshold()
    fix_hit_count_accumulation()
    fix_sort_ordering()

    print()
    print("All patches applied. Re-running cache engine...")
    print()

    result = subprocess.run(
        ["python3", "-m", "runtime.run_cache"],
        cwd="/app",
        capture_output=True,
        text=True,
    )

    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)

    if result.returncode != 0:
        print(f"Engine failed with exit code {result.returncode}", file=sys.stderr)
        sys.exit(result.returncode)

    print("Cache eviction engine repair completed successfully.")


if __name__ == "__main__":
    main()
