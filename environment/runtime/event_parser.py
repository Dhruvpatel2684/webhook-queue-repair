"""
Event parser module for loading and parsing event streams from JSONL files.

Handles custom ISO 8601 timestamp parsing with timezone offset conversion,
event validation, and stream file discovery.
"""

import json
import logging
import os
import re
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

from .models import Event

logger = logging.getLogger(__name__)

# Regex for ISO 8601 timestamps with timezone offsets
ISO_TIMESTAMP_PATTERN = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})"
    r"(?:\.(\d+))?"
    r"(?:Z|([+-])(\d{2}):(\d{2}))$"
)

REQUIRED_EVENT_FIELDS = {"stream_id", "seq", "timestamp", "version", "event_type", "payload"}
VALID_EVENT_TYPES = {
    "order_created", "order_updated", "order_completed", "order_cancelled",
    "payment_received", "payment_refunded", "payment_adjusted",
    "inventory_added", "inventory_removed", "inventory_adjusted",
    "shipment_created", "shipment_dispatched", "shipment_delivered",
    "return_initiated", "return_received", "return_processed",
}


def parse_iso_timestamp(ts_string: str) -> float:
    """
    Parse an ISO 8601 timestamp string and return UTC epoch seconds.

    Supports timezone offsets like +05:30, -08:00, and Z for UTC.
    Handles fractional seconds up to microsecond precision.

    Args:
        ts_string: ISO 8601 formatted timestamp string

    Returns:
        UTC epoch timestamp as float seconds
    """
    match = ISO_TIMESTAMP_PATTERN.match(ts_string)
    if not match:
        raise ValueError(f"Invalid ISO timestamp format: {ts_string}")

    year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
    hour, minute, second = int(match.group(4)), int(match.group(5)), int(match.group(6))

    # Handle fractional seconds
    microsecond = 0
    if match.group(7):
        frac = match.group(7)[:6].ljust(6, "0")
        microsecond = int(frac)

    local_ts = datetime(year, month, day, hour, minute, second, microsecond)

    # Handle timezone offset
    if match.group(8) is not None:
        sign = match.group(8)
        offset_h = int(match.group(9))
        offset_m = int(match.group(10))

        # Convert local time to UTC by applying the timezone offset
        if sign == "+":
            utc_ts = local_ts + timedelta(hours=offset_h, minutes=offset_m)
        else:
            utc_ts = local_ts - timedelta(hours=offset_h, minutes=offset_m)
    else:
        # Z suffix means already UTC
        utc_ts = local_ts

    epoch = datetime(1970, 1, 1)
    delta = utc_ts - epoch
    return delta.total_seconds()


def validate_event_payload(payload: dict, event_type: str) -> Tuple[bool, Optional[str]]:
    """
    Validate that the event payload contains expected fields for its type.

    Performs type checking on numeric fields and ensures required
    payload attributes are present based on the event type category.

    Args:
        payload: The event payload dictionary
        event_type: The event type string

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not isinstance(payload, dict):
        return False, "Payload must be a dictionary"

    if len(payload) == 0:
        return False, "Payload cannot be empty"

    # Validate numeric fields are actually numeric
    for key, value in payload.items():
        if key.endswith("_amount") or key.endswith("_count") or key.endswith("_total"):
            if not isinstance(value, (int, float)):
                return False, f"Field '{key}' must be numeric, got {type(value).__name__}"
            if value < 0 and not key.startswith("adjustment"):
                logger.warning(
                    "Negative value %.2f for field '%s' in event type '%s'",
                    value, key, event_type
                )

    # Check for category-specific required fields
    category = event_type.split("_")[0] if "_" in event_type else event_type
    category_requirements = {
        "order": ["order_id"],
        "payment": ["transaction_id"],
        "inventory": ["product_id"],
        "shipment": ["shipment_id"],
        "return": ["return_id"],
    }

    required = category_requirements.get(category, [])
    for field_name in required:
        if field_name not in payload:
            return False, f"Missing required field '{field_name}' for {event_type}"

    return True, None


def discover_stream_files(data_directory: str) -> List[str]:
    """
    Discover all JSONL stream files in the data directory.

    Args:
        data_directory: Path to the directory containing stream files

    Returns:
        Sorted list of absolute file paths to JSONL files
    """
    if not os.path.isdir(data_directory):
        raise FileNotFoundError(f"Stream data directory not found: {data_directory}")

    files = []
    for filename in os.listdir(data_directory):
        if filename.endswith(".jsonl"):
            files.append(os.path.join(data_directory, filename))

    files.sort()
    logger.info("Discovered %d stream files in %s", len(files), data_directory)
    return files


def load_events_from_file(filepath: str) -> List[Event]:
    """
    Load and parse all events from a single JSONL file.

    Skips comment lines (starting with #) and blank lines.
    Validates each event before including it in the result.

    Args:
        filepath: Absolute path to the JSONL file

    Returns:
        List of parsed and validated Event objects
    """
    events = []
    line_number = 0
    skipped_count = 0

    logger.info("Loading events from: %s", filepath)

    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line_number += 1
            line = line.strip()

            # Skip empty lines and comments
            if not line or line.startswith("#"):
                continue

            try:
                data = json.loads(line)
            except json.JSONDecodeError as e:
                logger.error("JSON parse error at %s:%d - %s", filepath, line_number, e)
                skipped_count += 1
                continue

            # Validate required fields
            missing = REQUIRED_EVENT_FIELDS - set(data.keys())
            if missing:
                logger.error(
                    "Missing fields %s at %s:%d", missing, filepath, line_number
                )
                skipped_count += 1
                continue

            # Validate event type
            if data["event_type"] not in VALID_EVENT_TYPES:
                logger.warning(
                    "Unknown event type '%s' at %s:%d - processing anyway",
                    data["event_type"], filepath, line_number
                )

            # Validate payload
            is_valid, error_msg = validate_event_payload(data["payload"], data["event_type"])
            if not is_valid:
                logger.error(
                    "Invalid payload at %s:%d - %s", filepath, line_number, error_msg
                )
                skipped_count += 1
                continue

            # Parse timestamp
            try:
                utc_epoch = parse_iso_timestamp(data["timestamp"])
            except ValueError as e:
                logger.error("Timestamp parse error at %s:%d - %s", filepath, line_number, e)
                skipped_count += 1
                continue

            event = Event(
                stream_id=data["stream_id"],
                seq=data["seq"],
                timestamp=utc_epoch,
                version=data["version"],
                event_type=data["event_type"],
                payload=data["payload"],
                raw_timestamp=data["timestamp"],
                source_file=os.path.basename(filepath),
            )
            events.append(event)

    if skipped_count > 0:
        logger.warning("Skipped %d invalid lines in %s", skipped_count, filepath)

    logger.info("Loaded %d events from %s", len(events), os.path.basename(filepath))
    return events


def load_all_events(data_directory: str) -> List[Event]:
    """
    Load events from all stream files in the data directory.

    Args:
        data_directory: Path to the streams directory

    Returns:
        Combined list of all events from all stream files
    """
    files = discover_stream_files(data_directory)
    all_events = []

    for filepath in files:
        events = load_events_from_file(filepath)
        all_events.extend(events)

    logger.info(
        "Total events loaded from %d streams: %d",
        len(files), len(all_events)
    )
    return all_events
