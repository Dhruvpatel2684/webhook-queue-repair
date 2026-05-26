"""Sorts fragments within each flow by sequence number for ordered reassembly."""


def sort_flow_fragments(flows):
    """Sort fragments within each flow by their sequence number.

    Fragments arrive from multiple streams and may be interleaved.
    Sorting by sequence number ensures correct reassembly order.
    """
    sorted_flows = {}

    for flow_key, flow_data in flows.items():
        fragments = list(flow_data["fragments"])

        # Sort fragments by sequence number for proper ordering
        fragments.sort(key=lambda f: f["seq_num"])

        sorted_flows[flow_key] = {
            "flow_id": flow_data["flow_id"],
            "fragments": fragments,
            "expected_bytes": flow_data["expected_bytes"],
        }

    return sorted_flows
