"""WAL Segment Loader — reads JSONL WAL segment files in sorted order."""

import json
import glob
import os


def load_wal_segments(segment_dir, segment_pattern):
    """Load all WAL segment files matching the pattern from the given directory.

    Returns a list of all WAL records across all segments, in file order.
    Segments are loaded in lexicographic filename order.
    """
    pattern = os.path.join(segment_dir, segment_pattern)
    segment_files = sorted(glob.glob(pattern))

    all_records = []
    for filepath in segment_files:
        with open(filepath, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    record = json.loads(line)
                    all_records.append(record)

    return all_records
