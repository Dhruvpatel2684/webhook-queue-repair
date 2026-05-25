"""
Webhook Replay Engine — Dependency-Aware Delivery Orchestrator

Entry point for the webhook delivery replay system. Processes delivery logs,
builds the dependency graph, computes replay scheduling, and generates reports.

Usage: python3 replay_engine.py

Reads: delivery_logs.txt
Produces:
  - webhook_status.jsonl (per-webhook final state, sorted by webhook_id)
  - delivery_report.json (dependency analysis, scheduling metrics, and fingerprint)
"""

import os
import sys

RUNTIME_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, RUNTIME_DIR)

from log_parser import load_events
from queue_state import DeliveryQueueManager
from report_generator import generate_report


def main():
    """Main execution: parse logs, build dependency state, write report."""
    log_path = os.path.join(RUNTIME_DIR, "delivery_logs.txt")
    events = load_events(log_path)

    print(f"Loaded {len(events)} events from delivery log")

    manager = DeliveryQueueManager()
    for event in events:
        manager.process_event(event)

    queue_state = manager.get_queue_state()
    graph = manager.get_graph()
    delivery_order = manager.get_delivery_order()

    print(f"Replay complete. {len(queue_state)} webhooks processed.")
    print(f"Dependency graph: {len(graph.nodes)} nodes, "
          f"{sum(len(s) for s in graph.edges.values())} edges")

    jsonl_path, report_path = generate_report(
        queue_state=queue_state,
        graph=graph,
        delivery_order=delivery_order,
        output_dir=RUNTIME_DIR,
    )

    print(f"Output written:")
    print(f"  - {jsonl_path}")
    print(f"  - {report_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
