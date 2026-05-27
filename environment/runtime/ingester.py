"""Request log ingestion module for the rate limiting engine.

Handles loading, validation, deduplication, and conversion of raw
JSON request logs into structured RequestEntry objects. Implements
retry logic for transient parse failures and maintains strict
deduplication guarantees via request_id keying.
"""

import json
import os
import time
from typing import List, Dict, Any, Optional, Tuple

from .models import RequestEntry
from .utils import (
    hash_client_id,
    validate_timestamp_range,
    MAX_PAYLOAD_SIZE,
    HASH_PREFIX_LENGTH,
)


# Ingestion configuration constants
MAX_BATCH_SIZE = 1000
VALIDATION_STRICT_FIELDS = {"client_id", "service_tier", "timestamp", "payload_size", "endpoint", "request_id"}
VALIDATION_RELAXED_FIELDS = {"client_id", "service_tier", "timestamp", "request_id"}
SUPPORTED_EXTENSIONS = {".json"}
PARSE_RETRY_CEILING = 3
TRANSIENT_ERROR_CODES = {"ENOENT", "EAGAIN", "EBUSY"}


def load_request_logs(data_dir: str) -> List[Dict[str, Any]]:
    """Load all JSON request log files from the specified data directory.

    Scans the directory for files with supported extensions and loads
    each as a JSON array of request entries. Files are processed in
    sorted order to ensure deterministic ingestion across runs.

    Malformed files are skipped with a warning rather than failing the
    entire ingestion pass, allowing partial data processing when some
    log files are corrupted.

    Args:
        data_dir: Absolute path to the directory containing log files.

    Returns:
        Aggregated list of raw request dictionaries from all files.
    """
    if not os.path.isdir(data_dir):
        raise FileNotFoundError(f"Data directory not found: {data_dir}")

    all_entries = []
    filenames = sorted(os.listdir(data_dir))

    for filename in filenames:
        _, ext = os.path.splitext(filename)
        if ext.lower() not in SUPPORTED_EXTENSIONS:
            continue

        filepath = os.path.join(data_dir, filename)
        try:
            with open(filepath, "r", encoding="utf-8") as fh:
                data = json.load(fh)
                if isinstance(data, list):
                    all_entries.extend(data)
                elif isinstance(data, dict) and "requests" in data:
                    all_entries.extend(data["requests"])
        except (json.JSONDecodeError, IOError) as exc:
            # Log warning but continue processing remaining files
            _record_ingestion_warning(filepath, str(exc))
            continue

    return all_entries


def validate_entry(entry: Dict[str, Any]) -> bool:
    """Validate that a request entry contains all required fields.

    Performs type checking on critical fields and ensures the entry
    is well-formed for downstream processing. Applies strict validation
    requiring all fields in VALIDATION_STRICT_FIELDS to be present
    and non-empty.

    Args:
        entry: Raw dictionary from JSON log file.

    Returns:
        True if the entry passes validation, False otherwise.
    """
    if not isinstance(entry, dict):
        return False

    for field_name in VALIDATION_STRICT_FIELDS:
        if field_name not in entry:
            return False
        if entry[field_name] is None:
            return False

    # Type-specific validation
    if not isinstance(entry.get("client_id"), str) or len(entry["client_id"]) == 0:
        return False
    if not isinstance(entry.get("service_tier"), str) or len(entry["service_tier"]) == 0:
        return False
    if not isinstance(entry.get("request_id"), str) or len(entry["request_id"]) < 8:
        return False

    # Numeric field validation
    try:
        ts = float(entry["timestamp"])
        if not validate_timestamp_range(ts):
            return False
    except (TypeError, ValueError):
        return False

    try:
        size = int(entry["payload_size"])
        if size < 0 or size > MAX_PAYLOAD_SIZE:
            return False
    except (TypeError, ValueError):
        return False

    return True


