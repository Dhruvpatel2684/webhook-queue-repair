# Regex Engine Pattern Matcher - Debugging Task

## Overview

You are given a regex pattern matching engine that reads pattern definitions from
text files, compiles them into NFA (Nondeterministic Finite Automaton) state machines,
evaluates each pattern against a set of test inputs, and writes structured JSON output.

The system is currently producing incorrect results. Your task is to identify and fix
the bugs so that all tests pass.

## System Architecture

Global system-wide tooling is provided via Python 3.11 with the `uv` package manager
for running tests. The matching engine consists of four main modules:

### Modules

1. **Loader** (`/app/runtime/loader.py`): Reads pattern definitions from data files
   in `/app/runtime/data/` and filters them by the enabled categories listed in the
   configuration file.

2. **Compiler** (`/app/runtime/compiler.py`): Compiles regex pattern strings into NFA
   representations using Thompson's construction. Each compiled pattern contains a list
   of states with labeled transitions.

3. **Evaluator** (`/app/runtime/evaluator.py`): Runs compiled NFAs against test input
   strings. Uses a backtrack-limited simulation to prevent excessive computation on
   complex patterns. Processes patterns in configurable batch sizes.

4. **Entry Point** (`/app/runtime/run_matcher.py`): Orchestrates the full flow from
   loading through evaluation, sorts results, and writes output JSON files.

### Configuration

The configuration file at `/app/runtime/config.ini` contains:

- `[matcher]` section: general matcher settings including enabled categories
- `[matcher.limits]` section: execution limits including backtrack ceiling and batch size
- `[output]` section: output format preferences

### Data Files

Pattern definitions live in `/app/runtime/data/` as text files. Each line follows
the format:

```
name|priority|category|regex|test_input1;test_input2;...
```

Three category files are provided:
- `/app/runtime/data/patterns_core.txt` (20 patterns, category: core)
- `/app/runtime/data/patterns_extended.txt` (20 patterns, category: extended)
- `/app/runtime/data/patterns_unicode.txt` (18 patterns, category: unicode)

## Running the Engine

From the `/app` working directory:

```bash
python3 -m runtime.run_matcher
```

This produces two output files in `/app/runtime/output/`:

### Output: `/app/runtime/output/match_results.json`

An array of result objects, sorted by priority (ascending), then category
(alphabetical), then pattern name (alphabetical). Each object contains:

```json
{
  "pattern_name": "string - name of the pattern",
  "category": "string - category the pattern belongs to",
  "priority": "integer - priority level (1-10)",
  "input_text": "string - the test input that was evaluated",
  "matched": "boolean - whether the pattern matched this input",
  "match_span": "[start, end] or null - character positions of the match",
  "match_count": "integer - total matches across all inputs for this pattern"
}
```

### Output: `/app/runtime/output/summary.json`

A summary object containing:

```json
{
  "total_patterns": "integer - number of pattern definitions loaded",
  "total_evaluated": "integer - number of individual evaluations performed",
  "categories_processed": ["list of category strings that were processed"],
  "match_rate": "float - ratio of matched evaluations to total",
  "patterns_by_category": {"category": "count of unique patterns per category"}
}
```

## Expected Behavior

When working correctly, the engine should:

1. Load patterns from all three category files (core, extended, unicode)
2. Apply the backtrack limit from the `[matcher.limits]` configuration section
3. Report accurate match counts (each pattern's count equals how many of its test
   inputs actually match)
4. Sort output deterministically by priority, then category, then pattern name

## Debugging Tips

- Check how configuration values are parsed and which sections they come from
- Trace the data flow from loading through evaluation to output
- Verify that category filtering correctly includes all expected categories
- Examine how results are accumulated across processing passes
- Confirm the sort key produces stable, deterministic ordering when patterns from
  different categories share the same priority value
