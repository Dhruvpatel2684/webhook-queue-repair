"""Tests for CRDT merge engine output validation."""

import json
import hashlib
import os

OUTPUT_DIR = "/app/runtime/output"
STATE_PATH = os.path.join(OUTPUT_DIR, "merged_state.json")
CONFLICT_PATH = os.path.join(OUTPUT_DIR, "conflict_report.json")


def load_state():
    with open(STATE_PATH) as f:
        return json.load(f)


def load_conflicts():
    with open(CONFLICT_PATH) as f:
        return json.load(f)


# ============================================================
# Tier 1: Structural validation (7 tests, pass with bugs)
# ============================================================

def test_output_directory_exists():
    """Output directory must exist after merge."""
    assert os.path.isdir(OUTPUT_DIR), f"Output directory not found at {OUTPUT_DIR}"


def test_state_file_exists():
    """merged_state.json must be created."""
    assert os.path.isfile(STATE_PATH), f"State file not found at {STATE_PATH}"


def test_conflict_file_exists():
    """conflict_report.json must be created."""
    assert os.path.isfile(CONFLICT_PATH), f"Conflict file not found at {CONFLICT_PATH}"


def test_state_top_level_fields():
    """State must contain required top-level fields."""
    state = load_state()
    required = {"registers", "sets", "state_digest", "total_registers", "total_sets"}
    missing = required - set(state.keys())
    assert not missing, f"Missing fields in state: {missing}"


def test_conflict_top_level_fields():
    """Conflict report must contain required fields."""
    conflicts = load_conflicts()
    assert "high_conflict_entries" in conflicts, "Missing high_conflict_entries"
    assert "total_conflicts" in conflicts, "Missing total_conflicts"


def test_register_count():
    """Must have correct number of register keys."""
    state = load_state()
    assert state["total_registers"] == 12, (
        f"Expected 12 register keys, got {state['total_registers']}"
    )


def test_set_count():
    """Must have correct number of set keys."""
    state = load_state()
    assert state["total_sets"] == 2, (
        f"Expected 2 set keys, got {state['total_sets']}"
    )


# ============================================================
# Tier 2: Register value tests (3 tests, need Bugs 1+4 fixed)
# ============================================================

def test_register_user_1001_name():
    """user:1001:name must resolve to the correct LWW value."""
    state = load_state()
    reg = state["registers"]["user:1001:name"]
    assert reg["value"] == "Alice_v3", (
        f"Expected 'Alice_v3', got '{reg['value']}'"
    )


def test_register_user_1002_email_value():
    """user:1002:email must resolve to the correct replica's value."""
    state = load_state()
    reg = state["registers"]["user:1002:email"]
    assert reg["value"] == "bob@beta.com", (
        f"Expected 'bob@beta.com', got '{reg['value']}'"
    )


def test_register_user_1002_email_replica():
    """user:1002:email must come from the correct replica."""
    state = load_state()
    reg = state["registers"]["user:1002:email"]
    assert reg["replica"] == "beta", (
        f"Expected replica 'beta', got '{reg['replica']}'"
    )


# ============================================================
# Tier 3: OR-set and conflict tests (3 tests, need Bugs 2+3+5)
# ============================================================

def test_tags_element_count():
    """user:1001:tags must have correct element count after merge."""
    state = load_state()
    tags = state["sets"]["user:1001:tags"]
    assert len(tags) == 8, (
        f"Expected 8 elements in user:1001:tags, got {len(tags)}"
    )


def test_trial_removed_from_tags():
    """Value 'trial' must not appear in user:1001:tags after remove."""
    state = load_state()
    tags = state["sets"]["user:1001:tags"]
    values = [e["value"] for e in tags]
    assert "trial" not in values, (
        f"'trial' should not be in user:1001:tags but was found"
    )


def test_conflict_total_count():
    """Conflict report must have correct number of entries."""
    conflicts = load_conflicts()
    assert conflicts["total_conflicts"] == 13, (
        f"Expected 13 conflict entries, got {conflicts['total_conflicts']}"
    )


# ============================================================
# Tier 4: Combined validation (2 tests, need ALL 5 bugs fixed)
# ============================================================

def test_state_digest():
    """State digest must match expected value for correct merge."""
    state = load_state()
    assert state["state_digest"] == "440246c2793e4e9f", (
        f"Expected digest '440246c2793e4e9f', got '{state['state_digest']}'"
    )


def test_combined_correctness():
    """Combined check: registers, sets, and conflicts must all be correct."""
    state = load_state()
    conflicts = load_conflicts()

    # Register: user:1001:name resolved correctly
    reg = state["registers"]["user:1001:name"]
    assert reg["value"] == "Alice_v3", (
        f"Register wrong: expected 'Alice_v3', got '{reg['value']}'"
    )

    # Set: premium must appear twice (different element_ids from different replicas)
    tags = state["sets"]["user:1001:tags"]
    premium_count = sum(1 for e in tags if e["value"] == "premium")
    assert premium_count == 2, (
        f"Expected 2 'premium' entries in tags, got {premium_count}"
    )

    # Set: viewer must not be in user:1002:roles (removed by value)
    roles = state["sets"]["user:1002:roles"]
    role_values = [e["value"] for e in roles]
    assert "viewer" not in role_values, (
        f"'viewer' should not be in user:1002:roles but was found"
    )

    # Conflict: user:1010:region should NOT be in conflicts (only 2 replicas)
    conflict_keys = [e["key"] for e in conflicts["high_conflict_entries"]]
    assert "user:1010:region" not in conflict_keys, (
        f"user:1010:region should not be high-conflict"
    )
