"""
Tests for webhook-queue-repair task.
Validates the webhook delivery replay analyzer output.
"""

import json
import os


RUNTIME_DIR = "/app/runtime"
JSONL_PATH = os.path.join(RUNTIME_DIR, "webhook_status.jsonl")
REPORT_PATH = os.path.join(RUNTIME_DIR, "delivery_report.json")


def load_webhook_status():
    """Load webhook_status.jsonl and return list of webhook records."""
    records = []
    with open(JSONL_PATH, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def load_report():
    """Load delivery_report.json and return dict."""
    with open(REPORT_PATH, "r") as f:
        return json.load(f)


# ============================================================
# TIER 1: Basic structure (pass even with buggy code)
# ============================================================

def test_output_files_exist():
    """Both output files must be created."""
    assert os.path.exists(JSONL_PATH), "webhook_status.jsonl not found"
    assert os.path.exists(REPORT_PATH), "delivery_report.json not found"


def test_correct_webhook_count():
    """Output must contain exactly 12 webhook records."""
    records = load_webhook_status()
    assert len(records) == 12, f"Expected 12 webhooks, got {len(records)}"


def test_webhook_ids_present():
    """All expected webhook IDs must be in output."""
    records = load_webhook_status()
    ids = {r["webhook_id"] for r in records}
    expected = {f"wh-{c}" for c in "ABCDEFGHIJKL"}
    assert ids == expected, f"Missing webhooks: {expected - ids}"


def test_delivery_status_counts():
    """11 delivered, 1 dead-lettered, 0 pending."""
    report = load_report()
    assert report["delivered"] == 11, f"Expected 11 delivered, got {report['delivered']}"
    assert report["dead_lettered"] == 1, f"Expected 1 dead_lettered, got {report['dead_lettered']}"
    assert report["pending"] == 0, f"Expected 0 pending, got {report['pending']}"


def test_total_attempts():
    """Total delivery attempts must equal 16."""
    report = load_report()
    assert report["total_attempts"] == 16, f"Expected 16, got {report['total_attempts']}"


def test_graph_edge_count():
    """Dependency graph must have 11 edges."""
    report = load_report()
    assert report["total_edges"] == 11, f"Expected 11, got {report['total_edges']}"


def test_no_ordering_violations():
    """The observed delivery order must have 0 causal violations."""
    report = load_report()
    assert report["ordering_violations"] == 0, (
        f"Expected 0 violations, got {report['ordering_violations']}"
    )


# ============================================================
# TIER 2: Medium (requires fixing Bug 1 — independence check)
# ============================================================

def test_independent_pair_count():
    """Independent pairs must equal 35 (using transitive closure, not adjacency)."""
    report = load_report()
    assert report["independent_pair_count"] == 35, (
        f"Expected 35 independent pairs, got {report['independent_pair_count']}. "
        f"Independence requires checking reachability (transitive closure), "
        f"not just direct edges."
    )


def test_priority_ordering_top():
    """wh-A must have highest priority (longest critical path of 5)."""
    report = load_report()
    assert report["priority_order"][0] == "wh-A", (
        f"Expected wh-A as highest priority, got {report['priority_order'][0]}. "
        f"Priority should reflect critical path length, not fan-out."
    )


# ============================================================
# TIER 3: Hard (requires fixing Bug 2 — priority + parallel set)
# ============================================================

def test_parallel_replay_size():
    """Parallel replay set must have exactly 6 webhooks."""
    report = load_report()
    assert report["parallel_replay_size"] == 6, (
        f"Expected parallel set size 6, got {report['parallel_replay_size']}. "
        f"The maximum antichain in this DAG has 6 mutually incomparable elements."
    )


def test_scheduling_priority_values():
    """Priority scores must reflect critical path length (longest-path-from)."""
    report = load_report()
    priorities = report["scheduling_priorities"]
    # wh-A has critical path 5 (A->B->C->D->F->G)
    assert priorities["wh-A"] == 5, f"wh-A priority: expected 5, got {priorities['wh-A']}"
    # wh-B has critical path 4 (B->C->D->F->G)
    assert priorities["wh-B"] == 4, f"wh-B priority: expected 4, got {priorities['wh-B']}"
    # wh-C has critical path 3 (C->D->F->G)
    assert priorities["wh-C"] == 3, f"wh-C priority: expected 3, got {priorities['wh-C']}"
    # Leaf nodes have critical path 0
    assert priorities["wh-E"] == 0, f"wh-E priority: expected 0, got {priorities['wh-E']}"
    assert priorities["wh-G"] == 0, f"wh-G priority: expected 0, got {priorities['wh-G']}"


# ============================================================
# TIER 4: Hardest (requires ALL bugs fixed — antichain + fingerprint)
# ============================================================

def test_parallel_set_is_antichain():
    """Every pair in the parallel set must be truly causally independent."""
    report = load_report()
    parallel_set = report["parallel_replay_set"]
    # The correct set contains only leaf-level nodes with no paths between them.
    # Verify no element in the set is an ancestor/descendant of another.
    # The correct antichain is: E, G, H, J, K, L (all leaves/near-leaves)
    # If B or D appear, there's a causal violation (B->C->D path exists)
    problematic = {"wh-A", "wh-B", "wh-C", "wh-D", "wh-F"}
    found_problematic = set(parallel_set) & problematic
    assert not found_problematic, (
        f"Parallel set contains {found_problematic} which have causal paths "
        f"to other nodes. Only truly incomparable nodes belong in the antichain."
    )


def test_parallel_set_members():
    """Parallel replay set must contain exactly [wh-E, wh-G, wh-H, wh-J, wh-K, wh-L]."""
    report = load_report()
    expected = ["wh-E", "wh-G", "wh-H", "wh-J", "wh-K", "wh-L"]
    assert sorted(report["parallel_replay_set"]) == sorted(expected), (
        f"Expected {expected}, got {report['parallel_replay_set']}"
    )


def test_queue_fingerprint():
    """Queue fingerprint must match expected deterministic value."""
    report = load_report()
    assert report["queue_fingerprint"] == "a424de727db259bd", (
        f"Expected 'a424de727db259bd', got '{report['queue_fingerprint']}'"
    )
