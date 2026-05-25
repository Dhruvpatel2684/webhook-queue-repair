"""Aggregate phase-level metrics into category summaries."""


def aggregate_phase_summaries(schedule_result):
    """Produce final per-category summaries from phase snapshots.

    Each phase contributes a snapshot of category metrics. The aggregator
    processes all phases and produces a single summary per category.

    Returns:
        list of dicts with keys: category, total_passes, total_cost_ms, phases_active
    """
    active_raw = set()
    phase_snapshots = {}

    scheduled = schedule_result["scheduled"]
    total_phases = schedule_result["total_phases"]

    for entry in scheduled:
        cat = entry["category"]
        phase = entry["phase"]
        active_raw.add(cat)

        if phase not in phase_snapshots:
            phase_snapshots[phase] = {}

        if cat not in phase_snapshots[phase]:
            phase_snapshots[phase][cat] = {"count": 0, "cost": 0}

        phase_snapshots[phase][cat]["count"] += 1
        phase_snapshots[phase][cat]["cost"] += entry["estimated_cost_ms"]

    category_summaries = {}
    for phase_num in sorted(phase_snapshots.keys()):
        snapshot = phase_snapshots[phase_num]
        for cat, metrics in snapshot.items():
            if cat not in category_summaries:
                category_summaries[cat] = {
                    "total_passes": 0,
                    "total_cost_ms": 0,
                    "phases_active": 0,
                }
            category_summaries[cat]["total_passes"] += metrics["count"]
            category_summaries[cat]["total_cost_ms"] += metrics["cost"]
            category_summaries[cat]["phases_active"] += 1

    result = []
    for cat in sorted(category_summaries.keys()):
        summary = category_summaries[cat]
        result.append({
            "category": cat,
            "total_passes": summary["total_passes"],
            "total_cost_ms": summary["total_cost_ms"],
            "phases_active": summary["phases_active"],
        })

    return result
