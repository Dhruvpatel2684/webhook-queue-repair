#!/bin/bash
set -e

# Step 1: Run the broken replay engine to generate initial (incorrect) output
python3 /app/runtime/replay_engine.py

# Step 2: Run the repair script which re-processes delivery_logs.txt with
# corrected dependency analysis:
#   - Fixes independence check to use transitive closure (reachability)
#   - Fixes priority computation to use critical path length (longest-path-from)
#   - Fixes parallel set algorithm to use ascending priority (antichain maximization)
python3 /solution/repair_webhook.py
