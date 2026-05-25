#!/bin/bash
set -e

# Step 1: Run the broken replay engine to generate initial (incorrect) output
python3 /app/runtime/replay_engine.py

# Step 2: Run the repair script which re-processes delivery_logs.txt with
# corrected logic:
#   - Fixes total_attempts counting (only from ATTEMPT events, not ENQUEUE)
#   - Fixes delivery_rate formula (delivered/total_webhooks, not successes/attempts)
#   - Fixes mean_latency to only average delivered webhook durations
#   - Fixes fingerprint to use sorted webhook iteration for determinism
python3 /solution/repair_webhook.py
