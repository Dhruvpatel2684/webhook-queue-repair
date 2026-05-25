"""Load operation logs from replica JSONL files."""
import json
import os
import glob

DATA_DIR = os.path.dirname(os.path.abspath(__file__))


def load_all_operations():
    """Load operations from all replica JSONL files, sorted by timestamp."""
    all_ops = []
    pattern = os.path.join(DATA_DIR, "ops_replica_*.jsonl")
    for filepath in sorted(glob.glob(pattern)):
        with open(filepath, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    op = json.loads(line)
                    all_ops.append(op)
    all_ops.sort(key=lambda o: o["timestamp"])
    return all_ops
