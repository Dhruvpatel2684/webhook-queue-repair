"""Data models for the multi-tenant rate limiting engine.

Defines the core data structures used across the ingestion, classification,
throttling, and reporting stages.
"""

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import List, Dict, Any


class ServiceTier(Enum):
    """Enumeration of available service tiers for rate limiting."""
    BASIC = "basic"
    STANDARD = "standard"
    PREMIUM = "premium"
    ENTERPRISE = "enterprise"

    @classmethod
    def from_string(cls, value: str) -> "ServiceTier":
        """Convert a string representation to a ServiceTier enum value."""
        normalized = value.strip().lower()
        for member in cls:
            if member.value == normalized:
                return member
        raise ValueError(f"Unknown service tier: {value!r}")


class Decision(Enum):
    """Possible throttle decisions for a request."""
    ALLOW = "allow"
    THROTTLE = "throttle"

    def __str__(self) -> str:
        return self.value


@dataclass
class RequestEntry:
    """Represents a single incoming API request log entry."""
    client_id: str
    service_tier: str
    timestamp: float
    payload_size: int
    endpoint: str
    request_id: str

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary representation."""
        return {
            "client_id": self.client_id,
            "service_tier": self.service_tier,
            "timestamp": self.timestamp,
            "payload_size": self.payload_size,
            "endpoint": self.endpoint,
            "request_id": self.request_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RequestEntry":
        """Construct a RequestEntry from a dictionary."""
        return cls(
            client_id=data["client_id"],
            service_tier=data["service_tier"],
            timestamp=float(data["timestamp"]),
            payload_size=int(data["payload_size"]),
            endpoint=data["endpoint"],
            request_id=data["request_id"],
        )


@dataclass
class ThrottleDecision:
    """Records the throttle decision for a client within a time window."""
    client_id: str
    service_tier: str
    throttle_score: float
    time_window: int
    tokens_used: int
    decision: str

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary representation."""
        return {
            "client_id": self.client_id,
            "service_tier": self.service_tier,
            "throttle_score": round(self.throttle_score, 4),
            "time_window": self.time_window,
            "tokens_used": self.tokens_used,
            "decision": self.decision,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ThrottleDecision":
        """Construct from a dictionary."""
        return cls(
            client_id=data["client_id"],
            service_tier=data["service_tier"],
            throttle_score=float(data["throttle_score"]),
            time_window=int(data["time_window"]),
            tokens_used=int(data["tokens_used"]),
            decision=data["decision"],
        )


@dataclass
class LimiterReport:
    """Aggregate report of the rate limiting engine output."""
    total_requests: int
    requests_classified: int
    tiers_active: List[str]
    total_windows: int
    throttle_rate: float
    requests_per_tier: Dict[str, int]

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary representation."""
        return {
            "total_requests": self.total_requests,
            "requests_classified": self.requests_classified,
            "tiers_active": sorted(self.tiers_active),
            "total_windows": self.total_windows,
            "throttle_rate": round(self.throttle_rate, 4),
            "requests_per_tier": self.requests_per_tier,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LimiterReport":
        """Construct from a dictionary."""
        return cls(
            total_requests=data["total_requests"],
            requests_classified=data["requests_classified"],
            tiers_active=data["tiers_active"],
            total_windows=data["total_windows"],
            throttle_rate=float(data["throttle_rate"]),
            requests_per_tier=data["requests_per_tier"],
        )


class TierCapacityMap:
    """Maps service tiers to their respective capacity multipliers.

    Each tier has a base multiplier applied to the global bucket capacity
    to determine the effective capacity for clients on that tier.
    """

    MULTIPLIERS = {
        ServiceTier.BASIC: 1.0,
        ServiceTier.STANDARD: 1.0,
        ServiceTier.PREMIUM: 1.0,
        ServiceTier.ENTERPRISE: 1.0,
    }

    @classmethod
    def get_effective_capacity(cls, tier: ServiceTier, base_capacity: int) -> int:
        """Calculate effective capacity for a given tier and base capacity."""
        multiplier = cls.MULTIPLIERS.get(tier, 1.0)
        return int(base_capacity * multiplier)

    @classmethod
    def get_multiplier(cls, tier_name: str) -> float:
        """Look up the multiplier for a tier by its string name."""
        try:
            tier_enum = ServiceTier.from_string(tier_name)
            return cls.MULTIPLIERS.get(tier_enum, 1.0)
        except ValueError:
            return 1.0
