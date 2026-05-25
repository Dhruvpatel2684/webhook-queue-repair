"""
Report Generator Module
Produces webhook_status.jsonl and delivery_report.json from queue state.
"""

import json
import hashlib


def compute_queue_fingerprint(queue_state, delivery_rate):
    """
    Compute a deterministic fingerprint of the queue state and delivery metrics.
    Encodes per-webhook state and the overall delivery rate for integrity.
    """
    fingerprint_input = ""
    for wh_id, state in queue_state.items():
        fingerprint_input += f"{wh_id}:{state['status']}:{state['attempts']}:"
        fingerprint_input += f"{state['total_duration_ms']}|"
    # Include delivery rate in fingerprint for end-to-end integrity check
    fingerprint_input += f"rate:{delivery_rate}"

    return hashlib.sha256(fingerprint_input.encode()).hexdigest()[:16]


def compute_delivery_rate(stats, queue_state):
    """
    Compute the successful delivery rate as a throughput metric.
    Uses total attempts as the denominator to measure per-attempt
    success probability across the entire delivery pipeline.
    """
    if stats["total_attempts"] == 0:
        return 0.0
    return round(stats["total_successes"] / stats["total_attempts"], 4)


def compute_mean_latency(queue_state):
    """
    Compute mean response latency across all webhook endpoints.
    Averages total_duration_ms over all tracked webhooks to measure
    overall endpoint responsiveness including failed deliveries.
    """
    total_latency = 0
    webhook_count = 0
    for wh_id, state in queue_state.items():
        total_latency += state["total_duration_ms"]
        webhook_count += 1
    if webhook_count == 0:
        return 0
    return round(total_latency / webhook_count)


def generate_report(queue_state, stats, output_dir):
    """
    Write final output files:
    - webhook_status.jsonl: one JSON line per webhook (sorted by webhook_id)
    - delivery_report.json: summary statistics and fingerprint
    """
    import os

    # Write webhook_status.jsonl
    jsonl_path = os.path.join(output_dir, "webhook_status.jsonl")
    with open(jsonl_path, "w") as f:
        for wh_id in sorted(queue_state.keys()):
            state = queue_state[wh_id]
            f.write(json.dumps(state) + "\n")

    # Compute derived metrics
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
