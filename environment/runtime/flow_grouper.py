"""Groups fragments into logical flows based on flow_id and temporal proximity."""

import configparser
from collections import defaultdict


def group_into_flows(fragments, config_path):
    """Group fragments by flow_id, splitting on temporal gaps.

    Fragments sharing a flow_id that arrive with a gap exceeding the
    configured maximum inter-fragment interval are assigned to separate
    logical flows.
    """
    config = configparser.ConfigParser()
    config.read(config_path)

    # Read flow grouping parameters from configuration
    max_gap_ms = config.getint("flows", "max_gap_ms")
    min_fragments = config.getint("flows", "min_fragments")

    # Group fragments by their declared flow identifier
    by_flow_id = defaultdict(list)
    for fragment in fragments:
        by_flow_id[fragment["flow_id"]].append(fragment)

    flows = {}
    flow_counter = 0

    for flow_id, flow_fragments in by_flow_id.items():
        # Sort by timestamp to detect temporal gaps
        flow_fragments.sort(key=lambda f: f["timestamp_ms"])

        # Split into sub-flows based on inter-fragment gap threshold
        current_group = [flow_fragments[0]]

        for i in range(1, len(flow_fragments)):
            gap = flow_fragments[i]["timestamp_ms"] - flow_fragments[i - 1]["timestamp_ms"]
            if gap > max_gap_ms:
                # Gap exceeds threshold, start new sub-flow
                if len(current_group) >= min_fragments:
                    flow_key = flow_id if flow_counter == 0 or flow_id not in flows else f"{flow_id}-{flow_counter}"
                    if flow_id not in flows:
                        flow_key = flow_id
                    else:
                        flow_key = f"{flow_id}_{flow_counter}"
                    flows[flow_key] = {
                        "flow_id": flow_key,
                        "fragments": current_group,
                        "expected_bytes": _compute_expected_bytes(current_group),
                    }
                    flow_counter += 1
                current_group = [flow_fragments[i]]
            else:
                current_group.append(flow_fragments[i])

        # Final group
        if len(current_group) >= min_fragments:
            if flow_id not in flows:
                flow_key = flow_id
            else:
                flow_key = f"{flow_id}_{flow_counter}"
            flows[flow_key] = {
                "flow_id": flow_key,
                "fragments": current_group,
                "expected_bytes": _compute_expected_bytes(current_group),
            }
            flow_counter += 1

    return flows


def _compute_expected_bytes(fragments):
    """Compute expected total bytes as max(offset + length) across fragments."""
    max_end = 0
    for f in fragments:
        end = f["offset"] + f["length"]
        if end > max_end:
            max_end = end
    return max_end
