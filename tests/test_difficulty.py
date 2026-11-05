"""Уровни сложности (этап 2, S2-01): множители из balance.json и детерминизм партии."""

from __future__ import annotations

import json
import math
from dataclasses import asdict

import pytest

from reddome.bot.bot_v0 import BotV0
from reddome.config.balance import BALANCE_PATH, Balance, balance_from_dict, load_balance
from reddome.sim.simulation import Simulation
from reddome.sim.state import add_unit, find_free_tile_near
from reddome.sim.types import DIFFICULTIES, SIDES, Difficulty, Point
from reddome.sim.workers import deliver

#: Сколько гонять партию в тестах детерминизма: первая волна ВЕКТОРа успевает уйти на всех уровнях.
GAME_MS = 420_000


def half_up(value: float) -> int:
    return math.floor(value + 0.5)


def test_normal_is_the_base_numbers(balance: Balance) -> None:
    """«Обычный» — числа из разделов start, bot, buildings и player без изменений."""
    assert balance.difficulty == "normal"
    assert load_balance(difficulty="normal") == balance
    level = balance.difficulties["normal"]
    assert (level.bot_timing, level.bot_waves, level.bot_resources, level.player_dome_hp) == (1.0, 1.0, 1.0, 1.0)
    vector, player = balance.side("vector"), balance.side("player")
    assert vector.bot == balance.bot
    assert vector.start == balance.start
    assert vector.income_ratio == player.income_ratio == 1.0
    assert balance.max_hp("vector", "dome") == balance.buildings["dome"].hp
    assert balance.max_hp("player", "dome") == balance.player.dome_hp
    assert player.start.metal == balance.player.start_metal
    assert player.bot == balance.bot


@pytest.mark.parametrize("difficulty", ["easy", "hard"])
def test_multipliers_are_applied_once_at_load(balance: Balance, difficulty: Difficulty) -> None:
    hard = balance.with_difficulty(difficulty)
    level = balance.difficulties[difficulty]
    bot = hard.side("vector").bot
    assert bot.first_wave_sec == pytest.approx(balance.bot.first_wave_sec * level.bot_timing)
    assert bot.wave_interval_sec == pytest.approx(balance.bot.wave_interval_sec * level.bot_timing)
    assert bot.wave_size_ratio == level.bot_waves
    start = hard.side("vector").start
    for key in ("energy", "water", "oxygen", "metal"):
        assert getattr(start, key) == half_up(getattr(balance.start, key) * level.bot_resources)
    assert start.drones == balance.start.drones
    assert hard.side("vector").income_ratio == level.bot_resources
    assert hard.max_hp("player", "dome") == half_up(balance.player.dome_hp * level.player_dome_hp)
    # Остальное не трогается: купол ВЕКТОРа, другие здания, сторона игрока и общие разделы.
    assert hard.max_hp("vector", "dome") == balance.max_hp("vector", "dome")
    assert hard.side("player").bot == balance.bot
    assert hard.side("player").start == balance.side("player").start
    assert (hard.bot, hard.start, hard.buildings, hard.units) == (balance.bot, balance.start, balance.buildings, balance.units)


def test_levels_order_easy_normal_hard(balance: Balance) -> None:
    levels = [balance.with_difficulty(d) for d in DIFFICULTIES]
    first_waves = [b.side("vector").bot.first_wave_sec for b in levels]
    domes = [b.max_hp("player", "dome") for b in levels]
    metals = [b.side("vector").start.metal for b in levels]
    assert first_waves == sorted(first_waves, reverse=True)
    assert domes == sorted(domes, reverse=True)
    assert metals == sorted(metals)


def test_unknown_difficulty_is_reported() -> None:
    with pytest.raises(ValueError, match="сложность"):
        load_balance(difficulty="nightmare")


def test_missing_level_is_reported() -> None:
    raw = json.loads(BALANCE_PATH.read_text(encoding="utf-8"))
    del raw["difficulty"]["levels"]["hard"]
    with pytest.raises(ValueError, match="difficulty"):
        balance_from_dict(raw)


def test_simulation_takes_difficulty_next_to_seed(balance: Balance) -> None:
    sim = Simulation(balance, seed=1, difficulty="easy")
    easy = balance.with_difficulty("easy")
    assert sim.state.difficulty == "easy"
    assert sim.balance.difficulty == "easy"
    assert sim.state.colonies["vector"].resources["metal"] == easy.side("vector").start.metal
    dome = next(b for b in sim.state.buildings if b.side == "player" and b.type == "dome")
    assert dome.hp == easy.max_hp("player", "dome")
    assert Simulation(balance, seed=1).state.difficulty == balance.difficulty


def bot_game(balance: Balance, difficulty: Difficulty, seed: int = 4) -> Simulation:
    sim = Simulation(balance, seed, difficulty)
    for side in SIDES:
        sim.add_controller(BotV0(side))
    sim.update(GAME_MS)
    return sim


@pytest.mark.parametrize("difficulty", DIFFICULTIES)
def test_same_seed_and_difficulty_give_same_game(balance: Balance, difficulty: Difficulty) -> None:
    assert asdict(bot_game(balance, difficulty).state) == asdict(bot_game(balance, difficulty).state)


def test_difficulty_changes_the_game(balance: Balance) -> None:
    assert asdict(bot_game(balance, "easy").state) != asdict(bot_game(balance, "hard").state)


def test_bot_income_follows_difficulty(balance: Balance) -> None:
    for difficulty in DIFFICULTIES:
        sim = Simulation(balance, seed=1, difficulty=difficulty)
        state = sim.state
        dome = next(b for b in state.buildings if b.side == "vector" and b.type == "dome")
        spot = find_free_tile_near(state, Point(dome.x, dome.y))
        assert spot is not None
        drone = add_unit(state, sim.balance, "vector", "drone", spot)
        drone.carry = balance.workers.carry
        before = state.colonies["vector"].resources["metal"]
        deliver(state, sim.balance, drone, dome, [])
        expected = half_up(balance.workers.carry * sim.balance.side("vector").income_ratio)
        assert state.colonies["vector"].resources["metal"] - before == expected
        assert state.stats["vector"].metal_mined == expected
