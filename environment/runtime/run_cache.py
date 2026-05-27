"""Cache eviction engine orchestrator.

Coordinates the multi-tier cache eviction workflow: loads configuration,
reads access logs, filters entries by tier, computes eviction scores,
and produces deterministic output files for downstream consumption.
"""

import configparser
import json
import logging
import os
from pathlib import Path
from typing import Dict, List

from runtime.analyzer import AccessLogAnalyzer
from runtime.evictor import EvictionEngine
from runtime.tier_filter import TierFilter


logger = logging.getLogger(__name__)

OUTPUT_DIR = Path("/app/runtime/output")
CONFIG_PATH = Path("/app/runtime/config.ini")


def load_configuration() -> configparser.ConfigParser:
    """Load and return the application configuration.

    Returns:
        ConfigParser instance with all sections loaded.

    Raises:
        FileNotFoundError: If config.ini is not found at the expected path.
    """
    config = configparser.ConfigParser()
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Configuration file not found: {CONFIG_PATH}")

    config.read(str(CONFIG_PATH))
    logger.info("Configuration loaded from %s", CONFIG_PATH)
    return config


def build_eviction_plan(results) -> List[Dict]:
    """Convert eviction results to serializable plan entries.

    Args:
        results: List of EvictionResult objects from the engine.

    Returns:
        List of dictionaries suitable for JSON serialization.
    """
    plan = []
    for result in results:
        plan.append({
            "entry_key": result.entry_key,
            "tier_name": result.tier_name,
            "eviction_score": result.eviction_score,
            "time_window": result.time_window,
            "hit_count": result.hit_count,
            "decision": result.decision,
        })
    return plan


def compute_eviction_rate(plan: List[Dict]) -> float:
    """Calculate the proportion of entries marked for eviction.

    Args:
        plan: List of eviction plan entries.

    Returns:
        Float between 0.0 and 1.0 representing eviction rate.
    """
    if not plan:
        return 0.0
    evicted = sum(1 for e in plan if e["decision"] == "evict")
    return round(evicted / len(plan), 4)


def build_cache_report(
    total_entries: int,
    plan: List[Dict],
    tier_summary: Dict[str, int],
    num_windows: int,
) -> Dict:
    """Build the summary cache report.

    Args:
        total_entries: Total number of entries loaded from access logs.
        plan: The eviction plan list.
        tier_summary: Mapping of tier names to entry counts.
        num_windows: Number of processing windows used.

    Returns:
        Dictionary containing report fields.
    """
    return {
        "total_entries": total_entries,
        "entries_evaluated": len(plan),
        "tiers_processed": sorted(tier_summary.keys()),
        "total_windows": num_windows,
        "eviction_rate": compute_eviction_rate(plan),
        "entries_per_tier": tier_summary,
    }


def run_cache_engine():
    """Execute the full cache eviction workflow.

    Steps:
        1. Load configuration from config.ini
        2. Initialize and run the access log analyzer
        3. Filter entries through the tier filter
        4. Compute eviction scores and schedule evictions
        5. Build and sort the eviction plan
        6. Write output files (eviction_plan.json, cache_report.json)
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    logger.info("Starting cache eviction engine")

    config = load_configuration()

    analyzer = AccessLogAnalyzer(config)
    all_entries = analyzer.load_all_logs()
    logger.info("Loaded %d total cache entries", len(all_entries))

    tier_filter = TierFilter(config)
    filtered_entries = tier_filter.filter_entries(all_entries)
    logger.info(
        "Tier filtering complete: %d of %d entries passed",
        len(filtered_entries),
        len(all_entries),
    )

    engine = EvictionEngine(config)
    eviction_results = engine.schedule_evictions(filtered_entries)

    eviction_plan = build_eviction_plan(eviction_results)

    # Note: entry_key is only unique within a tier
    eviction_plan.sort(key=lambda e: (e["eviction_score"], e["entry_key"]))

    tier_summary = tier_filter.get_tier_summary(filtered_entries)
    window_size = max(len(filtered_entries) // 3, 1)
    num_windows = len(
        [filtered_entries[i:i + window_size]
         for i in range(0, len(filtered_entries), window_size)]
    )

    report = build_cache_report(
        total_entries=len(all_entries),
        plan=eviction_plan,
        tier_summary=tier_summary,
        num_windows=num_windows,
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    plan_path = OUTPUT_DIR / "eviction_plan.json"
    with open(plan_path, "w") as f:
        json.dump(eviction_plan, f, indent=2)
    logger.info("Eviction plan written to %s (%d entries)", plan_path, len(eviction_plan))

    report_path = OUTPUT_DIR / "cache_report.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    logger.info("Cache report written to %s", report_path)

    logger.info("Cache eviction engine completed successfully")


if __name__ == "__main__":
    run_cache_engine()
