#!/bin/bash
set -e
cd /app

# Apply the repair patches and re-run the scheduler with corrected logic
python3 /solution/repair_scheduler.py
