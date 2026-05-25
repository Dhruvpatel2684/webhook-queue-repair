"""
Report Writer Module
Produces output files from scheduling results and pool summaries.

Output files:
  - schedule.json: ordered list of job assignments with round numbers
  - pool_report.json: per-pool resource allocation statistics
"""

import json
import hashlib
import os

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")


def compute_schedule_digest(pool_summaries, total_scheduled, total_rejected):
    """
    Compute a deterministic digest of the scheduling result.
    Iterates pools in sorted order and includes scheduling totals
    for a stable integrity hash.
    """
    digest_input = ""
    for pool_id in sorted(pool_summaries.keys()):
        ps = pool_summaries[pool_id]
        digest_input += f"{pool_id}:{ps['job_count']}:{ps['avg_cpu']}|"
    digest_input += f"scheduled:{total_scheduled}:rejected:{total_rejected}"
    return hashlib.sha256(digest_input.encode()).hexdigest()[:16]


def write_schedule(scheduled, rejected):
    """Write job schedule assignments to output JSON file."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    outpath = os.path.join(OUTPUT_DIR, "schedule.json")

    schedule_entries = []
    for job, round_num in scheduled:
        schedule_entries.append({
            "job_id": job["job_id"],
            "queue_name": job["queue_name"],
            "priority": job["priority"],
            "resource_pool": job["resource_pool"],
            "round": round_num,
        })

    rejected_entries = []
    for job in rejected:
        rejected_entries.append({
            "job_id": job["job_id"],
            "queue_name": job["queue_name"],
            "resource_pool": job["resource_pool"],
            "reason": "invalid_pool",
        })

    output = {
        "total_scheduled": len(scheduled),
        "total_rejected": len(rejected),
        "total_rounds": max((r for _, r in scheduled), default=0),
        "assignments": schedule_entries,
        "rejected": rejected_entries,
    }

    with open(outpath, "w") as f:
        json.dump(output, f, indent=2)
    return outpath


def write_pool_report(pool_summaries, total_scheduled, total_rejected):
    """Write pool allocation report to output JSON file."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    outpath = os.path.join(OUTPUT_DIR, "pool_report.json")

    digest = compute_schedule_digest(pool_summaries, total_scheduled, total_rejected)

    pools_list = []
    for pool_id in sorted(pool_summaries.keys()):
        pools_list.append(pool_summaries[pool_id])

    output = {
        "total_pools": len(pool_summaries),
        "total_scheduled": total_scheduled,
        "total_rejected": total_rejected,
        "schedule_digest": digest,
        "pools": pools_list,
    }

    with open(outpath, "w") as f:
        json.dump(output, f, indent=2)
    return outpath
