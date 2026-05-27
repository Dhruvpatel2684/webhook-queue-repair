"""Entry point for the multi-tenant rate limiting engine.

Orchestrates the complete rate limiting workflow: configuration loading,
request ingestion, tier classification, throttle evaluation, and report
generation. Produces two output artifacts: throttle_plan.json containing
individual throttle decisions, and limiter_report.json with aggregate
metrics.
"""

import json
import os
import sys
import time
from configparser import ConfigParser
from typing import List, Dict, Any

from .ingester import load_request_logs, build_request_entries, compute_ingestion_stats
from .classifier import (
    classify_requests,
    get_active_tiers,
    filter_by_evaluation_mode,
    compute_request_rate,
    compute_tier_window_distribution,
)
from .throttler import apply_throttling
from .reporter import generate_report, write_report, aggregate_window_metrics
from .models import ThrottleDecision, LimiterReport
from .utils import compute_window_span


# Path constants
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.ini")
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
THROTTLE_PLAN_FILENAME = "throttle_plan.json"
REPORT_FILENAME = "limiter_report.json"


def load_configuration(config_path: str) -> ConfigParser:
    """Load and parse the limiter configuration file.

    Reads the INI-format configuration and returns a ConfigParser
    instance. Raises FileNotFoundError if the configuration file
    is missing.

    Args:
        config_path: Absolute path to the configuration INI file.

    Returns:
        Parsed ConfigParser instance.
    """
    if not os.path.isfile(config_path):
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    config = ConfigParser()
    config.read(config_path, encoding="utf-8")
    return config


def ensure_output_directory(output_dir: str) -> None:
    """Create the output directory if it does not exist.

    Args:
        output_dir: Path to the output directory.
    """
    if not os.path.isdir(output_dir):
        os.makedirs(output_dir, exist_ok=True)


def write_throttle_plan(decisions: List[ThrottleDecision], output_path: str) -> None:
    """Serialize throttle decisions to JSON output file.

    Writes the complete list of throttle decisions as a JSON array
    with consistent formatting for downstream consumption.

    Args:
        decisions: Ordered list of ThrottleDecision objects.
        output_path: Absolute path for the output file.
    """
    serialized = [d.to_dict() for d in decisions]

    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.isdir(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(serialized, fh, indent=2)


def run_engine() -> None:
    """Execute the complete rate limiting engine workflow.

    Sequence:
    1. Load configuration from config.ini
    2. Ingest request logs from data directory
    3. Classify requests by service tier
    4. Apply throttle evaluation
    5. Sort and write throttle plan
    6. Generate and write aggregate report
    """
    start_time = time.time()

    # Step 1: Load configuration
    config = load_configuration(CONFIG_PATH)
    evaluation_mode = config.get("limiter", "evaluation_mode")
    window_duration = config.getint("limiter", "window_duration")

    # Step 2: Ingest request logs
    raw_data = load_request_logs(DATA_DIR)
    entries = build_request_entries(raw_data)

    # Apply evaluation mode filtering
    entries = filter_by_evaluation_mode(entries, evaluation_mode)

    # Step 3: Classify by service tier
    classified = classify_requests(entries, config)

    # Compute window span for rate calculations
    all_timestamps = [e.timestamp for e in entries]
    window_count = compute_window_span(all_timestamps, window_duration)

    # Step 4: Apply throttling
    decisions = apply_throttling(classified, config)

    # Step 5: Sort results for deterministic output
    # Note: client_id is scoped to a service tier
    decisions.sort(key=lambda d: (d.throttle_score, d.client_id))

    # Step 6: Write outputs
    ensure_output_directory(OUTPUT_DIR)

    throttle_plan_path = os.path.join(OUTPUT_DIR, THROTTLE_PLAN_FILENAME)
    write_throttle_plan(decisions, throttle_plan_path)

    # Step 7: Generate and write report
    report = generate_report(decisions, classified, config)
    report_path = os.path.join(OUTPUT_DIR, REPORT_FILENAME)
    write_report(report, report_path)

    elapsed = time.time() - start_time
    _log_completion(report, elapsed)


def _log_completion(report: LimiterReport, elapsed: float) -> None:
    """Log engine completion summary to stderr.

    Outputs key metrics for operational visibility without
    polluting stdout which may be used for structured output.

    Args:
        report: The generated limiter report.
        elapsed: Wall-clock execution time in seconds.
    """
    sys.stderr.write(
        f"[limiter] completed in {elapsed:.3f}s | "
        f"requests={report.total_requests} | "
        f"classified={report.requests_classified} | "
        f"tiers={len(report.tiers_active)} | "
        f"throttle_rate={report.throttle_rate:.4f}\n"
    )


def validate_environment() -> bool:
    """Validate that the runtime environment is properly configured.

    Checks for the presence of required files and directories
    before starting the engine workflow.

    Returns:
        True if environment is valid, False otherwise.
    """
    checks = [
        os.path.isfile(CONFIG_PATH),
        os.path.isdir(DATA_DIR),
    ]
    return all(checks)


if __name__ == "__main__":
    if not validate_environment():
        sys.stderr.write("[limiter] environment validation failed\n")
        sys.exit(1)
    run_engine()
