"""Загрузка balance.json (НФТ-07)."""

from __future__ import annotations

import json

import pytest

from reddome.config.balance import BALANCE_PATH, balance_from_dict


def test_balance_json_loads_with_all_buildings_and_units() -> None:
    raw = json.loads(BALANCE_PATH.read_text(encoding="utf-8"))
    balance = balance_from_dict(raw)
    assert balance.buildings["ice_drill"].needs == "ice"
    assert balance.units["guard_rover"].dps > 0


def test_unknown_building_key_is_reported() -> None:
    raw = json.loads(BALANCE_PATH.read_text(encoding="utf-8"))
    raw["buildings"]["iceDrill"] = raw["buildings"].pop("ice_drill")
    with pytest.raises(ValueError, match="buildings"):
        balance_from_dict(raw)
