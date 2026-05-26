"""Test suite for packet fragment reassembly engine."""

import json
import os

OUTPUT_DIR = "/app/runtime/output"


def load_state():
    with open(os.path.join(OUTPUT_DIR, "reassembly_state.json")) as f:
        return json.load(f)


def load_report():
    with open(os.path.join(OUTPUT_DIR, "reassembly_report.json")) as f:
        return json.load(f)


# --- Tier 1: structural tests (pass with bugs) ---


def test_output_files_exist():
    assert os.path.exists(os.path.join(OUTPUT_DIR, "reassembly_state.json"))
    assert os.path.exists(os.path.join(OUTPUT_DIR, "reassembly_report.json"))


def test_state_has_required_fields():
    state = load_state()
    assert "flows" in state
    assert "total_flows" in state
    assert "total_fragments_processed" in state
    assert "checksum_failures" in state
    assert "state_digest" in state


def test_report_has_required_fields():
    report = load_report()
    assert "complete_flows" in report
    assert "incomplete_flows" in report
    assert "corrupted_flows" in report
    assert "retransmission_count" in report
    assert "total_bytes_reassembled" in report
    assert "flow_details" in report


def test_total_fragments_count():
    state = load_state()
    assert state["total_fragments_processed"] == 65, (
        f"Expected 65 fragments processed, got {state['total_fragments_processed']}"
    )


def test_flows_are_dicts():
    state = load_state()
    assert isinstance(state["flows"], dict)
    for flow_key, flow_data in state["flows"].items():
        assert "fragments_count" in flow_data
        assert "reassembled_bytes" in flow_data
        assert "status" in flow_data


def test_flow_details_is_list():
    report = load_report()
    assert isinstance(report["flow_details"], list)
    assert len(report["flow_details"]) > 0


def test_report_has_flow_details():
    report = load_report()
    for detail in report["flow_details"]:
        assert "flow_id" in detail
        assert "fragment_count" in detail
        assert "status" in detail
        assert "checksum_ok" in detail


# --- Tier 2: need Bug 4 + Bug 1 fixed ---


def test_correct_flow_count():
    state = load_state()
    assert state["total_flows"] == 8, (
        f"Expected 8 flows, got {state['total_flows']}"
    )


def test_flow_003_fragment_count():
    state = load_state()
    assert "flow-003" in state["flows"], "flow-003 not found in state"
    count = state["flows"]["flow-003"]["fragments_count"]
    assert count == 12, (
        f"Expected flow-003 to have 12 fragments, got {count}"
    )


def test_flow_003_ordering():
    state = load_state()
    preview = state["flows"]["flow-003"]["payload_preview"]
    expected = "S01_flow3_reassemblyS02_flow3_re"
    assert preview == expected, (
        f"flow-003 payload ordering wrong"
    )


# --- Tier 3: need Bugs 2+3+5 fixed ---


def test_checksum_failures():
    state = load_state()
    assert state["checksum_failures"] == 0, (
        f"Expected 0 checksum failures, got {state['checksum_failures']}"
    )


def test_retransmission_handling():
    report = load_report()
    assert report["retransmission_count"] == 4, (
        f"Expected 4 retransmissions, got {report['retransmission_count']}"
    )


def test_complete_flow_count():
    report = load_report()
    assert report["complete_flows"] == 8, (
        f"Expected 8 complete flows, got {report['complete_flows']}"
    )


# --- Tier 4: need ALL 5 bugs fixed ---


def test_state_digest():
    state = load_state()
    assert state["state_digest"] == "3f20d226c816ee6a", (
        f"State digest mismatch"
    )


def test_combined():
    state = load_state()
    report = load_report()
    assert state["total_flows"] == 8, f"Expected 8 flows, got {state['total_flows']}"
    assert report["complete_flows"] == 8, f"Expected 8 complete, got {report['complete_flows']}"
    assert state["checksum_failures"] == 0, f"Expected 0 failures, got {state['checksum_failures']}"
    assert report["total_bytes_reassembled"] == 3860, (
        f"Expected total bytes 3860, got {report['total_bytes_reassembled']}"
    )
