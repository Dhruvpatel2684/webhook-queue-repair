"""Automated repair for packet fragment reassembly engine."""

import re


def fix_fragment_sorter():
    path = "/app/runtime/fragment_sorter.py"
    with open(path, "r") as f:
        content = f.read()

    content = content.replace(
        'fragments.sort(key=lambda f: f["seq_num"])',
        'fragments.sort(key=lambda f: int(f["seq_num"]))',
    )

    with open(path, "w") as f:
        f.write(content)


def fix_checksum_validator():
    path = "/app/runtime/checksum_validator.py"
    with open(path, "r") as f:
        content = f.read()

    content = content.replace(
        "payload_bytes = payload.encode()[::-1]",
        "payload_bytes = payload.encode()",
    )

    with open(path, "w") as f:
        f.write(content)


def fix_reassembler():
    path = "/app/runtime/reassembler.py"
    with open(path, "r") as f:
        content = f.read()

    # Fix Bug 3: replace keep-first with keep-latest
    old_dedup = '''    seen_offsets = set()
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

    return assembled_fragments, retransmission_count'''

    new_dedup = '''    offset_map = {}
    retransmission_count = 0

    for fragment in fragments:
        offset = fragment["offset"]
        if offset in offset_map:
            retransmission_count += 1
        offset_map[offset] = fragment

    assembled_fragments = sorted(offset_map.values(), key=lambda f: f["offset"])
    return assembled_fragments, retransmission_count'''

    content = content.replace(old_dedup, new_dedup)

    # Fix Bug 5: change >= to ==
    content = content.replace(
        'elif total_bytes >= expected_bytes:',
        'elif total_bytes == expected_bytes:',
    )

    with open(path, "w") as f:
        f.write(content)


def fix_flow_grouper():
    path = "/app/runtime/flow_grouper.py"
    with open(path, "r") as f:
        content = f.read()

    content = content.replace(
        'max_gap_ms = config.getint("flows", "max_gap_ms")',
        'max_gap_ms = config.getint("flows.calibrated", "max_gap_ms")',
    )
    content = content.replace(
        'min_fragments = config.getint("flows", "min_fragments")',
        'min_fragments = config.getint("flows.calibrated", "min_fragments")',
    )

    with open(path, "w") as f:
        f.write(content)


if __name__ == "__main__":
    fix_fragment_sorter()
    fix_checksum_validator()
    fix_reassembler()
    fix_flow_grouper()
    print("All repairs applied successfully.")
