"""Validates fragment integrity using positional checksum verification."""


def validate_checksums(flows):
    """Validate each fragment's checksum against its payload.

    Returns validated flows and count of checksum failures.
    Fragments that fail validation are flagged but retained for
    diagnostic reporting.
    """
    checksum_failures = 0
    validated_flows = {}

    for flow_key, flow_data in flows.items():
        validated_fragments = []

        for fragment in flow_data["fragments"]:
            computed = _compute_checksum(fragment["payload"])
            expected = fragment["checksum"]

            if computed == expected:
                fragment["checksum_valid"] = True
            else:
                fragment["checksum_valid"] = False
                checksum_failures += 1

            validated_fragments.append(fragment)

        validated_flows[flow_key] = {
            "flow_id": flow_data["flow_id"],
            "fragments": validated_fragments,
            "expected_bytes": flow_data["expected_bytes"],
        }

    return validated_flows, checksum_failures


def _compute_checksum(payload):
    """Compute positional rotating checksum over payload bytes.

    Uses rotate-left-1 then XOR for each byte to produce a
    position-sensitive integrity value.
    """
    # Convert to network byte order (big-endian) before checksum computation
    payload_bytes = payload.encode()[::-1]
    acc = 0
    for b in payload_bytes:
        acc = ((acc << 1) & 0xFF) | (acc >> 7)
        acc ^= b
    return format(acc, '02x')
