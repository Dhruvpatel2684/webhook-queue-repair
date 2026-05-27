"""
Data models for the CQRS event projection system.

Defines the core structures used throughout the event processing
and materialized view generation workflow.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class Event:
    """Represents a single domain event from an event stream."""

    stream_id: str
    seq: int
    timestamp: float  # UTC epoch seconds
    version: int
    event_type: str
    payload: Dict[str, Any]
    raw_timestamp: str = ""
    source_file: str = ""

    def __post_init__(self):
        if not isinstance(self.seq, int):
            self.seq = int(self.seq)
        if not isinstance(self.version, int):
            self.version = int(self.version)


@dataclass
class Projection:
    """A materialized view projection record."""

    view_key: str
    field_name: str
    value: float
    merge_mode: str
    priority: int
    source_stream: str
    source_event_type: str
    last_updated_seq: int = 0
    update_count: int = 0

    def __repr__(self):
        return (
            f"Projection(view={self.view_key}, field={self.field_name}, "
            f"value={self.value}, mode={self.merge_mode}, pri={self.priority})"
        )


@dataclass
class WindowConfig:
    """Configuration for the sliding window processor."""

    size: int
    overlap: int

    def validate(self) -> bool:
        """Ensure window configuration is sensible."""
        if self.size <= 0:
            return False
        if self.overlap < 0:
            return False
        if self.overlap >= self.size:
            return False
        return True


@dataclass
class ProjectionRule:
    """A rule defining how events map to projections."""

    source_stream: str
    event_type: str
    target_view: str
    target_field: str
    merge_mode: str
    priority: int
    payload_field: str

    def matches(self, event: Event) -> bool:
        """Check if this rule applies to the given event."""
        return (
            event.stream_id == self.source_stream
            and event.event_type == self.event_type
        )


@dataclass
class ProcessingMetrics:
    """Tracks metrics during event processing."""

    total_events_loaded: int = 0
    events_after_dedup: int = 0
    windows_processed: int = 0
    projections_created: int = 0
    streams_processed: list = field(default_factory=list)
    errors: list = field(default_factory=list)
