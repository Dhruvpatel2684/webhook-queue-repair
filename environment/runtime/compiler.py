"""Regex compiler that builds NFA representations using Thompson's construction."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .loader import PatternDef


@dataclass
class NFAState:
    state_id: int
    transitions: Dict[str, List[int]] = field(default_factory=dict)
    is_accept: bool = False


@dataclass
class CompiledPattern:
    name: str
    category: str
    priority: int
    states: List[NFAState]
    start_state: int
    test_inputs: List[str]


class _NFAFragment:
    """Intermediate NFA fragment used during construction."""

    def __init__(self, start: int, accept: int):
        self.start = start
        self.accept = accept


class RegexCompiler:
    """Compiles regex strings into NFA state machines."""

    # backtrack limit from matcher.limits section

    def __init__(self):
        self._states: List[NFAState] = []
        self._next_id: int = 0

    def compile(self, pattern_def: PatternDef) -> CompiledPattern:
        """Compile a pattern definition into an NFA."""
        self._states = []
        self._next_id = 0

        fragment = self._parse_regex(pattern_def.regex, 0)
        if fragment is None:
            fragment = self._create_empty_match()

        self._states[fragment.accept].is_accept = True

        return CompiledPattern(
            name=pattern_def.name,
            category=pattern_def.category,
            priority=pattern_def.priority,
            states=list(self._states),
            start_state=fragment.start,
            test_inputs=list(pattern_def.test_inputs),
        )

    def _new_state(self) -> NFAState:
        """Create a new NFA state."""
        state = NFAState(state_id=self._next_id)
        self._next_id += 1
        self._states.append(state)
        return state

    def _add_transition(self, from_id: int, label: str, to_id: int):
        """Add a transition between states."""
        state = self._states[from_id]
        if label not in state.transitions:
            state.transitions[label] = []
        state.transitions[label].append(to_id)

    def _create_empty_match(self) -> _NFAFragment:
        """Create a fragment that matches empty string."""
        s = self._new_state()
        a = self._new_state()
        self._add_transition(s.state_id, "epsilon", a.state_id)
        return _NFAFragment(s.state_id, a.state_id)

    def _parse_regex(self, regex: str, pos: int) -> Optional[_NFAFragment]:
        """Parse a full regex expression handling alternation at the top level."""
        alternatives = []
        current = self._parse_sequence(regex, pos)
        if current is None:
            return None

        alternatives.append(current[0])
        pos = current[1]

        while pos < len(regex) and regex[pos] == "|":
            pos += 1
            current = self._parse_sequence(regex, pos)
            if current is None:
                break
            alternatives.append(current[0])
            pos = current[1]

        if len(alternatives) == 1:
            return alternatives[0]

        return self._build_alternation(alternatives)

    def _build_alternation(self, fragments: List[_NFAFragment]) -> _NFAFragment:
        """Build alternation NFA from multiple fragments."""
        start = self._new_state()
        accept = self._new_state()

        for frag in fragments:
            self._add_transition(start.state_id, "epsilon", frag.start)
            self._add_transition(frag.accept, "epsilon", accept.state_id)

        return _NFAFragment(start.state_id, accept.state_id)

    def _parse_sequence(
        self, regex: str, pos: int
    ) -> Optional[Tuple[_NFAFragment, int]]:
        """Parse a sequence of concatenated atoms."""
        fragments = []

        while pos < len(regex) and regex[pos] not in ("|", ")"):
            result = self._parse_quantified(regex, pos)
            if result is None:
                break
            frag, pos = result
            fragments.append(frag)

        if not fragments:
            empty = self._create_empty_match()
            return (empty, pos)

        combined = fragments[0]
        for i in range(1, len(fragments)):
            combined = self._concatenate(combined, fragments[i])

        return (combined, pos)

    def _concatenate(self, a: _NFAFragment, b: _NFAFragment) -> _NFAFragment:
        """Concatenate two NFA fragments."""
        self._add_transition(a.accept, "epsilon", b.start)
        return _NFAFragment(a.start, b.accept)

    def _parse_quantified(
        self, regex: str, pos: int
    ) -> Optional[Tuple[_NFAFragment, int]]:
        """Parse an atom with optional quantifier."""
        result = self._parse_atom(regex, pos)
        if result is None:
            return None

        frag, pos = result

        if pos < len(regex) and regex[pos] in ("*", "+", "?"):
            quantifier = regex[pos]
            pos += 1
            frag = self._apply_quantifier(frag, quantifier)

        return (frag, pos)

    def _apply_quantifier(self, frag: _NFAFragment, quant: str) -> _NFAFragment:
        """Apply a quantifier to an NFA fragment."""
        start = self._new_state()
        accept = self._new_state()

        if quant == "*":
            self._add_transition(start.state_id, "epsilon", frag.start)
            self._add_transition(start.state_id, "epsilon", accept.state_id)
            self._add_transition(frag.accept, "epsilon", frag.start)
            self._add_transition(frag.accept, "epsilon", accept.state_id)
        elif quant == "+":
            self._add_transition(start.state_id, "epsilon", frag.start)
            self._add_transition(frag.accept, "epsilon", frag.start)
            self._add_transition(frag.accept, "epsilon", accept.state_id)
        elif quant == "?":
            self._add_transition(start.state_id, "epsilon", frag.start)
            self._add_transition(start.state_id, "epsilon", accept.state_id)
            self._add_transition(frag.accept, "epsilon", accept.state_id)

        return _NFAFragment(start.state_id, accept.state_id)

    def _parse_atom(self, regex: str, pos: int) -> Optional[Tuple[_NFAFragment, int]]:
        """Parse a single atom: literal, escape, dot, char class, or group."""
        if pos >= len(regex):
            return None

        ch = regex[pos]

        if ch == "(":
            return self._parse_group(regex, pos)
        elif ch == "[":
            return self._parse_char_class(regex, pos)
        elif ch == ".":
            return self._build_dot(pos)
        elif ch == "\\":
            return self._parse_escape(regex, pos)
        elif ch in ("|", ")", "*", "+", "?"):
            return None
        else:
            return self._build_literal(ch, pos)

    def _build_literal(self, ch: str, pos: int) -> Tuple[_NFAFragment, int]:
        """Build NFA for a single literal character."""
        start = self._new_state()
        accept = self._new_state()
        self._add_transition(start.state_id, ch, accept.state_id)
        return (_NFAFragment(start.state_id, accept.state_id), pos + 1)

    def _build_dot(self, pos: int) -> Tuple[_NFAFragment, int]:
        """Build NFA for dot (match any character)."""
        start = self._new_state()
        accept = self._new_state()
        self._add_transition(start.state_id, "ANY", accept.state_id)
        return (_NFAFragment(start.state_id, accept.state_id), pos + 1)

    def _parse_escape(self, regex: str, pos: int) -> Optional[Tuple[_NFAFragment, int]]:
        """Parse an escape sequence."""
        if pos + 1 >= len(regex):
            return self._build_literal("\\", pos)

        next_ch = regex[pos + 1]
        start = self._new_state()
        accept = self._new_state()

        if next_ch == "d":
            self._add_transition(start.state_id, "DIGIT", accept.state_id)
        elif next_ch == "w":
            self._add_transition(start.state_id, "WORD", accept.state_id)
        elif next_ch == "s":
            self._add_transition(start.state_id, "SPACE", accept.state_id)
        elif next_ch == "D":
            self._add_transition(start.state_id, "NON_DIGIT", accept.state_id)
        elif next_ch == "W":
            self._add_transition(start.state_id, "NON_WORD", accept.state_id)
        elif next_ch == "S":
            self._add_transition(start.state_id, "NON_SPACE", accept.state_id)
        else:
            self._add_transition(start.state_id, next_ch, accept.state_id)

        return (_NFAFragment(start.state_id, accept.state_id), pos + 2)

    def _parse_group(
        self, regex: str, pos: int
    ) -> Optional[Tuple[_NFAFragment, int]]:
        """Parse a parenthesized group."""
        pos += 1
        frag = self._parse_regex(regex, pos)
        if frag is None:
            frag = self._create_empty_match()
            inner_pos = pos
        else:
            inner_pos = self._find_group_end(regex, pos)

        if inner_pos < len(regex) and regex[inner_pos] == ")":
            inner_pos += 1

        return (frag, inner_pos)

    def _find_group_end(self, regex: str, pos: int) -> int:
        """Find the closing parenthesis position."""
        depth = 1
        while pos < len(regex) and depth > 0:
            if regex[pos] == "(":
                depth += 1
            elif regex[pos] == ")":
                depth -= 1
            if depth > 0:
                pos += 1
        return pos

    def _parse_char_class(
        self, regex: str, pos: int
    ) -> Optional[Tuple[_NFAFragment, int]]:
        """Parse a character class [...]."""
        pos += 1
        negated = False
        if pos < len(regex) and regex[pos] == "^":
            negated = True
            pos += 1

        chars = set()
        while pos < len(regex) and regex[pos] != "]":
            if (
                pos + 2 < len(regex)
                and regex[pos + 1] == "-"
                and regex[pos + 2] != "]"
            ):
                start_c = regex[pos]
                end_c = regex[pos + 2]
                for code in range(ord(start_c), ord(end_c) + 1):
                    chars.add(chr(code))
                pos += 3
            elif regex[pos] == "\\" and pos + 1 < len(regex):
                chars.add(regex[pos + 1])
                pos += 2
            else:
                chars.add(regex[pos])
                pos += 1

        if pos < len(regex) and regex[pos] == "]":
            pos += 1

        start = self._new_state()
        accept = self._new_state()

        label = ("NCLASS:" if negated else "CLASS:") + "".join(sorted(chars))
        self._add_transition(start.state_id, label, accept.state_id)

        return (_NFAFragment(start.state_id, accept.state_id), pos)
