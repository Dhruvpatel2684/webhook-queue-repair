"""Writes reassembly output reports in JSON format."""

import hashlib
import json
import os


def write_reports(reassembled, checksum_failures, total_fragments, output_dir):
    """Write reassembly state and summary report files."""
    os.makedirs(output_dir, exist_ok=True)

    state = _build_state(reassembled, checksum_failures, total_fragments)
    report = _build_report(reassembled, checksum_failures)

    state_path = os.path.join(output_dir, "reassembly_state.json")
    report_path = os.path.join(output_dir, "reassembly_report.json")

    with open(state_path, "w") as f:
        json.dump(state, f, indent=2)

    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)


def _build_state(reassembled, checksum_failures, total_fragments):
    """Build the reassembly_state.json structure."""
    flows = {}
    for flow_key, data in reassembled.items():
        flows[flow_key] = {
            "fragments_count": data["fragments_count"],
            "reassembled_bytes": data["reassembled_bytes"],
            "status": data["status"],
            "payload_preview": data["payload_preview"],
        }

    state = {
        "flows": flows,
        "total_flows": len(flows),
        "total_fragments_processed": total_fragments,
        "checksum_failures": checksum_failures,
        "state_digest": _compute_digest(flows),
    }
    return state


def _build_report(reassembled, checksum_failures):
    """Build the reassembly_report.json structure."""
    complete_flows = sum(1 for d in reassembled.values() if d["status"] == "complete")
    incomplete_flows = sum(1 for d in reassembled.values() if d["status"] == "incomplete")
    corrupted_flows = sum(1 for d in reassembled.values() if d["status"] == "corrupted")
    total_retransmissions = sum(d["retransmission_count"] for d in reassembled.values())
    total_bytes = sum(d["reassembled_bytes"] for d in reassembled.values())

    flow_details = []
    for flow_key, data in reassembled.items():
        flow_details.append({
            "flow_id": data["flow_id"],
            "fragment_count": data["fragments_count"],
            "status": data["status"],
            "checksum_ok": data["checksum_ok"],
        })

    report = {
        "complete_flows": complete_flows,
        "incomplete_flows": incomplete_flows,
        "corrupted_flows": corrupted_flows,
        "retransmission_count": total_retransmissions,
        "total_bytes_reassembled": total_bytes,
        "flow_details": flow_details,
    }
    return report


def _compute_digest(flows):
    """Compute a 16-character hex digest of the flow state for integrity verification."""
    canonical = json.dumps(flows, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]
