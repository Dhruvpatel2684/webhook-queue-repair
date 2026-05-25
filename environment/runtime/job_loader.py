"""
Job Loader Module
Reads job manifest CSV files and produces a unified job stream.
Each queue file represents a distinct workload category.
"""

import csv
import os
import glob

DATA_DIR = os.path.dirname(os.path.abspath(__file__))


def load_queue_file(filepath):
    """Load a single queue CSV file into a list of job dicts."""
    jobs = []
    with open(filepath, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            jobs.append({
                "job_id": row["job_id"],
                "queue_name": row["queue_name"],
                "priority": int(row["priority"]),
                "resource_pool": row["resource_pool"],
                "cpu_units": int(row["cpu_units"]),
                "memory_mb": int(row["memory_mb"]),
                "submitted_at": int(row["submitted_at"]),
                "estimated_runtime_sec": int(row["estimated_runtime_sec"]),
            })
    return jobs


def load_all_jobs():
    """Load jobs from all queue CSV files in the data directory."""
    all_jobs = []
    pattern = os.path.join(DATA_DIR, "queue_*.csv")
    for filepath in sorted(glob.glob(pattern)):
        jobs = load_queue_file(filepath)
        all_jobs.extend(jobs)
    # Sort by submitted_at for temporal ordering
    all_jobs.sort(key=lambda j: j["submitted_at"])
    return all_jobs
