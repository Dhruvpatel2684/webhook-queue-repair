#!/usr/bin/env bash
set -e
cd /app
python3 -m runtime.run_limiter
uv run --with pytest pytest /tests/test_limiter.py -v
