"""Entry point for the packet fragment reassembly engine."""

import os
import sys

from runtime.capture_loader import load_captures
from runtime.flow_grouper import group_into_flows
from runtime.fragment_sorter import sort_flow_fragments
from runtime.checksum_validator import validate_checksums
from runtime.reassembler import reassemble_flows
from runtime.report_writer import write_reports


def main():
    runtime_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(runtime_dir, "reassembly.ini")
    output_dir = os.path.join(runtime_dir, "output")
    os.makedirs(output_dir, exist_ok=True)

    # Step 1: Load all fragment captures
    fragments = load_captures(runtime_dir)

    # Step 2: Group fragments into logical flows
    flows = group_into_flows(fragments, config_path)

    # Step 3: Sort fragments within each flow by sequence number
    sorted_flows = sort_flow_fragments(flows)

    # Step 4: Validate fragment checksums
    validated_flows, checksum_failures = validate_checksums(sorted_flows)

    # Step 5: Reassemble packets from ordered, validated fragments
    reassembled = reassemble_flows(validated_flows)

    # Step 6: Write output reports
    write_reports(reassembled, checksum_failures, len(fragments), output_dir)


if __name__ == "__main__":
    main()
