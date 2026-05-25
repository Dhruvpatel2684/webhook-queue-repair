"""LWW Register merge - Last Writer Wins semantics."""
import configparser
import os

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "merge_config.ini")


def load_config():
    config = configparser.ConfigParser()
    config.read(CONFIG_PATH)
    return config


def merge_registers(operations, config):
    """Merge set_register operations using Last-Writer-Wins.

    For each key, the operation with the highest timestamp wins.
    On timestamp ties, replica priority determines the winner.
    """
    registers = {}
    register_ops = [op for op in operations if op["op_type"] == "set_register"]

    # Load replica priority for tie-breaking
    priority_raw = config.get("merge", "replica_priority")
    priority_order = [r.strip() for r in priority_raw.split(",")]

    for op in register_ops:
        key = op["key"]
        if key not in registers:
            registers[key] = op
            continue

        current = registers[key]
        # Compare timestamps to determine winner
        if op["timestamp"] > current["timestamp"]:
            registers[key] = op
        elif op["timestamp"] == current["timestamp"]:
            # Tie-break by replica priority (lower index = higher priority)
            op_priority = priority_order.index(op["replica"]) if op["replica"] in priority_order else 999
            cur_priority = priority_order.index(current["replica"]) if current["replica"] in priority_order else 999
            if op_priority < cur_priority:
                registers[key] = op

    return registers
