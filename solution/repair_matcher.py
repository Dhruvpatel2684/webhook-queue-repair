"""Repair script for the regex pattern matching engine."""

import subprocess
import sys


def fix_category_parsing():
    """Fix whitespace handling when parsing enabled_categories from config."""
    filepath = "/app/runtime/loader.py"
    with open(filepath, "r") as f:
        content = f.read()

    content = content.replace(
        'self._config.get("matcher", "enabled_categories").split(",")\n        )',
        'c.strip() for c in self._config.get("matcher", "enabled_categories").split(",")\n        )',
    )

    with open(filepath, "w") as f:
        f.write(content)


def fix_backtrack_limit():
    """Read max_backtrack from the correct config section."""
    filepath = "/app/runtime/evaluator.py"
    with open(filepath, "r") as f:
        content = f.read()

    content = content.replace(
        'self._config.getint("matcher", "max_backtrack")',
        'self._config.getint("matcher.limits", "max_backtrack")',
    )

    with open(filepath, "w") as f:
        f.write(content)


def fix_match_count_accumulation():
    """Use assignment instead of accumulation for match counts."""
    filepath = "/app/runtime/evaluator.py"
    with open(filepath, "r") as f:
        content = f.read()

    content = content.replace(
        'results[pattern.name]["match_count"] += count',
        'results[pattern.name]["match_count"] = count',
    )

    with open(filepath, "w") as f:
        f.write(content)


def fix_sort_order():
    """Add category to sort key for deterministic ordering."""
    filepath = "/app/runtime/run_matcher.py"
    with open(filepath, "r") as f:
        content = f.read()

    content = content.replace(
        'key=lambda m: (m["priority"], m["name"])',
        'key=lambda m: (m["priority"], m["category"], m["name"])',
    )

    with open(filepath, "w") as f:
        f.write(content)


def main():
    fix_category_parsing()
    fix_backtrack_limit()
    fix_match_count_accumulation()
    fix_sort_order()

    result = subprocess.run(
        [sys.executable, "-m", "runtime.run_matcher"],
        cwd="/app",
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"Engine execution failed: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    print("All fixes applied and engine re-executed successfully.")


if __name__ == "__main__":
    main()
