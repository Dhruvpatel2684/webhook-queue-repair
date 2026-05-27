"""Repair script for the multi-tenant rate limiting engine.

Applies four targeted patches to fix configuration parsing, capacity
sourcing, token accumulation, and sort ordering issues.
"""

import os

BASE_DIR = "/app/runtime"


def patch_classifier():
    """Fix tier classification to handle whitespace in config values."""
    filepath = os.path.join(BASE_DIR, "classifier.py")
    with open(filepath, "r") as f:
        content = f.read()

    # The split produces items with leading whitespace that won't match
    # tier names from request entries. Strip each item after splitting.
    old = 'valid_tiers = set(tier_str.split(","))'
    new = 'valid_tiers = set(t.strip() for t in tier_str.split(","))'
    content = content.replace(old, new)

    with open(filepath, "w") as f:
        f.write(content)


def patch_throttler_capacity():
    """Fix bucket capacity to read from correct config section."""
    filepath = os.path.join(BASE_DIR, "throttler.py")
    with open(filepath, "r") as f:
        content = f.read()

    # The capacity should come from limiter.tokens section (100)
    # not from limiter section (1000)
    old = 'capacity = config.getint("limiter", "bucket_capacity")'
    new = 'capacity = config.getint("limiter.tokens", "bucket_capacity")'
    content = content.replace(old, new)

    with open(filepath, "w") as f:
        f.write(content)


def patch_throttler_accumulation():
    """Fix double-counting of tokens in second pass."""
    filepath = os.path.join(BASE_DIR, "throttler.py")
    with open(filepath, "r") as f:
        content = f.read()

    # The second pass re-adds token costs that were already counted
    # in the first pass. Change to a tracking assignment instead.
    old = '            consumption[key]["tokens_used"] += int(tokens * weight)'
    new = '            consumption[key]["weighted_check"] = int(tokens * weight)'
    content = content.replace(old, new)

    with open(filepath, "w") as f:
        f.write(content)


def patch_run_limiter_sort():
    """Fix sort key to include service_tier for stable ordering."""
    filepath = os.path.join(BASE_DIR, "run_limiter.py")
    with open(filepath, "r") as f:
        content = f.read()

    old = 'decisions.sort(key=lambda d: (d.throttle_score, d.client_id))'
    new = 'decisions.sort(key=lambda d: (d.throttle_score, d.service_tier, d.client_id))'
    content = content.replace(old, new)

    with open(filepath, "w") as f:
        f.write(content)


if __name__ == "__main__":
    patch_classifier()
    patch_throttler_capacity()
    patch_throttler_accumulation()
    patch_run_limiter_sort()
    print("[repair] All four patches applied successfully.")
