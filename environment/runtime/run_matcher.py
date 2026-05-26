"""Regex pattern matching engine - main entry point."""

import json
import os
import sys

from .loader import PatternLoader
from .compiler import RegexCompiler
from .evaluator import PatternEvaluator


def main():
    config_path = "/app/runtime/config.ini"
    output_dir = "/app/runtime/output"
    os.makedirs(output_dir, exist_ok=True)

    loader = PatternLoader(config_path)
    patterns = loader.load_all_patterns()

    compiler = RegexCompiler()
    compiled = [compiler.compile(p) for p in patterns]

    evaluator = PatternEvaluator(config_path)
    results = evaluator.evaluate_all(compiled)

    # Sort results - Note: priority is shared across categories
    sorted_results = sorted(
        results,
        key=lambda m: (m["priority"], m["name"]),
    )

    match_results = []
    for r in sorted_results:
        match_results.append(
            {
                "pattern_name": r["name"],
                "category": r["category"],
                "priority": r["priority"],
                "input_text": r["input_text"],
                "matched": r["matched"],
                "match_span": r["match_span"],
                "match_count": r["match_count"],
            }
        )

    with open(os.path.join(output_dir, "match_results.json"), "w") as f:
        json.dump(match_results, f, indent=2)

    categories = sorted(set(r["category"] for r in sorted_results))
    total_matched = sum(1 for r in sorted_results if r["matched"])

    summary = {
        "total_patterns": len(patterns),
        "total_evaluated": len(sorted_results),
        "categories_processed": categories,
        "match_rate": round(total_matched / max(len(sorted_results), 1), 4),
        "patterns_by_category": {},
    }
    for cat in categories:
        cat_count = len(set(r["name"] for r in sorted_results if r["category"] == cat))
        summary["patterns_by_category"][cat] = cat_count

    with open(os.path.join(output_dir, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)


if __name__ == "__main__":
    main()
