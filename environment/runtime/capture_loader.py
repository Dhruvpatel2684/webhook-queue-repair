"""Loads fragment captures from JSONL source files."""

import json
import os
import configparser


def load_captures(runtime_dir):
    """Load all fragments from configured capture source files."""
    config_path = os.path.join(runtime_dir, "reassembly.ini")
    config = configparser.ConfigParser()
    config.read(config_path)

    source_files = config.get("capture", "sources").split(",")
    fragments = []

    for source_file in source_files:
        file_path = os.path.join(runtime_dir, source_file.strip())
        if not os.path.exists(file_path):
            continue
        with open(file_path, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    fragment = json.loads(line)
                    fragments.append(fragment)

    return fragments
