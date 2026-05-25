"""
Repair script for webhook-queue-repair task.
Re-processes the delivery log with corrected dependency analysis logic.

Fixes applied to queue_state.py logic:
1. are_causally_independent: Use transitive closure (BFS reachability) to determine
   if two nodes are truly incomparable in the partial order, not just adjacency check.
2. compute_topological_priority: Use longest-path-from-node (critical path length)
   as the scheduling priority, not out-degree (immediate fan-out count).
3. find_safe_parallel_set: Use ascending priority order (leaves first) for greedy
   antichain construction, not descending (roots first).
"""

import json
import hashlib
import os
import sys
from collections import defaultdict

RUNTIME_DIR = "/app/runtime"
LOG_FILE = os.path.join(RUNTIME_DIR, "delivery_logs.txt")


# ============================================================
# Log Parser (correct — same as original)
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
# FIXED Dependency Graph
# ============================================================

class DependencyGraph:
    def __init__(self):
        self.nodes = set()
        self.edges = defaultdict(set)
        self.reverse_edges = defaultdict(set)
        self._reachable_cache = {}

    def add_node(self, node_id):
        self.nodes.add(node_id)

    def add_edge(self, from_node, to_node):
        self.nodes.add(from_node)
        self.nodes.add(to_node)
        self.edges[from_node].add(to_node)
        self.reverse_edges[to_node].add(from_node)

    def get_successors(self, node_id):
        return self.edges.get(node_id, set())

    def get_predecessors(self, node_id):
        return self.reverse_edges.get(node_id, set())

    def _get_reachable(self, node_id):
        """Compute all nodes reachable from node_id via transitive closure."""
        if node_id in self._reachable_cache:
            return self._reachable_cache[node_id]
        visited = set()
        stack = [node_id]
        while stack:
            current = stack.pop()
            for succ in self.edges.get(current, set()):
                if succ not in visited:
                    visited.add(succ)
                    stack.append(succ)
        self._reachable_cache[node_id] = visited
        return visited

    def are_causally_independent(self, node_a, node_b):
        """
        FIX: Two events are independent only if NEITHER can reach the other
        through ANY path in the dependency graph (transitive closure).
        The buggy version only checked direct edges (adjacency).
        """
        reachable_from_a = self._get_reachable(node_a)
        reachable_from_b = self._get_reachable(node_b)
        if node_b in reachable_from_a:
            return False
        if node_a in reachable_from_b:
            return False
        return True

    def compute_topological_priority(self, node_id):
        """
        FIX: Priority = longest path from this node to any leaf (critical path).
        The buggy version used out-degree (number of direct dependents).
        Critical path length correctly captures how many downstream nodes
        are transitively blocked by this node.
        """
        memo = {}

        def _longest_path(node):
            if node in memo:
                return memo[node]
            successors = self.edges.get(node, set())
            if not successors:
                memo[node] = 0
                return 0
            max_path = max(1 + _longest_path(s) for s in successors)
            memo[node] = max_path
            return max_path

        return _longest_path(node_id)

    def find_safe_parallel_set(self, candidates):
        """
        FIX: Find maximum antichain using ascending priority order (leaves first).
        The buggy version used descending priority (roots first), which picks
        high-priority nodes that dominate many others, resulting in smaller sets
        with causal violations when combined with the adjacency-only independence check.

        Ascending order (lowest priority first = leaf nodes) maximizes the antichain
        because leaf nodes are more likely to be mutually incomparable.
        """
        if not candidates:
            return set()

        # FIX: Sort by priority ASCENDING (leaves first), then alphabetical
        sorted_candidates = sorted(
            candidates,
            key=lambda n: (self.compute_topological_priority(n), n),
        )

        parallel_set = set()
        for node in sorted_candidates:
            can_add = True
            for selected in parallel_set:
                if not self.are_causally_independent(node, selected):
                    can_add = False
                    break
            if can_add:
                parallel_set.add(node)

        return parallel_set


# ============================================================
# Webhook State (correct — same as original)
# ============================================================

class WebhookState:
    def __init__(self, webhook_id, endpoint, event_name, priority):
        self.webhook_id = webhook_id
        self.endpoint = endpoint
        self.event_name = event_name
        self.priority = priority
        self.status = "pending"
        self.attempts = 0
        self.delivered_at = None
        self.failure_reasons = []
        self.total_duration_ms = 0

    def to_dict(self):
        return {
            "webhook_id": self.webhook_id,
            "endpoint": self.endpoint,
            "event": self.event_name,
            "priority": self.priority,
            "status": self.status,
            "attempts": self.attempts,
            "delivered_at": self.delivered_at,
            "failure_reasons": self.failure_reasons,
            "total_duration_ms": self.total_duration_ms,
        }


# ============================================================
# Queue Manager (correct — same as original)
# ============================================================

