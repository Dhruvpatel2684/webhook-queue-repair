"""NFA-based pattern evaluator with backtrack-limited matching."""

import configparser
from typing import Dict, List, Optional, Set, Tuple

from .compiler import CompiledPattern, NFAState


class PatternEvaluator:
    """Evaluates compiled NFA patterns against test input strings."""

    def __init__(self, config_path: str):
        self._config = configparser.ConfigParser()
        self._config.read(config_path)
        self._max_backtrack = self._config.getint("matcher", "max_backtrack")
        self._batch_size = self._config.getint("matcher.limits", "batch_size")

    def evaluate_all(
        self, patterns: List[CompiledPattern]
    ) -> List[Dict]:
        """Evaluate all compiled patterns against their test inputs."""
        results = {p.name: {"match_count": 0} for p in patterns}

        pattern_map = {p.name: p for p in patterns}

        for batch_start in range(0, len(patterns), self._batch_size):
            batch = patterns[batch_start : batch_start + self._batch_size]
            for pattern in batch:
                count = self._count_matches(pattern)
                results[pattern.name]["match_count"] += count

        for batch_start in range(0, len(patterns), self._batch_size):
            batch = patterns[batch_start : batch_start + self._batch_size]
            for pattern in batch:
                count = self._count_matches(pattern)
                results[pattern.name]["match_count"] += count

        output = []
        for pattern in patterns:
            count = results[pattern.name]["match_count"]
            for test_input in pattern.test_inputs:
                matched, span = self._simulate_nfa(pattern, test_input)
                output.append(
                    {
                        "name": pattern.name,
                        "category": pattern.category,
                        "priority": pattern.priority,
                        "input_text": test_input,
                        "matched": matched,
                        "match_span": span,
                        "match_count": count,
                    }
                )

        return output

    def _count_matches(self, pattern: CompiledPattern) -> int:
        """Count how many test inputs match for a pattern."""
        count = 0
        for test_input in pattern.test_inputs:
            matched, _ = self._simulate_nfa(pattern, test_input)
            if matched:
                count += 1
        return count

    def _simulate_nfa(
        self, pattern: CompiledPattern, text: str
    ) -> Tuple[bool, Optional[List[int]]]:
        """Simulate NFA execution on input text with backtrack limiting."""
        states = pattern.states
        start = pattern.start_state

        for start_pos in range(len(text)):
            result = self._try_match_at(states, start, text, start_pos)
            if result is not None:
                return (True, [start_pos, result])

        return (False, None)

    def _try_match_at(
        self,
        states: List[NFAState],
        start: int,
        text: str,
        start_pos: int,
    ) -> Optional[int]:
        """Try to find a match starting at the given position.

        Uses step counting where each state transition counts toward the
        backtrack limit. This bounds computation on complex patterns.
        """
        step_count = 0
        best_end = None

        current_states = self._epsilon_closure_counted(states, {start})
        step_count += len(current_states)

        for sid in current_states:
            if states[sid].is_accept:
                best_end = start_pos

        pos = start_pos
        while pos < len(text) and step_count < self._max_backtrack:
            ch = text[pos]
            next_states: Set[int] = set()

            for sid in current_states:
                state = states[sid]
                for label, targets in state.transitions.items():
                    if label == "epsilon":
                        continue
                    if self._label_matches(label, ch):
                        for t in targets:
                            next_states.add(t)
                            step_count += 1

            if not next_states:
                break

            current_states = self._epsilon_closure_counted(states, next_states)
            step_count += len(current_states)
            pos += 1

            for sid in current_states:
                if states[sid].is_accept:
                    if best_end is None or pos > best_end:
                        best_end = pos

        return best_end

    def _epsilon_closure_counted(
        self, states: List[NFAState], state_ids: Set[int]
    ) -> Set[int]:
        """Compute epsilon closure of a set of states."""
        closure = set(state_ids)
        stack = list(state_ids)

        while stack:
            sid = stack.pop()
            if sid >= len(states):
                continue
            state = states[sid]
            if "epsilon" in state.transitions:
                for target in state.transitions["epsilon"]:
                    if target not in closure:
                        closure.add(target)
                        stack.append(target)

        return closure

    def _label_matches(self, label: str, ch: str) -> bool:
        """Check if a transition label matches the given character."""
        if label == "ANY":
            return ch != "\n"
        elif label == "DIGIT":
            return ch.isdigit()
        elif label == "NON_DIGIT":
            return not ch.isdigit()
        elif label == "WORD":
            return ch.isalnum() or ch == "_"
        elif label == "NON_WORD":
            return not (ch.isalnum() or ch == "_")
        elif label == "SPACE":
            return ch.isspace()
        elif label == "NON_SPACE":
            return not ch.isspace()
        elif label.startswith("CLASS:"):
            chars = label[6:]
            return ch in chars
        elif label.startswith("NCLASS:"):
            chars = label[7:]
            return ch not in chars
        else:
            return label == ch
