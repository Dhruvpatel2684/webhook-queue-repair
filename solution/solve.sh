#!/bin/bash
set -e

cd "$(dirname "$0")/../environment/runtime"

python3 /app/solution/patch_gc.py
python3 run_gc.py
