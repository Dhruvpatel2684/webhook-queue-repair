"""Load pass definitions from CSV manifest files."""

import csv
import os
import configparser


def load_config(config_path):
    """Load and return the passes configuration."""
    parser = configparser.ConfigParser()
    parser.read(config_path)
    return parser


def load_passes(runtime_dir):
    """Load all pass definitions from CSV files in the runtime directory.

    Returns a list of pass records with fields:
        pass_id, module_name, category, priority, depends_on,
        estimated_cost_ms, submitted_order, source_file
    """
    csv_files = [
        "passes_frontend.csv",
        "passes_middle.csv",
        "passes_backend.csv",
    ]

    all_passes = []
    for csv_file in csv_files:
        filepath = os.path.join(runtime_dir, csv_file)
        if not os.path.exists(filepath):
            continue
        with open(filepath, "r", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                record = {
                    "pass_id": row["pass_id"].strip(),
                    "module_name": row["module_name"].strip(),
                    "category": row["category"].strip(),
                    "priority": int(row["priority"].strip()),
                    "depends_on": [
                        d.strip() for d in row["depends_on"].split(",") if d.strip()
                    ],
                    "estimated_cost_ms": int(row["estimated_cost_ms"].strip()),
                    "submitted_order": int(row["submitted_order"].strip()),
                    "source_file": csv_file,
                }
                all_passes.append(record)

    return all_passes
