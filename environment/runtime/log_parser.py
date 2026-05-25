"""
Log Parser Module
Parses webhook delivery logs into structured event records.
Handles REGISTER, DEPENDENCY, ATTEMPT, SUCCESS, FAILURE, and DEAD_LETTER events.

This module is correct — no bugs here.
"""

import os

LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "delivery_logs.txt")


def parse_payload(payload_str):
    """Parse comma-separated key=value pairs into a dict."""
    result = {}
    for pair in payload_str.split(","):
        if "=" in pair:
            key, value = pair.split("=", 1)
            result[key.strip()] = value.strip()
    return result


def parse_log_line(line):
    """Parse a single log line into a structured event dict."""
    line = line.strip()
    if not line or line.startswith("#"):
        return None

    parts = line.split("|")
    if len(parts) != 4:
        return None

    timestamp_str, webhook_id, event_type, payload_str = parts

    return {
        "timestamp": int(timestamp_str),
        "webhook_id": webhook_id,
        "event_type": event_type,
        "payload": parse_payload(payload_str),
    }


def load_events(log_path=None):
    """Load all events from the log file, ordered by timestamp."""
    if log_path is None:
        log_path = LOG_FILE

    events = []
    with open(log_path, "r") as f:
        for line in f:
            event = parse_log_line(line)
            if event is not None:
                events.append(event)

    events.sort(key=lambda e: e["timestamp"])
    return events
