#!/bin/bash
set -euo pipefail

mkdir -p /logs/verifier

# Run the entrypoint if output doesn't exist yet
if [ ! -f /app/runtime/webhook_status.jsonl ]; then
    python3 /app/runtime/replay_engine.py
fi

set +e
uv run --with pytest pytest -v /tests/test_webhook.py
TEST_EXIT=$?
set -e

if [ "$TEST_EXIT" -eq 0 ]; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi

cat /logs/verifier/reward.txt
exit "$TEST_EXIT"
