"""Repair script for the priority-based task scheduling engine.

Applies targeted patches to fix four interacting bugs:
1. Strip whitespace from priority level parsing in prioritizer.py
2. Read max_concurrent from correct config section in executor.py
3. Use assignment instead of accumulation for execution times in executor.py
4. Add queue_name to sort key in run_scheduler.py
"""

import subprocess
import sys


def read_file(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def write_file(path: str, content: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def fix_priority_parsing():
    """Fix Bug A: strip whitespace from comma-separated priority levels."""
    path = "/app/runtime/prioritizer.py"
    content = read_file(path)
    old = 'config.get("scheduler", "priority_levels").split(",")'
    new = (
        "level.strip() for level in "
        'config.get("scheduler", "priority_levels").split(",")'
    )
    content = content.replace(
        f"self._levels = set(\n            {old}\n        )",
        f"self._levels = set(\n            {new}\n        )",
    )
    write_file(path, content)
    print("Fixed: priority level whitespace stripping")


def fix_config_section():
    """Fix Bug B: read max_concurrent from scheduler.limits section."""
    path = "/app/runtime/executor.py"
    content = read_file(path)
    old = 'self._max_concurrent = config.getint("scheduler", "max_concurrent")'
    new = 'self._max_concurrent = config.getint("scheduler.limits", "max_concurrent")'
    content = content.replace(old, new)
    write_file(path, content)
    print("Fixed: max_concurrent config section reference")


def fix_execution_time_accumulation():
    """Fix Bug C: use assignment instead of += for execution_time."""
    path = "/app/runtime/executor.py"
    content = read_file(path)
    old = 'results[job.job_id]["execution_time"] += duration'
    new = 'results[job.job_id]["execution_time"] = duration'
    content = content.replace(old, new)
    write_file(path, content)
    print("Fixed: execution_time accumulation replaced with assignment")


def fix_sort_key():
    """Fix Bug D: add queue_name to sort key for deterministic ordering."""
    path = "/app/runtime/run_scheduler.py"
    content = read_file(path)
    old = 'scheduled.sort(key=lambda j: (j["priority"], j["job_id"]))'
    new = 'scheduled.sort(key=lambda j: (j["priority"], j["queue_name"], j["job_id"]))'
    content = content.replace(old, new)
    write_file(path, content)
    print("Fixed: sort key includes queue_name for deterministic ordering")


def rerun_scheduler():
    """Re-run the scheduling engine after applying fixes."""
    result = subprocess.run(
        ["python3", "-m", "runtime.run_scheduler"],
        cwd="/app",
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"Scheduler failed: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    print("Scheduler re-run completed successfully")


if __name__ == "__main__":
    fix_priority_parsing()
    fix_config_section()
    fix_execution_time_accumulation()
    fix_sort_key()
    rerun_scheduler()
