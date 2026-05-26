"""Reassembles complete packets from ordered, validated fragments."""


def reassemble_flows(flows):
    """Reassemble packets from fragment sequences.

    Handles duplicate offsets from retransmissions and determines
    flow completeness based on expected byte coverage.
    """
    reassembled = {}

    for flow_key, flow_data in flows.items():
        fragments = flow_data["fragments"]
        expected_bytes = flow_data["expected_bytes"]

        assembled_fragments, retransmission_count = _deduplicate_fragments(fragments)

        # Compute total reassembled bytes
        total_bytes = sum(f["length"] for f in assembled_fragments)

        # Build reassembled payload from ordered fragments
        payload_parts = [f["payload"] for f in assembled_fragments]
        full_payload = "".join(payload_parts)

        # Determine flow status
        all_valid = all(f.get("checksum_valid", False) for f in assembled_fragments)
        if not all_valid:
            status = "corrupted"
        elif total_bytes >= expected_bytes:
            status = "complete"
        else:
            status = "incomplete"

        reassembled[flow_key] = {
            "flow_id": flow_data["flow_id"],
            "fragments_count": len(assembled_fragments),
            "reassembled_bytes": total_bytes,
            "status": status,
            "payload_preview": full_payload[:32],
            "retransmission_count": retransmission_count,
            "checksum_ok": all_valid,
        }

    return reassembled


def _deduplicate_fragments(fragments):
    """Remove duplicate fragments at the same offset.

    When fragments share an offset (retransmissions), only one copy
    should be kept for reassembly.
    """
    seen_offsets = set()
    assembled_fragments = []
    retransmission_count = 0

    for fragment in fragments:
        offset = fragment["offset"]
        # Skip duplicate offsets to avoid double-counting
        if offset not in seen_offsets:
            assembled_fragments.append(fragment)
            seen_offsets.add(offset)
        else:
            retransmission_count += 1

    return assembled_fragments, retransmission_count
