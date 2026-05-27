#!/usr/bin/env bash
set -e
cd /app
python3 /solution/repair_limiter.py
python3 -m runtime.run_limiter
