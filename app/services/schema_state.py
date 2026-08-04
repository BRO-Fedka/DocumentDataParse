"""JSON skeleton / state helpers for block-wise GPT extraction."""

import copy
import json
from typing import Any, Dict, Optional

from loguru import logger


UNKNOWN = "???"


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


def _values_equal(left, right):
    # type: (Any, Any) -> bool
    if _is_unknown(left) and _is_unknown(right):
        return True
    return left == right


def apply_gpt_state(state, response, allow_overwrite=True):
    # type: (Dict[str, Any], Dict[str, Any], bool) -> Dict[str, Any]
    """
    Merge GPT response into state.
    - Fill ??? slots with new non-unknown values.
    - If allow_overwrite: careful overwrite of already set fields (logged).
    - If not allow_overwrite: different value raises OverwriteError.
    """
    if not isinstance(response, dict):
        raise ValueError("GPT response must be a JSON object")

    for key in state.keys():
        if key not in response:
            continue
        new_val = response[key]
        old_val = state[key]

        if _is_unknown(old_val):
            if not _is_unknown(new_val):
                state[key] = new_val
            continue

        if _is_unknown(new_val) or _values_equal(old_val, new_val):
            continue

        if not allow_overwrite:
            raise OverwriteError(key, old_val, new_val)

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
