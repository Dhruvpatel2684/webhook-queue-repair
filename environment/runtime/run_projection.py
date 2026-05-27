"""
Entry point for the CQRS event projection system.

Orchestrates the full event processing workflow:
1. Load configuration from engine.ini and projections.yaml
2. Discover and parse all event streams
3. Process events through sliding windows
4. Deduplicate events
5. Apply projection rules to build materialized views
6. Write output JSON files
"""

import configparser
import json
import logging
import os
import sys
import time
from typing import Dict, List

from .models import Event, ProcessingMetrics, WindowConfig
from .event_parser import load_all_events
from .window_processor import process_all_windows
from .dedup_engine import deduplicate_events
from .projection_engine import (
    build_projections,
    load_projection_rules,
    write_projections,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def load_engine_config(config_path: str) -> Dict:
    """
    Load engine configuration from INI file.

    Args:
        config_path: Path to engine.ini

    Returns:
        Dictionary of configuration sections and values
    """
    logger.info("Loading engine configuration from: %s", config_path)

    parser = configparser.ConfigParser()
    parser.read(config_path)

    config = {
        "window_size": parser.getint("processing", "window_size", fallback=10),
        "window_overlap": parser.getint("processing", "window_overlap", fallback=2),
        "dedup_enabled": parser.getboolean("processing", "dedup_enabled", fallback=True),
        "output_directory": parser.get("output", "directory", fallback="/app/runtime/output"),
        "output_format": parser.get("output", "format", fallback="json"),
        "log_level": parser.get("logging", "level", fallback="INFO"),
        "include_metrics": parser.getboolean("logging", "include_metrics", fallback=True),
    }

    logger.info(
        "Engine config: window_size=%d, overlap=%d, dedup=%s",
        config["window_size"], config["window_overlap"], config["dedup_enabled"]
    )

    return config


def collect_processing_summary(
    metrics: ProcessingMetrics, elapsed_ms: float
) -> Dict:
    """
    Build a summary of the processing run for logging.

    Args:
        metrics: Accumulated processing metrics
        elapsed_ms: Total processing time in milliseconds

    Returns:
        Summary dictionary
    """
    return {
        "total_events_loaded": metrics.total_events_loaded,
        "events_after_dedup": metrics.events_after_dedup,
        "windows_processed": metrics.windows_processed,
        "projections_created": metrics.projections_created,
        "streams_count": len(metrics.streams_processed),
        "error_count": len(metrics.errors),
        "elapsed_ms": round(elapsed_ms, 2),
    }


def run():
    """Execute the full projection processing workflow."""
    start_time = time.time()

    logger.info("=" * 60)
    logger.info("CQRS Event Projection System - Starting")
    logger.info("=" * 60)

    # Determine paths
    base_dir = os.path.dirname(os.path.abspath(__file__))
    config_dir = os.path.join(base_dir, "config")
    data_dir = os.path.join(base_dir, "data", "streams")

    engine_config_path = os.path.join(config_dir, "engine.ini")
    projections_config_path = os.path.join(config_dir, "projections.yaml")

    # Step 1: Load configuration
    config = load_engine_config(engine_config_path)
    rules = load_projection_rules(projections_config_path)

    # Update log level from config
    log_level = getattr(logging, config["log_level"].upper(), logging.INFO)
    logging.getLogger().setLevel(log_level)

    # Initialize metrics
    metrics = ProcessingMetrics()

    # Step 2: Load all events from stream files
    logger.info("Loading events from: %s", data_dir)
    all_events = load_all_events(data_dir)
    metrics.total_events_loaded = len(all_events)

    # Track which streams we processed
    stream_names = sorted(set(e.stream_id for e in all_events))
    metrics.streams_processed = stream_names
    logger.info("Streams found: %s", stream_names)

    # Step 3: Deduplicate events (remove exact duplicates from source)
    if config["dedup_enabled"]:
        deduped_events = deduplicate_events(all_events, metrics)
    else:
        deduped_events = all_events
        metrics.events_after_dedup = len(deduped_events)

    # Step 4: Process through sliding windows
    window_config = WindowConfig(
        size=config["window_size"],
        overlap=config["window_overlap"],
    )
    windowed_events = process_all_windows(deduped_events, window_config, metrics)

    # Step 5: Build projections
    projections = build_projections(windowed_events, rules, metrics)

    # Step 6: Write output
    write_projections(projections, config["output_directory"], metrics)

    # Processing complete
    elapsed_ms = (time.time() - start_time) * 1000
    summary = collect_processing_summary(metrics, elapsed_ms)

    logger.info("=" * 60)
    logger.info("Processing complete in %.1fms", elapsed_ms)
    logger.info("Summary: %s", json.dumps(summary, indent=2))
    logger.info("=" * 60)

    return summary


if __name__ == "__main__":
    run()
