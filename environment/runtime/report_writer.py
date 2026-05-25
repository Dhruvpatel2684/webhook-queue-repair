"""Write scheduling results to output files."""

import json
import os


def write_reports(schedule_result, category_summaries, output_dir):
    """Write schedule and report JSON files to output directory.

    Creates:
        schedule.json - full scheduling output with phases and assignments
        report.json - category summaries and statistics
    """
    os.makedirs(output_dir, exist_ok=True)

    schedule_output = {
        "total_phases": schedule_result["total_phases"],
        "total_scheduled": len(schedule_result["scheduled"]),
        "total_rejected": len(schedule_result["rejected"]),
        "total_blocked": len(schedule_result["blocked"]),
        "assignments": schedule_result["scheduled"],
        "rejected_passes": schedule_result["rejected"],
        "blocked_passes": schedule_result["blocked"],
    }

    schedule_path = os.path.join(output_dir, "schedule.json")
    with open(schedule_path, "w") as f:
        json.dump(schedule_output, f, indent=2)

    report_output = {
        "category_summaries": category_summaries,
        "statistics": {
            "total_passes_processed": (
                len(schedule_result["scheduled"])
                + len(schedule_result["rejected"])
                + len(schedule_result["blocked"])
            ),
            "total_phases": schedule_result["total_phases"],
            "scheduling_complete": True,
        },
    }

    report_path = os.path.join(output_dir, "report.json")
    with open(report_path, "w") as f:
        json.dump(report_output, f, indent=2)

    return schedule_path, report_path
