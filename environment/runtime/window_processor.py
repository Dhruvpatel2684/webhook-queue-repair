"""
Sliding window processor for event stream segmentation.

Processes events in overlapping windows based on sequence numbers,
handling boundary conditions, retry logic for transient failures,
and comprehensive processing metrics.
"""

import logging
import time
from typing import Callable, Dict, List, Optional, Tuple

from .models import Event, ProcessingMetrics, WindowConfig

logger = logging.getLogger(__name__)

# Constants for retry logic on transient processing failures
MAX_RETRY_ATTEMPTS = 3
INITIAL_RETRY_DELAY_MS = 100
RETRY_BACKOFF_MULTIPLIER = 2.0
TRANSIENT_ERROR_CODES = {"TIMEOUT", "RESOURCE_BUSY", "LOCK_CONTENTION"}


class WindowProcessingError(Exception):
    """Raised when a window cannot be processed after exhausting retries."""

    def __init__(self, window_id: int, reason: str):
        self.window_id = window_id
        self.reason = reason
        super().__init__(f"Window {window_id} processing failed: {reason}")


class RetryContext:
    """Manages retry state for transient failure handling."""

    def __init__(self, max_attempts: int = MAX_RETRY_ATTEMPTS):
        self.max_attempts = max_attempts
        self.attempt_count = 0
        self.last_error: Optional[str] = None
        self.total_delay_ms = 0

    def should_retry(self, error_code: str) -> bool:
        """Determine if the operation should be retried."""
        if error_code not in TRANSIENT_ERROR_CODES:
            return False
        if self.attempt_count >= self.max_attempts:
            return False
        return True

    def record_attempt(self, error_code: str):
        """Record a failed attempt and compute next delay."""
        self.attempt_count += 1
        self.last_error = error_code
        delay = INITIAL_RETRY_DELAY_MS * (
            RETRY_BACKOFF_MULTIPLIER ** (self.attempt_count - 1)
        )
        self.total_delay_ms += delay
        return delay

    def reset(self):
        """Reset retry state for next operation."""
        self.attempt_count = 0
        self.last_error = None


def sort_events_by_sequence(events: List[Event]) -> List[Event]:
    """
    Sort events by sequence number, with timestamp as tiebreaker.

    Args:
        events: Unsorted list of events

    Returns:
        New list sorted by (seq, timestamp)
    """
    return sorted(events, key=lambda e: (e.seq, e.timestamp))


def compute_window_boundaries(
    events: List[Event], config: WindowConfig
) -> List[Tuple[int, int]]:
    """
    Compute the start and end sequence numbers for each processing window.

    Windows slide forward by (size - overlap) events at a time.
    Each window covers events with sequence numbers in [start, end] inclusive.

    Args:
        events: Sorted list of events
        config: Window size and overlap configuration

    Returns:
        List of (window_start_seq, window_end_seq) tuples
    """
    if not events:
        return []

    if not config.validate():
        raise ValueError(f"Invalid window config: size={config.size}, overlap={config.overlap}")

    min_seq = events[0].seq
    max_seq = events[-1].seq
    step = config.size - config.overlap

    boundaries = []
    seq_start = min_seq

    while seq_start <= max_seq:
        # Compute inclusive window end boundary
        window_end = seq_start + config.size

        boundaries.append((seq_start, window_end))

        logger.debug(
            "Window %d: seq range [%d, %d]",
            len(boundaries), seq_start, window_end
        )

        seq_start += step

    logger.info(
        "Computed %d windows for %d events (size=%d, overlap=%d)",
        len(boundaries), len(events), config.size, config.overlap
    )
    return boundaries


def extract_window_events(
    events: List[Event], window_start: int, window_end: int
) -> List[Event]:
    """
    Extract events that fall within the given window boundaries.

    An event is included if its sequence number is >= window_start
    and <= window_end (inclusive on both ends).

    Args:
        events: Full sorted event list
        window_start: Inclusive lower bound of sequence numbers
        window_end: Inclusive upper bound of sequence numbers

    Returns:
        Subset of events within the window
    """
    window_events = []
    for event in events:
        if window_start <= event.seq <= window_end:
            window_events.append(event)
    return window_events


def process_window_with_retry(
    window_events: List[Event],
    window_id: int,
    processor_fn: Callable[[List[Event]], List[Event]],
    retry_ctx: Optional[RetryContext] = None,
) -> List[Event]:
    """
    Process a single window of events with retry capability.

    If a transient error occurs during processing, the operation
    is retried with exponential backoff up to the configured maximum.

    Args:
        window_events: Events in this window
        window_id: Numeric identifier for logging
        processor_fn: Function to apply to the window events
        retry_ctx: Optional retry context for failure handling

    Returns:
        Processed events from this window
    """
    if retry_ctx is None:
        retry_ctx = RetryContext()

    retry_ctx.reset()

    while True:
        try:
            result = processor_fn(window_events)
            logger.debug(
                "Window %d processed successfully: %d events in, %d events out",
                window_id, len(window_events), len(result)
            )
            return result
        except Exception as e:
            error_code = getattr(e, "code", "UNKNOWN")
            if retry_ctx.should_retry(error_code):
                delay = retry_ctx.record_attempt(error_code)
                logger.warning(
                    "Window %d transient failure (attempt %d/%d): %s. "
                    "Retrying in %dms...",
                    window_id, retry_ctx.attempt_count,
                    retry_ctx.max_attempts, error_code, delay
                )
                time.sleep(delay / 1000.0)
            else:
                raise WindowProcessingError(window_id, str(e)) from e


def process_all_windows(
    events: List[Event],
    config: WindowConfig,
    metrics: ProcessingMetrics,
) -> List[Event]:
    """
    Process all events through the sliding window mechanism.

    Events are sorted, windows are computed, and each window's events
    are extracted and collected. Events that appear in multiple windows
    due to overlap are included from each window they belong to, allowing
    downstream deduplication to handle identity resolution.

    Args:
        events: All events to process
        config: Window configuration
        metrics: Metrics collector

    Returns:
        All events after window processing (may include overlap duplicates)
    """
    sorted_events = sort_events_by_sequence(events)
    boundaries = compute_window_boundaries(sorted_events, config)

    all_processed = []

    retry_ctx = RetryContext()

    for idx, (w_start, w_end) in enumerate(boundaries):
        window_events = extract_window_events(sorted_events, w_start, w_end)

        if not window_events:
            logger.debug("Window %d is empty, skipping", idx + 1)
            continue

        # Use identity processor - windows just segment the stream
        processed = process_window_with_retry(
            window_events, idx + 1, lambda evts: evts, retry_ctx
        )

        all_processed.extend(processed)
        metrics.windows_processed += 1

        logger.info(
            "Window %d/%d: processed %d events (seq range [%d, %d])",
            idx + 1, len(boundaries), len(window_events), w_start, w_end
        )

    logger.info(
        "Window processing complete: %d total events after %d windows",
        len(all_processed), metrics.windows_processed
    )
    return all_processed
