"""Repair script for WAL Replay Recovery Engine.

Fixes 5 bugs:
1. txn_tracker.py: LSN comparison uses string instead of int
2. page_reconstructor.py: Writes sorted by txn_id instead of LSN
3. page_reconstructor.py: Uses before_image instead of after_image
4. txn_tracker.py: Reads from wrong config section
5. checkpoint_handler.py: Uses >= instead of > for checkpoint boundary
"""

import os


def fix_file(filepath, replacements):
    with open(filepath, "r") as f:
        content = f.read()
    for old, new in replacements:
        content = content.replace(old, new)
    with open(filepath, "w") as f:
        f.write(content)


def main():
    runtime_dir = "/app/runtime"

    # Bug 1: Fix LSN string comparison in txn_tracker.py
    fix_file(
        os.path.join(runtime_dir, "txn_tracker.py"),
        [
            (
                'if record["lsn"] > self.last_committed_lsn:',
                'if int(record["lsn"]) > int(self.last_committed_lsn):',
            ),
        ],
    )

    # Bug 4: Fix wrong config section in txn_tracker.py
    fix_file(
        os.path.join(runtime_dir, "txn_tracker.py"),
        [
            (
                'mode = self.config.get("recovery", "recovery_mode")',
                'mode = self.config.get("recovery.redo", "recovery_mode")',
            ),
        ],
    )

    # Bug 2: Fix write ordering in page_reconstructor.py
    fix_file(
        os.path.join(runtime_dir, "page_reconstructor.py"),
        [
            (
                'page_writes.sort(key=lambda w: (w["page_id"], w["txn_id"]))',
                'page_writes.sort(key=lambda w: (w["page_id"], int(w["lsn"])))',
            ),
        ],
    )

    # Bug 3: Fix page state - must overwrite on each write (last write wins)
    fix_file(
        os.path.join(runtime_dir, "page_reconstructor.py"),
        [
            (
                '            # Preserve earliest write to each page as the base state\n'
                '            if page_id not in self.page_state:\n'
                '                self.page_state[page_id] = record["after_image"]',
                '            # Apply write - last write to each page wins\n'
                '            self.page_state[page_id] = record["after_image"]',
            ),
        ],
    )

    # Bug 5: Fix checkpoint boundary >= to > in checkpoint_handler.py
    fix_file(
        os.path.join(runtime_dir, "checkpoint_handler.py"),
        [
            (
                'if int(record["lsn"]) >= checkpoint_lsn:',
                'if int(record["lsn"]) > checkpoint_lsn:',
            ),
        ],
    )

    print("All 5 bugs fixed. Re-running recovery...")

    # Re-run the recovery engine
    os.chdir("/app")
    os.system("python3 -m runtime.run_recovery")
    print("Recovery complete.")


if __name__ == "__main__":
    main()
