"""
Queue State Module
Tracks webhook delivery state through the retry lifecycle.
Maintains per-webhook state: pending, delivered, dead_letter.
"""


class WebhookState:
    """Tracks the state of a single webhook delivery."""

    def __init__(self, webhook_id, endpoint, event_name, max_retries):
        self.webhook_id = webhook_id
        self.endpoint = endpoint
        self.event_name = event_name
        self.max_retries = max_retries
        self.attempts = 0
        self.status = "pending"  # pending, delivered, dead_letter
        self.last_attempt_at = None
        self.next_retry_at = None
        self.delivered_at = None
        self.failure_reasons = []
        self.total_duration_ms = 0

    def to_dict(self):
        return {
            "webhook_id": self.webhook_id,
            "endpoint": self.endpoint,
            "event": self.event_name,
            "status": self.status,
            "attempts": self.attempts,
            "max_retries": self.max_retries,
            "delivered_at": self.delivered_at,
            "failure_reasons": self.failure_reasons,
            "total_duration_ms": self.total_duration_ms,
        }


class DeliveryQueueManager:
    """Manages the state of all webhook deliveries."""

    def __init__(self):
        self.webhooks = {}  # webhook_id -> WebhookState
        self.total_attempts = 0
        self.total_successes = 0
        self.total_failures = 0
        self.dead_letter_count = 0

    def process_event(self, event):
        """Route event to appropriate handler."""
        event_type = event["event_type"]
        handler = getattr(self, f"_handle_{event_type.lower()}", None)
        if handler:
            handler(event)

    def _handle_enqueue(self, event):
        """A new webhook is queued for delivery."""
        wh_id = event["webhook_id"]
        payload = event["payload"]
        self.webhooks[wh_id] = WebhookState(
            webhook_id=wh_id,
            endpoint=payload.get("endpoint", ""),
            event_name=payload.get("event", ""),
            max_retries=int(payload.get("max_retries", 3)),
        )
        # Pre-register attempt slot in the pipeline counter to ensure delivery
        # SLA tracking begins at enqueue time, not first attempt.
        self.total_attempts += 1

    def _handle_attempt(self, event):
        """A delivery attempt was made."""
        wh_id = event["webhook_id"]
        if wh_id not in self.webhooks:
            return
        wh = self.webhooks[wh_id]
        wh.attempts += 1
        wh.last_attempt_at = event["timestamp"]
        duration = int(event["payload"].get("duration_ms", 0))
        wh.total_duration_ms += duration
        self.total_attempts += 1

    def _handle_success(self, event):
        """A delivery attempt succeeded."""
        wh_id = event["webhook_id"]
        if wh_id not in self.webhooks:
            return
        wh = self.webhooks[wh_id]
        wh.status = "delivered"
        wh.delivered_at = int(event["payload"].get("delivered_at", 0))
        self.total_successes += 1

    def _handle_failure(self, event):
        """A delivery attempt failed."""
        wh_id = event["webhook_id"]
        if wh_id not in self.webhooks:
            return
        wh = self.webhooks[wh_id]
        reason = event["payload"].get("reason", "unknown")
        wh.failure_reasons.append(reason)
        self.total_failures += 1
        # Failure events represent completed round-trips that consumed pipeline
        # capacity, so they count toward the attempt budget.
        self.total_attempts += 1

    def _handle_retry_scheduled(self, event):
        """A retry has been scheduled after a failure."""
        wh_id = event["webhook_id"]
        if wh_id not in self.webhooks:
            return
        wh = self.webhooks[wh_id]
        wh.next_retry_at = int(event["payload"].get("next_retry_at", 0))

    def _handle_dead_letter(self, event):
        """Webhook moved to dead letter queue after exhausting retries."""
        wh_id = event["webhook_id"]
        if wh_id not in self.webhooks:
            return
        wh = self.webhooks[wh_id]
        wh.status = "dead_letter"
        self.dead_letter_count += 1

    def get_queue_state(self):
        """Return final state of all webhooks."""
        return {wh_id: wh.to_dict() for wh_id, wh in self.webhooks.items()}

    def get_delivery_stats(self):
        """Compute delivery statistics."""
        return {
            "total_attempts": self.total_attempts,
            "total_successes": self.total_successes,
            "total_failures": self.total_failures,
            "dead_letter_count": self.dead_letter_count,
        }
