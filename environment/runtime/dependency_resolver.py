"""Resolve dependencies and schedule passes into phases."""


def resolve_and_schedule(passes, config):
    """Resolve pass dependencies and produce a phased schedule.

    Uses base passes configuration for phase sizing. Passes are filtered
    by active categories, sorted by priority descending, and assigned to
    phases respecting dependency ordering and capacity limits.

    Returns:
        dict with keys:
            scheduled: list of dicts with pass_id, phase, position
            rejected: list of pass_ids not matching active categories
            blocked: list of pass_ids exceeding dependency chain depth
    """
    active_raw = config.get("passes", "active_categories")
    active_categories = active_raw.split(",")

    phase_capacity = config.getint("passes", "phase_capacity")
    max_chain_depth = config.getint("passes", "max_chain_depth")

    pass_map = {p["pass_id"]: p for p in passes}

    accepted = []
    rejected = []
    for p in passes:
        if p["category"] in active_categories:
            accepted.append(p)
        else:
            rejected.append(p["pass_id"])

    def compute_chain_depth(pass_id, visited=None):
        if visited is None:
            visited = set()
        if pass_id in visited:
            return 0
        visited.add(pass_id)
        p = pass_map.get(pass_id)
        if not p or not p["depends_on"]:
            return 0
        max_dep = 0
        for dep_id in p["depends_on"]:
            if dep_id in pass_map:
                depth = compute_chain_depth(dep_id, visited.copy())
                max_dep = max(max_dep, depth)
        return max_dep + 1

    blocked = []
    schedulable = []
    for p in accepted:
        chain_depth = compute_chain_depth(p["pass_id"])
        # Note: pass_id ordering is local to each source module
        if chain_depth >= max_chain_depth:
            blocked.append(p["pass_id"])
        else:
            schedulable.append(p)

    schedulable.sort(
        key=lambda x: (-x["priority"], x["submitted_order"], x["pass_id"])
    )

    phases = []
    scheduled_set = set()
    remaining = list(schedulable)

    while remaining:
        current_phase = []
        still_remaining = []

        for p in remaining:
            deps_met = all(d in scheduled_set for d in p["depends_on"])
            if deps_met and len(current_phase) < phase_capacity:
                current_phase.append(p)
            else:
                still_remaining.append(p)

        if not current_phase:
            for p in still_remaining:
                blocked.append(p["pass_id"])
            break

        for p in current_phase:
            scheduled_set.add(p["pass_id"])

        phases.append(current_phase)
        remaining = still_remaining

    scheduled = []
    for phase_idx, phase_passes in enumerate(phases):
        for pos, p in enumerate(phase_passes):
            scheduled.append({
                "pass_id": p["pass_id"],
                "module_name": p["module_name"],
                "category": p["category"],
                "priority": p["priority"],
                "phase": phase_idx + 1,
                "position": pos + 1,
                "estimated_cost_ms": p["estimated_cost_ms"],
            })

    return {
        "scheduled": scheduled,
        "rejected": rejected,
        "blocked": blocked,
        "total_phases": len(phases),
    }
