"""
Repair script for webhook-queue-repair task.
Re-processes the delivery log with corrected logic and overwrites output files.

Fixes applied:
1. queue_state.py: Remove pre-increment of total_attempts in _handle_enqueue
   (only ATTEMPT events should count toward total_attempts)
2. report_generator.py: delivery_rate = delivered/total_webhooks (not successes/attempts)
3. report_generator.py: mean_latency only averages delivered webhooks (not all)
4. report_generator.py: fingerprint uses sorted iteration (deterministic order)
"""

import json
import hashlib
import os

RUNTIME_DIR = "/app/runtime"
LOG_FILE = os.path.join(RUNTIME_DIR, "delivery_logs.txt")


# ============================================================
# Log Parser (no bugs - same as original)
# ============================================================

def parse_payload(payload_str):
    result = {}
    for pair in payload_str.split(","):
        if "=" in pair:
            key, value = pair.split("=", 1)
            result[key.strip()] = value.strip()
    return result


def parse_log_line(line):
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


def load_events():
    events = []
    with open(LOG_FILE, "r") as f:
        for line in f:
            event = parse_log_line(line)
            if event is not None:
                events.append(event)
    events.sort(key=lambda e: e["timestamp"])
    return events


# ============================================================
# FIXED Queue State
# ============================================================

class WebhookState:
    def __init__(self, webhook_id, endpoint, event_name, max_retries):
        self.webhook_id = webhook_id
        self.endpoint = endpoint
        self.event_name = event_name
        self.max_retries = max_retries
        self.attempts = 0
        self.status = "pending"
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
    def __init__(self):
        self.webhooks = {}
        self.total_attempts = 0
        self.total_successes = 0
        self.total_failures = 0
        self.dead_letter_count = 0

    def process_event(self, event):
        event_type = event["event_type"]
        handler = getattr(self, f"_handle_{event_type.lower()}", None)
        if handler:
            handler(event)

    def _handle_enqueue(self, event):
        wh_id = event["webhook_id"]
        payload = event["payload"]
        self.webhooks[wh_id] = WebhookState(
            webhook_id=wh_id,
            endpoint=payload.get("endpoint", ""),
            event_name=payload.get("event", ""),
            max_retries=int(payload.get("max_retries", 3)),
        )
        # FIX: Do NOT increment total_attempts here.
        # Attempts are only counted when ATTEMPT events occur.

    def _handle_attempt(self, event):
        wh_id = event["webhook_id"]
        if wh_id not in self.webhooks:
            return
        wh = self.webhooks[wh_id]
        wh.attempts += 1
        duration = int(event["payload"].get("duration_ms", 0))
        wh.total_duration_ms += duration
        self.total_attempts += 1

    def _handle_success(self, event):
        wh_id = event["webhook_id"]
        if wh_id not in self.webhooks:
            return
        wh = self.webhooks[wh_id]
        wh.status = "delivered"
        wh.delivered_at = int(event["payload"].get("delivered_at", 0))
        self.total_successes += 1

    def _handle_failure(self, event):
        wh_id = event["webhook_id"]
        if wh_id not in self.webhooks:
            return
        wh = self.webhooks[wh_id]
        reason = event["payload"].get("reason", "unknown")
        wh.failure_reasons.append(reason)
        self.total_failures += 1

    def _handle_retry_scheduled(self, event):
        wh_id = event["webhook_id"]
        if wh_id not in self.webhooks:
            return
        wh = self.webhooks[wh_id]
        wh.next_retry_at = int(event["payload"].get("next_retry_at", 0))

    def _handle_dead_letter(self, event):
        wh_id = event["webhook_id"]
        if wh_id not in self.webhooks:
            return
        wh = self.webhooks[wh_id]
        wh.status = "dead_letter"
        self.dead_letter_count += 1

    def get_queue_state(self):
        return {wh_id: wh.to_dict() for wh_id, wh in self.webhooks.items()}

    def get_delivery_stats(self):
        return {
            "total_attempts": self.total_attempts,
            "total_successes": self.total_successes,
            "total_failures": self.total_failures,
            "dead_letter_count": self.dead_letter_count,
        }


# ============================================================
# FIXED Report Generator
# ============================================================

def compute_queue_fingerprint(queue_state, delivery_rate):
    """FIX: Sort by webhook_id for deterministic output."""
    fingerprint_input = ""
    for wh_id in sorted(queue_state.keys()):  # FIX: sorted
        state = queue_state[wh_id]
        fingerprint_input += f"{wh_id}:{state['status']}:{state['attempts']}:"
        fingerprint_input += f"{state['total_duration_ms']}|"
    fingerprint_input += f"rate:{delivery_rate}"
    return hashlib.sha256(fingerprint_input.encode()).hexdigest()[:16]


def compute_delivery_rate(stats, queue_state):
    """FIX: Rate = delivered webhooks / total webhooks (not attempts)."""
    total_webhooks = len(queue_state)
    if total_webhooks == 0:
        return 0.0
    delivered = sum(1 for s in queue_state.values() if s["status"] == "delivered")
    return round(delivered / total_webhooks, 4)


def compute_mean_latency(queue_state):
    """FIX: Only average latency for DELIVERED webhooks."""
    total_latency = 0
    delivered_count = 0
    for wh_id, state in queue_state.items():
        if state["status"] == "delivered":
            total_latency += state["total_duration_ms"]
            delivered_count += 1
    if delivered_count == 0:
        return 0
    return round(total_latency / delivered_count)


def generate_report(queue_state, stats):
    """Write corrected output files."""
    output_dir = RUNTIME_DIR

    jsonl_path = os.path.join(output_dir, "webhook_status.jsonl")
    with open(jsonl_path, "w") as f:
        for wh_id in sorted(queue_state.keys()):
            state = queue_state[wh_id]
            f.write(json.dumps(state) + "\n")

    delivery_rate = compute_delivery_rate(stats, queue_state)
    mean_latency = compute_mean_latency(queue_state)
    fingerprint = compute_queue_fingerprint(queue_state, delivery_rate)

    total_webhooks = len(queue_state)
    delivered = sum(1 for s in queue_state.values() if s["status"] == "delivered")
    dead_lettered = sum(1 for s in queue_state.values() if s["status"] == "dead_letter")
    pending = sum(1 for s in queue_state.values() if s["status"] == "pending")

    report = {
        "total_webhooks": total_webhooks,
        "delivered": delivered,
        "dead_lettered": dead_lettered,
        "pending": pending,
        "delivery_rate": delivery_rate,
        "mean_latency_ms": mean_latency,
        "total_attempts": stats["total_attempts"],
        "queue_fingerprint": fingerprint,
    }

    report_path = os.path.join(output_dir, "delivery_report.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    return jsonl_path, report_path


# ============================================================
# Main
# ============================================================

def main():
    events = load_events()
    manager = DeliveryQueueManager()
    for event in events:
        manager.process_event(event)

    queue_state = manager.get_queue_state()
    stats = manager.get_delivery_stats()
    generate_report(queue_state, stats)

    print(f"Repair complete. Processed {len(events)} events.")
    print(f"Total attempts: {stats['total_attempts']}")
    print(f"Delivered: {stats['total_successes']}")


if __name__ == "__main__":
    main()
