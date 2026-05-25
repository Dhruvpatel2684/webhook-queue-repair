"""Repair the compiler pass scheduler by patching dependency_resolver.py and phase_aggregator.py."""

import os


def patch_dependency_resolver():
    """Apply fixes to dependency_resolver.py:
    - Fix A: strip whitespace from category names after split
    - Fix B: read phase_capacity from [passes.optimized] section
    - Fix D: sort by module_name instead of pass_id for stable tiebreaking
    - Fix E: use > instead of >= for chain depth threshold
    """
    filepath = "/app/runtime/dependency_resolver.py"
    with open(filepath, "r") as f:
        content = f.read()

    # Fix A: strip categories
    content = content.replace(
        "active_categories = active_raw.split(\",\")",
        "active_categories = [c.strip() for c in active_raw.split(\",\")]"
    )

    # Fix B: use passes.optimized section for phase_capacity
    content = content.replace(
        "phase_capacity = config.getint(\"passes\", \"phase_capacity\")",
        "phase_capacity = config.getint(\"passes.optimized\", \"phase_capacity\")"
    )

    # Fix E: change >= to > for chain depth check
    content = content.replace(
        "if chain_depth >= max_chain_depth:",
        "if chain_depth > max_chain_depth:"
    )

    # Fix D: sort by module_name instead of pass_id
    content = content.replace(
        "key=lambda x: (-x[\"priority\"], x[\"submitted_order\"], x[\"pass_id\"])",
        "key=lambda x: (-x[\"priority\"], x[\"submitted_order\"], x[\"module_name\"])"
    )

    with open(filepath, "w") as f:
        f.write(content)


def patch_phase_aggregator():
    """Apply fixes to phase_aggregator.py:
    - Fix C: use last-write-wins instead of accumulation for phase summaries
    """
    filepath = "/app/runtime/phase_aggregator.py"
    with open(filepath, "r") as f:
        content = f.read()

    # Fix C: change accumulation to last-write-wins for count and cost
    content = content.replace(
        "category_summaries[cat][\"total_passes\"] += metrics[\"count\"]",
        "category_summaries[cat][\"total_passes\"] = metrics[\"count\"]"
    )
    content = content.replace(
        "category_summaries[cat][\"total_cost_ms\"] += metrics[\"cost\"]",
        "category_summaries[cat][\"total_cost_ms\"] = metrics[\"cost\"]"
    )

    with open(filepath, "w") as f:
        f.write(content)


if __name__ == "__main__":
    patch_dependency_resolver()
    patch_phase_aggregator()

    # Re-run the scheduler with fixes applied
    import importlib
    import sys

    # Remove cached modules to pick up changes
    mods_to_remove = [k for k in sys.modules if k.startswith("runtime")]
    for mod in mods_to_remove:
        del sys.modules[mod]

    from runtime.run_passes import main
    main()
