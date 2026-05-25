"""Detect merge conflicts based on write frequency."""
import configparser
import os

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "merge_config.ini")


def load_config():
    config = configparser.ConfigParser()
    config.read(CONFIG_PATH)
    return config


def detect_conflicts(operations, config):
    """Detect keys with high write contention.

    A key is marked high-conflict when the number of write operations
    from distinct replicas exceeds the configured threshold.
    """
    threshold = config.getint("conflicts", "conflict_threshold")

    # Count distinct replica writes per key
    key_writes = {}
    for op in operations:
        if op["op_type"] == "set_register":
            key = op["key"]
            if key not in key_writes:
                key_writes[key] = set()
            key_writes[key].add(op["replica"])

    # Also count set operations
    for op in operations:
        if op["op_type"] in ("add_set", "remove_set"):
            key = op["key"]
            if key not in key_writes:
                key_writes[key] = set()
            key_writes[key].add(op["replica"])

    conflicts = []
    for key, replicas in key_writes.items():
        write_count = len(replicas)
        if write_count >= threshold:
            conflicts.append({
                "key": key,
                "write_count": write_count,
                "replicas": sorted(replicas),
                "severity": "high",
            })

    return sorted(conflicts, key=lambda c: c["key"])
