"""
Structure-only validation for YandexGPT JSON.

We do not validate field values — only that the payload is a JSON object.
Raise ValueError when structure is invalid; pipeline will retry.
"""

from typing import Any, Dict


def validate_json_structure(data):
    # type: (Any) -> Dict[str, Any]
    if not isinstance(data, dict):
        raise ValueError("Extracted payload must be a JSON object")
    return data
