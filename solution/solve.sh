#!/bin/bash
set -e
cd /app

# Apply the repair patches and re-run the engine with corrected logic
python3 /solution/repair_correlation.py
