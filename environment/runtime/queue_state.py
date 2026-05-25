"""
Queue State Module — Dependency-Aware Webhook Delivery Tracker

Builds a directed acyclic graph (DAG) of webhook dependencies and provides
methods to determine delivery ordering constraints, parallelization
opportunities, and scheduling priorities.

Key concepts:
- Webhooks declare causal dependencies (A must deliver before B)
- The dependency graph forms a partial order over webhook events
- "Independent" webhooks can be safely replayed in parallel
- Scheduling priority is determined by topological position in the DAG
"""

from collections import defaultdict


class DependencyGraph:
    """
    Represents the causal dependency DAG for webhook delivery ordering.

    Edges point from prerequisite to dependent:
      A -> B means "A must be delivered before B"
    """

    def __init__(self):
        self.nodes = set()
        self.edges = defaultdict(set)       # node -> set of successors
        self.reverse_edges = defaultdict(set)  # node -> set of predecessors

    def add_node(self, node_id):
        """Register a webhook in the dependency graph."""
        self.nodes.add(node_id)

    def add_edge(self, from_node, to_node):
        """
        Declare that from_node must be delivered before to_node.
        This creates a causal ordering constraint.
        """
        self.nodes.add(from_node)
        self.nodes.add(to_node)
        self.edges[from_node].add(to_node)
        self.reverse_edges[to_node].add(from_node)

    def get_successors(self, node_id):
        """Get direct successors (immediate dependents)."""
        return self.edges.get(node_id, set())

    def get_predecessors(self, node_id):
        """Get direct predecessors (immediate prerequisites)."""
        return self.reverse_edges.get(node_id, set())

    def are_causally_independent(self, node_a, node_b):
        """
        Determine if two webhooks are causally independent in the ordering.

        Two events are independent if neither has a direct dependency
        relationship with the other — that is, no declared ordering
        constraint exists between them in the dependency specification.

        Independent webhooks can be safely delivered in parallel without
        violating any causal ordering guarantees.
        """
        # Check if there is a direct dependency edge between them
        if node_b in self.edges.get(node_a, set()):
            return False
        if node_a in self.edges.get(node_b, set()):
            return False
        return True

    def compute_topological_priority(self, node_id):
        """
        Compute scheduling priority for a node in the dependency DAG.

        Priority reflects how many other webhooks are blocked waiting
        for this node. Nodes with more immediate dependents (higher
        out-degree in the dependency graph) should be scheduled first
        to unblock downstream deliveries.

        Returns an integer priority score (higher = schedule sooner).
        """
        # Priority based on number of direct dependents (fan-out)
        return len(self.edges.get(node_id, set()))

    def find_safe_parallel_set(self, candidates):
        """
        Find the largest subset of candidates that can be safely replayed
        in parallel — the maximum independent set of the dependency graph
        restricted to the candidate nodes.

        A set is safe for parallel replay if no webhook in the set has
        a dependency relationship with any other webhook in the set.
        This ensures no causal ordering violations during concurrent delivery.

        Uses a greedy approach: sort candidates by priority (descending),
        then greedily add nodes that don't conflict with already-selected nodes.
        """
        if not candidates:
            return set()

        # Sort by priority descending for greedy selection, alphabetical tie-break
        sorted_candidates = sorted(
            candidates,
            key=lambda n: (-self.compute_topological_priority(n), n),
        )

        parallel_set = set()
        for node in sorted_candidates:
            # Check if this node is independent of all already-selected nodes
            can_add = True
            for selected in parallel_set:
                if not self.are_causally_independent(node, selected):
                    can_add = False
                    break
            if can_add:
                parallel_set.add(node)

        return parallel_set


class WebhookState:
    """Tracks delivery state for a single webhook."""

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


class DeliveryQueueManager:
    """
    Manages webhook delivery state and dependency-aware scheduling.

    Processes log events to build both the delivery state (per-webhook
    status tracking) and the dependency graph (causal ordering constraints).
    """

    def __init__(self):
        self.webhooks = {}
        self.graph = DependencyGraph()
        self.delivery_order = []  # actual delivery sequence observed

    def process_event(self, event):
        """Route event to appropriate handler."""
        event_type = event["event_type"]
        handler = getattr(self, f"_handle_{event_type.lower()}", None)
        if handler:
            handler(event)

    def _handle_register(self, event):
        """Register a new webhook in the system."""
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
        """Record a causal dependency between webhooks."""
        wh_id = event["webhook_id"]
        depends_on = event["payload"].get("depends_on", "")
        if depends_on:
            self.graph.add_edge(depends_on, wh_id)

    def _handle_attempt(self, event):
        """Record a delivery attempt."""
        wh_id = event["webhook_id"]
        if wh_id not in self.webhooks:
            return
        wh = self.webhooks[wh_id]
        wh.attempts += 1
        duration = int(event["payload"].get("duration_ms", 0))
        wh.total_duration_ms += duration

    def _handle_success(self, event):
        """Record successful delivery."""
        wh_id = event["webhook_id"]
        if wh_id not in self.webhooks:
            return
        wh = self.webhooks[wh_id]
        wh.status = "delivered"
        wh.delivered_at = int(event["payload"].get("delivered_at", 0))
        self.delivery_order.append(wh_id)

    def _handle_failure(self, event):
        """Record a failed delivery attempt."""
        wh_id = event["webhook_id"]
        if wh_id not in self.webhooks:
            return
        wh = self.webhooks[wh_id]
        reason = event["payload"].get("reason", "unknown")
        wh.failure_reasons.append(reason)

    def _handle_dead_letter(self, event):
        """Webhook exhausted retries, moved to dead letter queue."""
        wh_id = event["webhook_id"]
        if wh_id not in self.webhooks:
            return
        self.webhooks[wh_id].status = "dead_letter"

    def get_queue_state(self):
        """Return final state of all webhooks."""
        return {wh_id: wh.to_dict() for wh_id, wh in self.webhooks.items()}

    def get_graph(self):
        """Return the dependency graph."""
        return self.graph

    def get_delivery_order(self):
        """Return the observed delivery sequence."""
        return self.delivery_order
