#!/bin/bash
set -e

cd /app

# Run the recovery engine to generate output
python3 -m runtime.run_recovery

# Run the test suite
pytest /tests/test_recovery.py -v
