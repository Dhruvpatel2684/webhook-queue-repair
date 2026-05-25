"""
Report Generator Module — Dependency Analysis and Scheduling Metrics

Produces webhook_status.jsonl and delivery_report.json with:
- Per-webhook delivery state
- Dependency graph analysis (independent pairs, parallel sets, priorities)
- Scheduling quality metrics
- Integrity fingerprint
"""

import json
import hashlib
import os


def compute_independent_pairs(graph):
    """
    Count the number of webhook pairs that are causally independent
    and can therefore be safely delivered in parallel.

    Two webhooks are independent if neither causally precedes the other
    in the dependency ordering — concurrent delivery won't violate
    any ordering guarantees.
    """
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
    """
    Determine which pending/ready webhooks can be replayed simultaneously.
    Uses the graph's safe parallel set computation on all registered webhooks
    to find the maximum set that respects causal ordering.
    """
    all_nodes = set(graph.nodes)
    parallel_set = graph.find_safe_parallel_set(all_nodes)
    return sorted(parallel_set)


def compute_scheduling_priorities(graph):
    """
    Compute priority ordering for webhook delivery scheduling.
    Returns webhooks sorted by their topological priority (descending),
    breaking ties alphabetically.
    """
    priorities = {}
    for node in sorted(graph.nodes):
        priorities[node] = graph.compute_topological_priority(node)

    # Sort by priority descending, then alphabetically for ties
    sorted_nodes = sorted(
        graph.nodes,
        key=lambda n: (-priorities[n], n),
    )
    return sorted_nodes, priorities


def compute_ordering_violations(graph, delivery_order):
    """
    Check how many times the actual delivery order violated causal dependencies.
    A violation occurs when a webhook was delivered before one of its prerequisites.
    """
    delivered_set = set()
    violations = 0

    for wh_id in delivery_order:
        # Check if all predecessors of this webhook were already delivered
        predecessors = graph.get_predecessors(wh_id)
        for pred in predecessors:
            if pred not in delivered_set:
                violations += 1
        delivered_set.add(wh_id)

    return violations


def compute_fingerprint(graph, queue_state, independent_count, parallel_set):
    """
    Compute deterministic integrity fingerprint encoding the dependency
    analysis results. Incorporates graph structure, independence analysis,
    and parallel scheduling output.
    """
    fingerprint_data = ""

    # Encode graph edges in deterministic order
    for node in sorted(graph.nodes):
        successors = sorted(graph.edges.get(node, set()))
        fingerprint_data += f"{node}:{','.join(successors)}|"

    # Encode independence count and parallel set
    fingerprint_data += f"indep:{independent_count};"
    fingerprint_data += f"parallel:{','.join(sorted(parallel_set))};"

    # Encode delivery states
    for wh_id in sorted(queue_state.keys()):
        state = queue_state[wh_id]
        fingerprint_data += f"{wh_id}={state['status']}:{state['attempts']};"

    return hashlib.sha256(fingerprint_data.encode()).hexdigest()[:16]


def generate_report(queue_state, graph, delivery_order, output_dir):
    """
    Write final output files:
    - webhook_status.jsonl: per-webhook state sorted by webhook_id
    - delivery_report.json: dependency analysis and scheduling metrics
    """
    # Write webhook_status.jsonl
    jsonl_path = os.path.join(output_dir, "webhook_status.jsonl")
    with open(jsonl_path, "w") as f:
        for wh_id in sorted(queue_state.keys()):
            state = queue_state[wh_id]
            f.write(json.dumps(state) + "\n")

    # Compute dependency analysis metrics
    independent_count, independent_pairs = compute_independent_pairs(graph)
    parallel_set = compute_parallel_replay_set(graph, queue_state)
    priority_order, priorities = compute_scheduling_priorities(graph)
    violations = compute_ordering_violations(graph, delivery_order)

    # Compute summary stats
    total_webhooks = len(queue_state)
    delivered = sum(1 for s in queue_state.values() if s["status"] == "delivered")
    dead_lettered = sum(1 for s in queue_state.values() if s["status"] == "dead_letter")
    pending = sum(1 for s in queue_state.values() if s["status"] == "pending")
    total_attempts = sum(s["attempts"] for s in queue_state.values())

    fingerprint = compute_fingerprint(
        graph, queue_state, independent_count, parallel_set
    )

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
