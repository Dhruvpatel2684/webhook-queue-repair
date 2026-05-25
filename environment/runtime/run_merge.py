"""CRDT Merge Engine - Main Entry Point."""
import os
import sys

RUNTIME_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(RUNTIME_DIR))

from runtime.op_loader import load_all_operations
from runtime.lww_register import load_config, merge_registers
from runtime.orset_merger import merge_sets
from runtime.conflict_detector import detect_conflicts
from runtime.state_writer import write_state


def main():
    operations = load_all_operations()
    print(f"Loaded {len(operations)} operations from replica logs")

    config = load_config()

    registers = merge_registers(operations, config)
    print(f"Merged {len(registers)} register entries")

    sets = merge_sets(operations)
    print(f"Merged {len(sets)} set entries")

    conflicts = detect_conflicts(operations, config)
    print(f"Detected {len(conflicts)} conflict entries")

    output_dir = os.path.join(RUNTIME_DIR, "output")
    write_state(registers, sets, conflicts, output_dir)
    print(f"State written to {output_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
