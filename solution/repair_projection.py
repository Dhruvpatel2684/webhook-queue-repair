"""
Repair script for the CQRS event projection system.

Fixes processing logic errors and re-runs the projection engine.
"""

import os


def fix_window_processor():
    """Fix off-by-one error in window boundary calculation."""
    filepath = "/app/runtime/window_processor.py"
    with open(filepath, "r") as f:
        content = f.read()

    # The window end boundary extends one past where it should
    content = content.replace(
        "window_end = seq_start + config.size\n",
        "window_end = seq_start + config.size - 1\n"
    )

    with open(filepath, "w") as f:
        f.write(content)
    print("Fixed: window_processor.py - window boundary calculation")


def fix_dedup_engine():
    """Fix deduplication hash key computation."""
    filepath = "/app/runtime/dedup_engine.py"
    with open(filepath, "r") as f:
        content = f.read()

    # The dedup key should use version not timestamp for identity
    content = content.replace(
        'raw_key = f"{event.stream_id}:{event.seq}:{event.timestamp}"',
        'raw_key = f"{event.stream_id}:{event.seq}:{event.version}"'
    )

    with open(filepath, "w") as f:
        f.write(content)
    print("Fixed: dedup_engine.py - dedup key field")


def fix_projection_last_write():
    """Fix last_write merge mode implementation."""
    filepath = "/app/runtime/projection_engine.py"
    with open(filepath, "r") as f:
        content = f.read()

    # last_write should return new_value directly, not max()
    old_lines = '    elif mode == "last_write":\n        return max(current_value, new_value)'
    new_lines = '    elif mode == "last_write":\n        return new_value'
    content = content.replace(old_lines, new_lines)

    with open(filepath, "w") as f:
        f.write(content)
    print("Fixed: projection_engine.py - last_write merge mode")


def fix_event_parser_timezone():
    """Fix timezone offset conversion direction."""
    filepath = "/app/runtime/event_parser.py"
    with open(filepath, "r") as f:
        content = f.read()

    # The timezone offset application is inverted:
    # +offset means local is ahead of UTC -> must subtract to get UTC
    # -offset means local is behind UTC -> must add to get UTC
    old_block = (
        '        # Convert local time to UTC by applying the timezone offset\n'
        '        if sign == "+":\n'
        '            utc_ts = local_ts + timedelta(hours=offset_h, minutes=offset_m)\n'
        '        else:\n'
        '            utc_ts = local_ts - timedelta(hours=offset_h, minutes=offset_m)'
    )
    new_block = (
        '        # Convert local time to UTC by applying the timezone offset\n'
        '        if sign == "+":\n'
        '            utc_ts = local_ts - timedelta(hours=offset_h, minutes=offset_m)\n'
        '        else:\n'
        '            utc_ts = local_ts + timedelta(hours=offset_h, minutes=offset_m)'
    )
    content = content.replace(old_block, new_block)

    with open(filepath, "w") as f:
        f.write(content)
    print("Fixed: event_parser.py - timezone offset direction")


def fix_projection_priority():
    """Fix priority conflict resolution comparison."""
    filepath = "/app/runtime/projection_engine.py"
    with open(filepath, "r") as f:
        content = f.read()

    # Higher priority should win (use > not <)
    content = content.replace(
        "if new_projection.priority < existing.priority:",
        "if new_projection.priority > existing.priority:"
    )

    with open(filepath, "w") as f:
        f.write(content)
    print("Fixed: projection_engine.py - priority comparison")


def main():
    print("=" * 50)
    print("CQRS Projection System - Applying Repairs")
    print("=" * 50)

    fix_window_processor()
    fix_dedup_engine()
    fix_projection_last_write()
    fix_event_parser_timezone()
    fix_projection_priority()

    print("\nAll fixes applied. Re-running projection engine...")
    os.system("cd /app && python3 -m runtime.run_projection")
    print("\nRepair complete.")


if __name__ == "__main__":
    main()
