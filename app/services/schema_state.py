"""JSON skeleton / state helpers for block-wise GPT extraction."""

import copy
import json
import re
from typing import Any, Dict, Optional

from loguru import logger


UNKNOWN = "???"

# Lite often invents role labels / stubs instead of real values.
_PLACEHOLDER_EXACT = frozenset(
    {
        "заказчик",
        "подрядчик",
        "исполнитель",
        "объект",
        "договор",
        "договор подряда",
        "работы",
        "наименование",
        "адрес",
    }
)
_PLACEHOLDER_PATTERNS = (
    re.compile(r"^объект\s*№?\s*_+$", re.IGNORECASE | re.UNICODE),
    re.compile(r"^договор(\s+подряда)?$", re.IGNORECASE | re.UNICODE),
)


class OverwriteError(ValueError):
    def __init__(self, key, old_value, new_value):
        self.key = key
        self.old_value = old_value
        self.new_value = new_value
        super(OverwriteError, self).__init__(
            "Overwrite forbidden for key '{}': {!r} -> {!r}".format(
                key, old_value, new_value
            )
        )


def _find_json_object_span(text):
    # type: (str) -> Optional[str]
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escape = False
    for index in range(start, len(text)):
        ch = text[index]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def _to_unknown_tree(value):
    # type: (Any) -> Any
    if isinstance(value, dict):
        return {key: _to_unknown_tree(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_to_unknown_tree(item) for item in value]
    return UNKNOWN


def extract_skeleton(prompt):
    # type: (str) -> Dict[str, Any]
    """Pull JSON object from prompt braces and replace values with ???."""
    raw = _find_json_object_span(prompt)
    if not raw:
        raise ValueError("Prompt must contain a JSON object skeleton in curly braces")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("Prompt JSON skeleton is invalid: {}".format(exc)) from exc
    if not isinstance(data, dict):
        raise ValueError("Prompt JSON skeleton must be an object")
    return _to_unknown_tree(data)


def fresh_state(skeleton):
    # type: (Dict[str, Any]) -> Dict[str, Any]
    return copy.deepcopy(skeleton)


def _is_unknown(value):
    # type: (Any) -> bool
    if value is None:
        return True
    if value == UNKNOWN:
        return True
    if isinstance(value, str) and value.strip() in ("", UNKNOWN):
        return True
    return False


def _is_placeholder(value):
    # type: (Any) -> bool
    """True for stubs Lite invents: Заказчик, Объект №__, ??? ____ 2026, etc."""
    if _is_unknown(value):
        return True
    if not isinstance(value, str):
        return False
    text = value.strip()
    if not text:
        return True
    if "???" in text or "??." in text or "___" in text:
        return True
    norm = " ".join(text.lower().split())
    if norm in _PLACEHOLDER_EXACT:
        return True
    for pattern in _PLACEHOLDER_PATTERNS:
        if pattern.match(norm):
            return True
    return False


def _is_usable_value(value):
    # type: (Any) -> bool
    return not _is_placeholder(value)


def _values_equal(left, right):
    # type: (Any, Any) -> bool
    if _is_unknown(left) and _is_unknown(right):
        return True
    return left == right


def _tree_is_complete(value):
    # type: (Any) -> bool
    if isinstance(value, dict):
        if not value:
            return False
        return all(_tree_is_complete(item) for item in value.values())
    if isinstance(value, list):
        if not value:
            return False
        return all(_tree_is_complete(item) for item in value)
    return _is_usable_value(value)


def is_state_complete(state):
    # type: (Dict[str, Any]) -> bool
    """True when every schema field has a real (non-??? / non-stub) value."""
    if not isinstance(state, dict) or not state:
        return False
    return _tree_is_complete(state)


def apply_gpt_state(state, response, allow_overwrite=True):
    # type: (Dict[str, Any], Dict[str, Any], bool) -> Dict[str, Any]
    """
    Merge GPT response into state.
    - Fill ??? slots with usable (non-placeholder) values.
    - Reject stubs like «Заказчик», «Объект», «Договор», «??? …».
    - If allow_overwrite: careful overwrite of already set fields (logged).
    - If not allow_overwrite: keep existing value (skip conflict, do not fail).
    """
    if not isinstance(response, dict):
        raise ValueError("GPT response must be a JSON object")

    for key in state.keys():
        if key not in response:
            continue
        new_val = response[key]
        old_val = state[key]

        if not _is_usable_value(new_val):
            if not _is_unknown(new_val):
                logger.info(
                    "Reject placeholder key={!r}: {!r}",
                    key,
                    new_val,
                )
            continue

        if _is_unknown(old_val):
            state[key] = new_val
            continue

        if _values_equal(old_val, new_val):
            continue

        if not allow_overwrite:
            logger.info(
                "Skip overwrite key={!r}: keep {!r}, ignore {!r}",
                key,
                old_val,
                new_val,
            )
            continue

        logger.info(
            "Careful overwrite key={!r}: {!r} -> {!r}",
            key,
            old_val,
            new_val,
        )
        state[key] = new_val

    return state


def state_to_json(state, compact=True):
    # type: (Dict[str, Any], bool) -> str
    """Serialize state for GPT requests (compact by default to save budget)."""
    if compact:
        return json.dumps(state, ensure_ascii=False, separators=(",", ":"))
    return json.dumps(state, ensure_ascii=False, indent=2)
