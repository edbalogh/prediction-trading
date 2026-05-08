# tests/dashboard/test_config_mgr.py
import json
import pytest
from pathlib import Path

from dashboard.api.services.config_mgr import read_config, write_config, validate_config

SCHEMA = [
    {"key": "sweep_min_spread_cents", "type": "int",   "default": 3,    "min": 1, "max": 50},
    {"key": "max_notional_usd",       "type": "float", "default": 1.00, "min": 0.01},
    {"key": "bail_seconds",           "type": "int",   "default": 45,   "min": 1},
]


def test_read_config_returns_defaults_when_no_file(tmp_path):
    path = tmp_path / "nonexistent.json"
    result = read_config(str(path), SCHEMA)
    assert result == {"sweep_min_spread_cents": 3, "max_notional_usd": 1.00, "bail_seconds": 45}


def test_read_config_returns_stored_values(tmp_path):
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({"sweep_min_spread_cents": 5, "max_notional_usd": 2.0, "bail_seconds": 60}))
    result = read_config(str(cfg_file), SCHEMA)
    assert result["sweep_min_spread_cents"] == 5
    assert result["max_notional_usd"] == 2.0
    assert result["bail_seconds"] == 60


def test_read_config_merges_defaults_for_missing_keys(tmp_path):
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({"sweep_min_spread_cents": 7}))
    result = read_config(str(cfg_file), SCHEMA)
    assert result["sweep_min_spread_cents"] == 7
    assert result["max_notional_usd"] == 1.00  # default filled in
    assert result["bail_seconds"] == 45  # default filled in


def test_write_config_creates_file(tmp_path):
    cfg_file = tmp_path / "config.json"
    write_config(str(cfg_file), {"sweep_min_spread_cents": 8, "max_notional_usd": 3.0, "bail_seconds": 30})
    assert cfg_file.exists()
    data = json.loads(cfg_file.read_text())
    assert data["sweep_min_spread_cents"] == 8


def test_validate_config_passes_correct_values():
    errors = validate_config({"sweep_min_spread_cents": 5, "max_notional_usd": 2.5}, SCHEMA)
    assert errors == []


def test_validate_config_rejects_wrong_type():
    errors = validate_config({"sweep_min_spread_cents": "five"}, SCHEMA)
    assert any("sweep_min_spread_cents" in e for e in errors)


def test_validate_config_rejects_below_minimum():
    errors = validate_config({"sweep_min_spread_cents": 0}, SCHEMA)
    assert any("minimum" in e for e in errors)


def test_validate_config_rejects_above_maximum():
    errors = validate_config({"sweep_min_spread_cents": 100}, SCHEMA)
    assert any("maximum" in e for e in errors)


def test_validate_config_ignores_unknown_keys():
    errors = validate_config({"unknown_param": 42}, SCHEMA)
    assert errors == []
