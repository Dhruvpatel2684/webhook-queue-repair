"""
Projection engine for building materialized views from event streams.

Applies projection rules to events, handling multiple merge modes
(sum, max, last_write) and priority-based conflict resolution when
multiple projections target the same view key and field.
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional, Set, Tuple

import yaml

from .models import Event, ProcessingMetrics, Projection, ProjectionRule

logger = logging.getLogger(__name__)

# Supported merge modes for projection aggregation
SUPPORTED_MERGE_MODES = {"sum", "max", "last_write", "min", "count"}

# Schema validation constraints
MAX_VIEW_KEY_LENGTH = 256
MAX_FIELD_NAME_LENGTH = 128
VALID_PRIORITY_RANGE = (1, 100)


class ProjectionSchemaError(Exception):
    """Raised when projection rules fail schema validation."""

    def __init__(self, rule_index: int, field: str, message: str):
        self.rule_index = rule_index
        self.field = field
        super().__init__(
            f"Rule #{rule_index} field '{field}': {message}"
        )


def validate_projection_rules(rules: List[Dict[str, Any]]) -> List[ProjectionRule]:
    """
    Validate and parse raw projection rule definitions from config.

    Performs comprehensive schema validation including type checks,
    value range constraints, and cross-rule consistency verification.

    Args:
        rules: Raw rule dictionaries from YAML config

    Returns:
        List of validated ProjectionRule objects

    Raises:
        ProjectionSchemaError: If any rule fails validation
    """
    parsed_rules = []
    seen_combinations: Set[Tuple[str, str, str]] = set()

    for idx, rule in enumerate(rules):
        # Check required fields
        required = {
            "source_stream", "event_type", "target_view",
            "target_field", "merge_mode", "priority", "payload_field"
        }
        missing = required - set(rule.keys())
        if missing:
            raise ProjectionSchemaError(idx, str(missing), "Missing required fields")

        # Validate merge mode
        if rule["merge_mode"] not in SUPPORTED_MERGE_MODES:
            raise ProjectionSchemaError(
                idx, "merge_mode",
                f"Unsupported mode '{rule['merge_mode']}'. "
                f"Valid modes: {SUPPORTED_MERGE_MODES}"
            )

        # Validate priority range
        priority = rule["priority"]
        if not isinstance(priority, int):
            raise ProjectionSchemaError(idx, "priority", "Must be an integer")
        if not (VALID_PRIORITY_RANGE[0] <= priority <= VALID_PRIORITY_RANGE[1]):
            raise ProjectionSchemaError(
                idx, "priority",
                f"Must be between {VALID_PRIORITY_RANGE[0]} and {VALID_PRIORITY_RANGE[1]}"
            )

        # Validate string field lengths
        if len(rule["target_view"]) > MAX_VIEW_KEY_LENGTH:
            raise ProjectionSchemaError(
                idx, "target_view",
                f"Exceeds max length of {MAX_VIEW_KEY_LENGTH}"
            )
        if len(rule["target_field"]) > MAX_FIELD_NAME_LENGTH:
            raise ProjectionSchemaError(
                idx, "target_field",
                f"Exceeds max length of {MAX_FIELD_NAME_LENGTH}"
            )

        # Track for cross-rule validation
        combo = (rule["source_stream"], rule["event_type"], rule["target_field"])
        if combo in seen_combinations:
            logger.warning(
                "Duplicate rule combination at index %d: %s - "
                "priority resolution will apply",
                idx, combo
            )
        seen_combinations.add(combo)

        parsed_rules.append(ProjectionRule(
            source_stream=rule["source_stream"],
            event_type=rule["event_type"],
            target_view=rule["target_view"],
            target_field=rule["target_field"],
            merge_mode=rule["merge_mode"],
            priority=rule["priority"],
            payload_field=rule["payload_field"],
        ))

    logger.info("Validated %d projection rules", len(parsed_rules))
    return parsed_rules


def load_projection_rules(config_path: str) -> List[ProjectionRule]:
    """
    Load projection rules from a YAML configuration file.

    Args:
        config_path: Path to the projections.yaml file

    Returns:
        Validated list of ProjectionRule objects
    """
    logger.info("Loading projection rules from: %s", config_path)

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    if "projections" not in config:
        raise ValueError("Config must contain 'projections' key")

    rules = config["projections"]
    if not isinstance(rules, list):
        raise ValueError("'projections' must be a list of rule definitions")

    return validate_projection_rules(rules)


def apply_merge_mode(
    current_value: float, new_value: float, mode: str
) -> float:
    """
    Apply the specified merge mode to combine current and new values.

    Merge modes:
    - sum: Add new value to current
    - max: Keep the larger value
    - min: Keep the smaller value
    - last_write: Replace current with new value (most recent wins)
    - count: Increment current by 1

    Args:
        current_value: Existing aggregated value
        new_value: New value from the event
        mode: The merge mode to apply

    Returns:
        The resulting merged value
    """
    if mode == "sum":
        return current_value + new_value
    elif mode == "max":
        return max(current_value, new_value)
    elif mode == "min":
        return min(current_value, new_value)
    elif mode == "last_write":
        return max(current_value, new_value)
    elif mode == "count":
        return current_value + 1
    else:
        logger.error("Unknown merge mode: %s, defaulting to last_write", mode)
        return new_value


def resolve_priority_conflict(
    existing: Projection, new_projection: Projection
) -> Projection:
    """
    Resolve conflicts when two projections target the same view key and field.

    Higher priority values indicate more authoritative sources that should
    take precedence. When priorities are equal, the existing value is kept.

    Args:
        existing: The current projection for this view_key+field
        new_projection: The incoming projection claiming the same slot

    Returns:
        The winning projection
    """
    if new_projection.priority < existing.priority:
        logger.debug(
            "Priority resolution for %s.%s: new (pri=%d) wins over existing (pri=%d)",
            existing.view_key, existing.field_name,
            new_projection.priority, existing.priority
        )
        return new_projection
    return existing


def build_projections(
    events: List[Event],
    rules: List[ProjectionRule],
    metrics: ProcessingMetrics,
) -> Dict[str, Projection]:
    """
    Build materialized view projections from events and rules.

    For each event, matching rules are found and applied. Values are
    aggregated according to the rule's merge mode. When multiple rules
    produce projections for the same view_key+field, priority resolution
    determines which value survives.

    Args:
        events: Deduplicated, windowed events
        rules: Projection rules from config
        metrics: Processing metrics collector

    Returns:
        Dictionary mapping "view_key:field_name" to Projection objects
    """
    projections: Dict[str, Projection] = {}
    match_count = 0
    conflict_count = 0

    logger.info(
        "Building projections from %d events with %d rules",
        len(events), len(rules)
    )

    for event in events:
        for rule in rules:
            if not rule.matches(event):
                continue

            match_count += 1

            # Extract value from event payload
            if rule.payload_field not in event.payload:
                logger.debug(
                    "Payload field '%s' not found in event %s:%d",
                    rule.payload_field, event.stream_id, event.seq
                )
                continue

            raw_value = event.payload[rule.payload_field]
            if not isinstance(raw_value, (int, float)):
                logger.warning(
                    "Non-numeric payload field '%s' = %s in event %s:%d",
                    rule.payload_field, raw_value, event.stream_id, event.seq
                )
                continue

            new_value = float(raw_value)
            projection_key = f"{rule.target_view}:{rule.target_field}"

            if projection_key in projections:
                existing = projections[projection_key]

                # Check if this is a priority conflict (different source)
                if existing.source_stream != rule.source_stream:
                    conflict_count += 1
                    candidate = Projection(
                        view_key=rule.target_view,
                        field_name=rule.target_field,
                        value=new_value,
                        merge_mode=rule.merge_mode,
                        priority=rule.priority,
                        source_stream=rule.source_stream,
                        source_event_type=rule.event_type,
                        last_updated_seq=event.seq,
                        update_count=1,
                    )
                    winner = resolve_priority_conflict(existing, candidate)
                    projections[projection_key] = winner
                else:
                    # Same source stream, apply merge mode
                    merged_value = apply_merge_mode(
                        existing.value, new_value, rule.merge_mode
                    )
                    existing.value = merged_value
                    existing.last_updated_seq = event.seq
                    existing.update_count += 1
            else:
                projections[projection_key] = Projection(
                    view_key=rule.target_view,
                    field_name=rule.target_field,
                    value=new_value,
                    merge_mode=rule.merge_mode,
                    priority=rule.priority,
                    source_stream=rule.source_stream,
                    source_event_type=rule.event_type,
                    last_updated_seq=event.seq,
                    update_count=1,
                )

    metrics.projections_created = len(projections)

    logger.info(
        "Projection build complete: %d projections from %d rule matches, "
        "%d priority conflicts resolved",
        len(projections), match_count, conflict_count
    )

    return projections


def write_projections(
    projections: Dict[str, Projection],
    output_directory: str,
    metrics: ProcessingMetrics,
):
    """
    Write projection results and metadata to JSON output files.

    Creates two files:
    - projections.json: The materialized view data
    - metadata.json: Processing statistics and event information

    Args:
        projections: Built projection dictionary
        output_directory: Directory to write output files
        metrics: Processing metrics to include in metadata
    """
    os.makedirs(output_directory, exist_ok=True)

    # Write projections
    projection_data = {}
    for key, proj in projections.items():
        projection_data[key] = {
            "view_key": proj.view_key,
            "field": proj.field_name,
            "value": proj.value,
            "merge_mode": proj.merge_mode,
            "priority": proj.priority,
            "source_stream": proj.source_stream,
            "source_event_type": proj.source_event_type,
            "last_updated_seq": proj.last_updated_seq,
            "update_count": proj.update_count,
        }

    projections_path = os.path.join(output_directory, "projections.json")
    with open(projections_path, "w", encoding="utf-8") as f:
        json.dump(projection_data, f, indent=2)

    logger.info("Wrote %d projections to %s", len(projection_data), projections_path)

    # Write metadata
    metadata = {
        "total_events_loaded": metrics.total_events_loaded,
        "events_after_dedup": metrics.events_after_dedup,
        "windows_processed": metrics.windows_processed,
        "projections_created": metrics.projections_created,
        "streams_processed": metrics.streams_processed,
        "errors": metrics.errors,
    }

    metadata_path = os.path.join(output_directory, "metadata.json")
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    logger.info("Wrote processing metadata to %s", metadata_path)
