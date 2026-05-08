# dashboard/api/services/config_mgr.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def read_config(config_path: str, schema: list[dict]) -> dict[str, Any]:
    """Read config from JSON file, filling in schema defaults for missing keys."""
    defaults = {f["key"]: f["default"] for f in schema}
    path = Path(config_path)
    if not path.exists():
        return defaults
    try:
        stored = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return defaults
    return {**defaults, **{k: v for k, v in stored.items() if k in defaults}}


def write_config(config_path: str, values: dict[str, Any]) -> None:
    """Write config values to JSON file, creating parent dirs as needed."""
    path = Path(config_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(values, indent=2))


def validate_config(values: dict[str, Any], schema: list[dict]) -> list[str]:
    """Return list of error strings for any invalid values. Empty = valid."""
    schema_by_key = {f["key"]: f for f in schema}
    errors: list[str] = []
    for key, val in values.items():
        if key not in schema_by_key:
            continue  # unknown keys are silently ignored
        field = schema_by_key[key]
        ftype = field["type"]
        if ftype == "int" and not isinstance(val, int):
            errors.append(f"{key}: expected int, got {type(val).__name__}")
            continue
        if ftype == "float" and not isinstance(val, (int, float)):
            errors.append(f"{key}: expected float, got {type(val).__name__}")
            continue
        if isinstance(val, (int, float)):
            if "min" in field and val < field["min"]:
                errors.append(f"{key}: {val} is below minimum {field['min']}")
            if "max" in field and val > field["max"]:
                errors.append(f"{key}: {val} is above maximum {field['max']}")
    return errors
