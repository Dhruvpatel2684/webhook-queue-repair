"""Pattern definition loader for the regex matching engine."""

import configparser
import os
from dataclasses import dataclass, field
from typing import List


@dataclass
class PatternDef:
    name: str
    priority: int
    category: str
    regex: str
    test_inputs: List[str] = field(default_factory=list)


class PatternLoader:
    """Loads and filters pattern definitions from data files."""

    def __init__(self, config_path: str):
        self._config = configparser.ConfigParser()
        self._config.read(config_path)
        self._data_dir = os.path.join(os.path.dirname(config_path), "data")
        self._categories = set(
            self._config.get("matcher", "enabled_categories").split(",")
        )

    @property
    def enabled_categories(self) -> set:
        return self._categories

    def load_all_patterns(self) -> List[PatternDef]:
        """Load patterns from all data files, filtering by enabled categories."""
        patterns = []
        data_files = sorted(
            f
            for f in os.listdir(self._data_dir)
            if f.startswith("patterns_") and f.endswith(".txt")
        )

        for filename in data_files:
            filepath = os.path.join(self._data_dir, filename)
            file_patterns = self._parse_pattern_file(filepath)
            patterns.extend(file_patterns)

        return patterns

    def _parse_pattern_file(self, filepath: str) -> List[PatternDef]:
        """Parse a single pattern definition file."""
        patterns = []
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split("|")
                if len(parts) < 5:
                    continue
                name = parts[0]
                priority_str = parts[1]
                category = parts[2]
                regex = parts[3]
                test_inputs_str = parts[4]

                if category not in self._categories:
                    continue

                test_inputs = [
                    t.strip() for t in test_inputs_str.split(";") if t.strip()
                ]
                patterns.append(
                    PatternDef(
                        name=name.strip(),
                        priority=int(priority_str.strip()),
                        category=category.strip(),
                        regex=regex.strip(),
                        test_inputs=test_inputs,
                    )
                )

        return patterns
