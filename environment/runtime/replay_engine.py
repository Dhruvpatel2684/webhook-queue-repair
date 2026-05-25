"""
Webhook Replay Engine - Main Entrypoint
Orchestrates replay of webhook delivery logs and produces output files.

Usage: python3 replay_engine.py

Reads: delivery_logs.txt
Produces:
  - webhook_status.jsonl (per-webhook final state)
  - delivery_report.json (summary statistics and queue fingerprint)
"""

import os
import sys

RUNTIME_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, RUNTIME_DIR)

from log_parser import load_events
from queue_state import DeliveryQueueManager
from report_generator import generate_report


def main():
    """Main execution: parse logs, replay through queue manager, write report."""
    log_path = os.path.join(RUNTIME_DIR, "delivery_logs.txt")
    events = load_events(log_path)

    print(f"Loaded {len(events)} events from delivery log")

    manager = DeliveryQueueManager()
    for event in events:
        manager.process_event(event)

    queue_state = manager.get_queue_state()
    stats = manager.get_delivery_stats()

    print(f"Replay complete. {len(queue_state)} webhooks processed.")
    print(f"Stats: {stats['total_attempts']} attempts, {stats['total_successes']} successes")

    jsonl_path, report_path = generate_report(
        queue_state=queue_state,
        stats=stats,
        output_dir=RUNTIME_DIR,
    )

    print(f"Output written:")
    print(f"  - {jsonl_path}")
    print(f"  - {report_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