class DeliveryQueueManager:
    def __init__(self):
        self.webhooks = {}
        self.graph = DependencyGraph()
        self.delivery_order = []

    def process_event(self, event):
        event_type = event["event_type"]
        handler = getattr(self, f"_handle_{event_type.lower()}", None)
        if handler:
            handler(event)

    def _handle_register(self, event):
        wh_id = event["webhook_id"]
        payload = event["payload"]
        self.webhooks[wh_id] = WebhookState(
            webhook_id=wh_id,
            endpoint=payload.get("endpoint", ""),
            event_name=payload.get("event", ""),
            priority=payload.get("priority", "medium"),
        )
        self.graph.add_node(wh_id)

    def _handle_dependency(self, event):
        wh_id = event["webhook_id"]
        depends_on = event["payload"].get("depends_on", "")
        if depends_on:
            self.graph.add_edge(depends_on, wh_id)

    def _handle_attempt(self, event):
        wh_id = event["webhook_id"]
        if wh_id not in self.webhooks:
            return
        wh = self.webhooks[wh_id]
        wh.attempts += 1
        duration = int(event["payload"].get("duration_ms", 0))
        wh.total_duration_ms += duration

    def _handle_success(self, event):
        wh_id = event["webhook_id"]
        if wh_id not in self.webhooks:
            return
        wh = self.webhooks[wh_id]
        wh.status = "delivered"
        wh.delivered_at = int(event["payload"].get("delivered_at", 0))
        self.delivery_order.append(wh_id)

    def _handle_failure(self, event):
        wh_id = event["webhook_id"]
        if wh_id not in self.webhooks:
            return
        wh = self.webhooks[wh_id]
        reason = event["payload"].get("reason", "unknown")
        wh.failure_reasons.append(reason)

    def _handle_dead_letter(self, event):
        wh_id = event["webhook_id"]
        if wh_id not in self.webhooks:
            return
        self.webhooks[wh_id].status = "dead_letter"

    def get_queue_state(self):
        return {wh_id: wh.to_dict() for wh_id, wh in self.webhooks.items()}

    def get_graph(self):
        return self.graph

    def get_delivery_order(self):
        return self.delivery_order


# ============================================================
# Report Generator (correct — same as original)
# ============================================================

def compute_independent_pairs(graph):
    nodes = sorted(graph.nodes)
    independent_count = 0
    independent_pairs = []
    for i in range(len(nodes)):
        for j in range(i + 1, len(nodes)):
            if graph.are_causally_independent(nodes[i], nodes[j]):
                independent_count += 1
                independent_pairs.append((nodes[i], nodes[j]))
    return independent_count, independent_pairs


def compute_parallel_replay_set(graph, queue_state):
    all_nodes = set(graph.nodes)
    parallel_set = graph.find_safe_parallel_set(all_nodes)
    return sorted(parallel_set)


def compute_scheduling_priorities(graph):
    priorities = {}
    for node in sorted(graph.nodes):
        priorities[node] = graph.compute_topological_priority(node)
    sorted_nodes = sorted(graph.nodes, key=lambda n: (-priorities[n], n))
    return sorted_nodes, priorities


def compute_ordering_violations(graph, delivery_order):
    delivered_set = set()
    violations = 0
    for wh_id in delivery_order:
        predecessors = graph.get_predecessors(wh_id)
        for pred in predecessors:
            if pred not in delivered_set:
                violations += 1
        delivered_set.add(wh_id)
    return violations


def compute_fingerprint(graph, queue_state, independent_count, parallel_set):
    fingerprint_data = ""
    for node in sorted(graph.nodes):
        successors = sorted(graph.edges.get(node, set()))
        fingerprint_data += f"{node}:{','.join(successors)}|"
    fingerprint_data += f"indep:{independent_count};"
    fingerprint_data += f"parallel:{','.join(sorted(parallel_set))};"
    for wh_id in sorted(queue_state.keys()):
        state = queue_state[wh_id]
        fingerprint_data += f"{wh_id}={state['status']}:{state['attempts']};"
    return hashlib.sha256(fingerprint_data.encode()).hexdigest()[:16]


def generate_report(queue_state, graph, delivery_order):
    output_dir = RUNTIME_DIR

    # Write webhook_status.jsonl
    jsonl_path = os.path.join(output_dir, "webhook_status.jsonl")
    with open(jsonl_path, "w") as f:
        for wh_id in sorted(queue_state.keys()):
            state = queue_state[wh_id]
            f.write(json.dumps(state) + "\n")

    # Compute metrics
    independent_count, _ = compute_independent_pairs(graph)
    parallel_set = compute_parallel_replay_set(graph, queue_state)
    priority_order, priorities = compute_scheduling_priorities(graph)
    violations = compute_ordering_violations(graph, delivery_order)

    total_webhooks = len(queue_state)
    delivered = sum(1 for s in queue_state.values() if s["status"] == "delivered")
    dead_lettered = sum(1 for s in queue_state.values() if s["status"] == "dead_letter")
    pending = sum(1 for s in queue_state.values() if s["status"] == "pending")
    total_attempts = sum(s["attempts"] for s in queue_state.values())

    fingerprint = compute_fingerprint(graph, queue_state, independent_count, parallel_set)

    report = {
        "total_webhooks": total_webhooks,
        "delivered": delivered,
        "dead_lettered": dead_lettered,
        "pending": pending,
        "total_attempts": total_attempts,
        "total_edges": sum(len(s) for s in graph.edges.values()),
        "independent_pair_count": independent_count,
        "parallel_replay_set": parallel_set,
        "parallel_replay_size": len(parallel_set),
        "priority_order": priority_order,
        "scheduling_priorities": priorities,
        "ordering_violations": violations,
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
    graph = manager.get_graph()
    delivery_order = manager.get_delivery_order()

    generate_report(queue_state, graph, delivery_order)

    print(f"Repair complete. Processed {len(events)} events, {len(queue_state)} webhooks.")


if __name__ == "__main__":
    main()
