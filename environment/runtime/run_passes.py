"""Entry point for the compiler pass scheduler."""

import os
import sys

from runtime.pass_loader import load_config, load_passes
from runtime.dependency_resolver import resolve_and_schedule
from runtime.phase_aggregator import aggregate_phase_summaries
from runtime.report_writer import write_reports


def main():
    runtime_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(runtime_dir, "passes.ini")
    output_dir = os.path.join(os.path.dirname(runtime_dir), "output")

    config = load_config(config_path)
    passes = load_passes(runtime_dir)

    if not passes:
        print("Error: No passes loaded from manifest files.", file=sys.stderr)
        sys.exit(1)

    schedule_result = resolve_and_schedule(passes, config)
    category_summaries = aggregate_phase_summaries(schedule_result)
    schedule_path, report_path = write_reports(schedule_result, category_summaries, output_dir)

    print(f"Scheduling complete: {len(schedule_result['scheduled'])} scheduled, "
          f"{len(schedule_result['rejected'])} rejected, "
          f"{len(schedule_result['blocked'])} blocked")
    print(f"Output written to {output_dir}")


if __name__ == "__main__":
    main()
