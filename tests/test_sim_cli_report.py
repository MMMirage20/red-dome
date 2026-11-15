"""Отчёт баланса tools/sim_cli --report: замеры партии и Markdown."""

from __future__ import annotations

import argparse
import math

from reddome.config.balance import Balance
from tools.sim_cli import play_report_game, render_markdown

#: Запас после первой волны: бот ждёт, пока соберёт нужное число роверов.
AFTER_FIRST_WAVE_SEC = 90


def short_sols(balance: Balance) -> int:
    """Солов ровно столько, чтобы ВЕКТОР успел отправить первую волну."""
    first_wave_sec = balance.for_mission(1).side("vector").bot.first_wave_sec
    return math.ceil((first_wave_sec + AFTER_FIRST_WAVE_SEC) / balance.sol_seconds)


def test_report_records_first_wave_and_checkpoint(balance: Balance) -> None:
    game = play_report_game(balance, seed=1, sols=short_sols(balance))
    vector = game.sides["vector"]
    assert vector.waves, "ВЕКТОР должен успеть отправить первую волну"
    first_sec, first_size = vector.waves[0]
    bot = balance.for_mission(1).side("vector").bot
    assert first_sec >= bot.first_wave_sec
    assert first_size == bot.wave_size(0)
    player = game.sides["player"]
    assert player.rovers_at_enemy_first_wave is not None
    assert player.metal_mined_at_checkpoint > 0
    assert 0 <= player.min_dome_hp <= player.dome_max_hp


def test_report_is_deterministic(balance: Balance) -> None:
    sols = short_sols(balance)
    assert play_report_game(balance, 3, sols) == play_report_game(balance, 3, sols)


def test_markdown_has_summary_and_game_rows(balance: Balance) -> None:
    sols = short_sols(balance)
    games = [play_report_game(balance, seed, sols) for seed in (1, 2)]
    args = argparse.Namespace(games=2, seed=1, sols=sols, player="bot")
    text = render_markdown(games, args, balance)
    assert "### Сводка" in text and "### Партии" in text
    assert "Своя волна 1: роверов" in text
    assert text.count("\n| 1 |") == 1 and text.count("\n| 2 |") == 1


def test_economy_player_builds_no_army(balance: Balance) -> None:
    game = play_report_game(balance, seed=2, sols=short_sols(balance), player="economy")
    player = game.sides["player"]
    assert player.hangar_sec is None and player.first_rover_sec is None and not player.waves
    assert player.metal_mined_at_checkpoint > 0
    assert player.rovers_at_enemy_first_wave == 0
    vector = game.sides["vector"]
    assert vector.first_shot_sec is not None and vector.first_shot_sec >= vector.waves[0][0]
