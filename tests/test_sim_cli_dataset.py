"""Датасет «бот против бота» (W3-13, ФТ-17): CSV, разброс чисел ботов и повторяемость."""

from __future__ import annotations

import csv
import random
from pathlib import Path

from reddome.config.balance import load_balance
from tools.sim_cli import jittered_bot, main


def read(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as file:
        return list(csv.DictReader(file))


def test_csv_has_rows_per_side_and_sol(tmp_path: Path) -> None:
    out = tmp_path / "games.csv"
    main(["--games", "2", "--seed", "5", "--sols", "4", "--out", str(out)])
    rows = read(out)
    assert len(rows) == 2 * 4 * 2
    assert {r["side"] for r in rows} == {"player", "vector"}
    for column in ("green_sols", "bot_target_drones", "bot_first_wave_sec", "winner", "n_solar", "metal"):
        assert column in rows[0]


def test_dataset_is_repeatable(tmp_path: Path) -> None:
    a, b = tmp_path / "a.csv", tmp_path / "b.csv"
    main(["--games", "2", "--seed", "9", "--sols", "6", "--out", str(a)])
    main(["--games", "2", "--seed", "9", "--sols", "6", "--out", str(b)])
    assert a.read_text(encoding="utf-8") == b.read_text(encoding="utf-8")


def test_bot_numbers_vary_slightly() -> None:
    spec = load_balance().bot
    seen = {jittered_bot(spec, random.Random(i), 0.15) for i in range(30)}
    assert len(seen) > 5
    for bot in seen:
        assert abs(bot.target_drones - spec.target_drones) <= 1
        assert spec.first_wave_sec * 0.85 - 0.1 <= bot.first_wave_sec <= spec.first_wave_sec * 1.15 + 0.1
    assert jittered_bot(spec, random.Random(1), 0) == spec