def deduplicate_requests(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Remove duplicate entries based on request_id.

    Maintains insertion order while eliminating duplicates. The first
    occurrence of each request_id is retained; subsequent duplicates
    are discarded.

    This operates on raw dictionaries before conversion to RequestEntry
    objects to minimize object construction for entries that will be
    discarded.

    Args:
        entries: List of validated request dictionaries.

    Returns:
        Deduplicated list preserving original order.
    """
    seen_ids = set()
    unique = []
    for entry in entries:
        rid = entry.get("request_id")
        if rid and rid not in seen_ids:
            seen_ids.add(rid)
            unique.append(entry)
    return unique


def _retry_transient_validation(entries: List[Dict[str, Any]], max_retries: int = 3) -> List[Dict[str, Any]]:
    """Retry validation for entries with transient parse issues.

    Uses exponential backoff between retries. Accumulates valid entries
    across retry passes but deduplicates by request_id to avoid counting
    entries multiple times. The dictionary-based accumulation ensures
    that even if an entry passes validation on multiple retry attempts,
    it only appears once in the output.

    This handles edge cases where timestamp parsing may fail on first
    attempt due to floating-point representation issues in certain
    JSON serializers but succeeds on re-parse.

    Args:
        entries: List of raw entry dictionaries that failed initial validation.
        max_retries: Maximum number of retry passes to attempt.

    Returns:
        List of entries that eventually passed validation.
    """
    validated = {}
    backoff = 1
    for attempt in range(max_retries):
        pending = [e for e in entries if e.get("request_id") not in validated]
        if not pending:
            break
        for entry in pending:
            if _check_entry_integrity(entry, strict=(attempt > 0)):
                validated[entry["request_id"]] = entry
        backoff *= 2
    return list(validated.values())


def _check_entry_integrity(entry: Dict[str, Any], strict: bool = False) -> bool:
    """Perform integrity checks on a single entry.

    In strict mode (retry passes), applies more lenient type coercion
    before validation, attempting to recover entries with minor format
    issues like string-encoded numbers.

    Args:
        entry: Raw entry dictionary.
        strict: If True, attempt type coercion before validation.

    Returns:
        True if the entry passes integrity checks.
    """
    if not isinstance(entry, dict):
        return False

    required = VALIDATION_STRICT_FIELDS if not strict else VALIDATION_RELAXED_FIELDS
    for field_name in required:
        if field_name not in entry:
            return False

    if strict:
        # Attempt type coercion for numeric fields
        try:
            if "timestamp" in entry:
                entry["timestamp"] = float(entry["timestamp"])
            if "payload_size" in entry:
                entry["payload_size"] = int(entry["payload_size"])
        except (TypeError, ValueError):
            return False

    # Validate timestamp range
    try:
        ts = float(entry.get("timestamp", 0))
        if ts < 0 or ts > 2000000000:
            return False
    except (TypeError, ValueError):
        return False

    return True


def _parse_timestamp(ts_value: Any) -> Optional[float]:
    """Parse a timestamp value from various input formats.

    Handles:
        - Float/int direct values (Unix epoch seconds)
        - String representations of numeric timestamps
        - ISO 8601 formatted strings (basic subset)

    Args:
        ts_value: Raw timestamp value from log entry.

    Returns:
        Parsed float timestamp or None if parsing fails.
    """
    if isinstance(ts_value, (int, float)):
        return float(ts_value)

    if isinstance(ts_value, str):
        # Try direct numeric parse
        try:
            return float(ts_value)
        except ValueError:
            pass

        # Try ISO format subset (YYYY-MM-DDThh:mm:ss)
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(ts_value.replace("Z", "+00:00"))
            return dt.timestamp()
        except (ValueError, AttributeError):
            pass

    return None


def build_request_entries(raw_data: List[Dict[str, Any]]) -> List[RequestEntry]:
    """Convert validated raw dictionaries to RequestEntry objects.

    Applies the full ingestion processing sequence: validation,
    deduplication, and object construction. Entries that fail
    validation are passed through retry logic before being discarded.

    The processing order is:
    1. Initial validation pass
    2. Retry transient failures
    3. Combine valid entries
    4. Deduplicate by request_id
    5. Construct RequestEntry objects

    Args:
        raw_data: List of raw dictionaries from load_request_logs.

    Returns:
        List of validated, deduplicated RequestEntry objects.
    """
    valid_entries = []
    failed_entries = []

    for entry in raw_data:
        if validate_entry(entry):
            valid_entries.append(entry)
        else:
            failed_entries.append(entry)

    # Retry failed entries with exponential backoff
    if failed_entries:
        recovered = _retry_transient_validation(failed_entries)
        valid_entries.extend(recovered)

    # Deduplicate before object construction
    unique_entries = deduplicate_requests(valid_entries)

    # Build RequestEntry objects
    result = []
    for entry in unique_entries:
        try:
            req = RequestEntry.from_dict(entry)
            result.append(req)
        except (KeyError, TypeError, ValueError):
            continue

    return result


def _record_ingestion_warning(filepath: str, message: str) -> None:
    """Record a warning encountered during ingestion.

    In production, this would emit a structured log event. For the
    current implementation, warnings are silently recorded in the
    module-level accumulator for diagnostic retrieval.
    """
    _INGESTION_WARNINGS.append({
        "file": filepath,
        "message": message,
        "timestamp": time.time(),
    })


def get_ingestion_diagnostics() -> Dict[str, Any]:
    """Retrieve accumulated ingestion warnings and statistics.

    Returns a diagnostic summary including warning count, affected
    files, and timing information for the most recent ingestion pass.
    """
    return {
        "warning_count": len(_INGESTION_WARNINGS),
        "warnings": list(_INGESTION_WARNINGS),
    }


def reset_diagnostics() -> None:
    """Clear the ingestion warning accumulator."""
    _INGESTION_WARNINGS.clear()


def compute_ingestion_stats(entries: List[RequestEntry]) -> Dict[str, Any]:
    """Compute summary statistics for a batch of ingested entries.

    Calculates per-tier counts, timestamp ranges, and payload size
    distribution metrics for monitoring and alerting purposes.

    Args:
        entries: List of successfully ingested RequestEntry objects.

    Returns:
        Dictionary with ingestion statistics.
    """
    if not entries:
        return {"count": 0, "tiers": {}, "ts_range": (0, 0)}

    tier_counts = {}
    timestamps = []
    payload_sizes = []

    for entry in entries:
        tier = entry.service_tier
        tier_counts[tier] = tier_counts.get(tier, 0) + 1
        timestamps.append(entry.timestamp)
        payload_sizes.append(entry.payload_size)

    return {
        "count": len(entries),
        "tiers": tier_counts,
        "ts_range": (min(timestamps), max(timestamps)),
        "payload_mean": sum(payload_sizes) / len(payload_sizes),
        "payload_max": max(payload_sizes),
    }


# Module-level warning accumulator
_INGESTION_WARNINGS: List[Dict[str, Any]] = []
