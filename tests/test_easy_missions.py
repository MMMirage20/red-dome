"""Этап S4: миссии 1–3 легче для игрока.

Правки баланса по миссиям (balance.json → missions.N.overrides), асимметричная цель миссии 2,
предел армии ВЕКТОРа, ограниченные контратаки «Адаптивного» и отчёт sim_cli по миссиям.
"""

from __future__ import annotations

import argparse
import copy

import pytest

from reddome.bot.adaptive import BotAdaptive
from reddome.bot.bot_v0 import BotV0
from reddome.config.balance import Balance, balance_from_dict, merge_overrides
from reddome.sim.objectives import mission_winner
from reddome.sim.simulation import Simulation
from reddome.sim.state import add_building
from reddome.sim.types import MISSIONS
from tests.helpers import add_rovers, open_spot
from tools.sim_cli import GameRecord, SideRecord, game_row, play_report_game, render_markdown


def overrides(balance: Balance, mission: int) -> dict:
    return balance.raw["missions"][str(mission)].get("overrides", {})


@pytest.mark.parametrize("mission", MISSIONS)
def test_every_mission_gives_player_more_metal_and_later_waves(balance: Balance, mission: int) -> None:
    """Каждая миссия легче общих чисел: больше стартового металла и первая волна ВЕКТОРа позже."""
    m = balance.for_mission(mission)
    assert m.side("player").start.metal > balance.side("player").start.metal
    assert m.side("vector").bot.first_wave_sec > balance.side("vector").bot.first_wave_sec
    assert 0 < m.side("vector").bot.max_fighters


def test_overrides_change_only_their_mission(balance: Balance) -> None:
    one, two = balance.for_mission(1), balance.for_mission(2)
    assert one.side("vector").dome_hp == overrides(balance, 1)["buildings"]["dome"]["hp"]
    assert two.side("vector").dome_hp == balance.buildings["dome"].hp
    assert one.side("player").dome_hp == overrides(balance, 1)["player"]["dome_hp"]
    # Общий баланс не трогается.
    assert balance.side("player").start.metal == balance.raw["player"]["start_metal"]


def test_mission_balance_keeps_difficulty_and_is_idempotent(balance: Balance) -> None:
    hard = balance.with_difficulty("hard").for_mission(3)
    normal = balance.for_mission(3)
    assert hard.difficulty == "hard"
    assert hard.for_mission(3).side("vector").bot == hard.side("vector").bot
    level = balance.difficulties["hard"]
    assert hard.side("vector").bot.first_wave_sec == pytest.approx(normal.side("vector").bot.first_wave_sec * level.bot_timing)


def test_simulation_plays_with_mission_numbers(balance: Balance) -> None:
    sim = Simulation(balance, seed=1, mission=3)
    assert sim.balance.meteors == balance.for_mission(3).meteors
    assert sim.balance.meteors.interval_sec == overrides(balance, 3)["meteors"]["interval_sec"]
    assert sim.state.colonies["player"].resources["metal"] == overrides(balance, 3)["player"]["start_metal"]


def test_override_with_unknown_key_is_rejected(balance: Balance) -> None:
    raw = copy.deepcopy(balance.raw)
    raw["missions"]["2"]["overrides"] = {"bot": {"first_wave": 400}}
    with pytest.raises(ValueError, match="overrides.bot.first_wave"):
        balance_from_dict(raw)


@pytest.mark.parametrize("section", ["missions", "difficulty"])
def test_mission_cannot_override_missions_or_difficulty(balance: Balance, section: str) -> None:
    with pytest.raises(ValueError, match=section):
        merge_overrides(balance.raw, {section: {}})


def test_vector_needs_longer_hold_than_player_in_mission_two(balance: Balance) -> None:
    sim = Simulation(balance, seed=1, mission=2)
    mission, state = sim.mission, sim.state
    player_need, vector_need = mission.hold_sols_for("player"), mission.hold_sols_for("vector")
    assert player_need < vector_need
    state.ice_hold_sols["vector"] = player_need
    assert mission_winner(state, sim.balance) is None
    state.ice_hold_sols["vector"] = vector_need
    assert mission_winner(state, sim.balance) == ("vector", "ice_held")
    state.ice_hold_sols.update(player=player_need, vector=0)
    assert mission_winner(state, sim.balance) == ("player", "ice_held")


def test_bot_does_not_train_rovers_over_max_fighters(balance: Balance) -> None:
    sim = Simulation(balance, seed=1, mission=1)
    limit = sim.balance.side("vector").bot.max_fighters
    base = sim.state.map.bases["vector"]
    hangar = add_building(sim.state, sim.balance, "vector", "hangar", open_spot(sim.state, base))
    for _ in range(2):  # запас лимита армии: иначе бот пойдёт строить генератор, а не ровера
        add_building(sim.state, sim.balance, "vector", "oxy_gen", open_spot(sim.state, base))
    sim.state.colonies["vector"].resources["metal"] = 5000
    add_rovers(sim, "vector", limit)
    bot = BotV0("vector")
    bot.step = len(bot.build_order)
    bot._grow(sim)
    assert not hangar.queue
    sim.state.units = [u for u in sim.state.units if not (u.side == "vector" and u.type == "guard_rover")]
    add_rovers(sim, "vector", limit - 1)
    bot._grow(sim)
    assert [item.type for item in hangar.queue] == ["guard_rover"]


def test_army_limit_is_only_for_vector(balance: Balance) -> None:
    for mission in MISSIONS:
        m = balance.for_mission(mission)
        assert m.side("player").bot.max_fighters == 0 < m.side("vector").bot.max_fighters


def test_zero_max_fighters_means_no_limit(balance: Balance) -> None:
    raw = copy.deepcopy(balance.raw)
    raw["missions"]["1"]["overrides"]["bot"]["max_fighters"] = 0
    sim = Simulation(balance_from_dict(raw), seed=1, mission=1)
    add_rovers(sim, "vector", 12)
    assert not BotV0("vector")._army_full(sim)


def test_adaptive_counter_attack_is_not_all_in(balance: Balance) -> None:
    """Против «техно» уходит волна обычного размера (не меньше tech_attack_size), остальные стерегут базу."""
    sim = Simulation(balance, seed=1, mission=3)
    rovers = add_rovers(sim, "vector", 10)
    spec = sim.balance.side("vector").bot
    bot = BotAdaptive("vector")
    bot.style = "tech"
    bot._counter(sim)
    sent = max(spec.tech_attack_size, spec.wave_size(0))
    assert bot.waves and bot.waves[-1][1] == sent
    assert sum(r.task == "idle" for r in rovers) == len(rovers) - sent


def test_adaptive_raids_economy_player_not_too_often(balance: Balance) -> None:
    sim = Simulation(balance, seed=1, mission=3)
    bot = BotAdaptive("vector")
    bot.style = "economy"
    bot.next_wave_ms = 10_000_000
    bot._counter(sim)
    raid_ms = round(sim.balance.side("vector").bot.economy_raid_sec * 1000)
    assert bot.next_wave_ms == sim.state.elapsed_ms + raid_ms
    assert raid_ms > 20_000


@pytest.mark.parametrize("mission", [2, 3])
def test_sim_cli_report_runs_for_missions_two_and_three(balance: Balance, mission: int) -> None:
    game = play_report_game(balance, seed=1, sols=4, player="bot", mission=mission)
    assert game.end_sec > 0
    args = argparse.Namespace(games=1, seed=1, sols=4, player="bot", mission=mission)
    text = render_markdown([game], args, balance)
    assert f"--mission {mission}" in text and balance.mission(mission).title in text


@pytest.mark.parametrize("reason", ["ice_held", "great_dome"])
def test_report_row_knows_stage_three_outcomes(reason: str) -> None:
    sides = {"player": SideRecord(dome_max_hp=1), "vector": SideRecord(dome_max_hp=1)}
    row = game_row(GameRecord(seed=1, sides=sides, winner="vector", reason=reason, end_sec=600))
    assert "поражение" in row[1]



def test_tech_counter_stops_once_reactor_has_paid_off(balance: Balance) -> None:
    """Устав: против «техно» — быстрая атака, пока реактор не окупился; потом — обычные волны."""
    sim = Simulation(balance, seed=1, mission=3)
    add_rovers(sim, "vector", 10)
    spec = sim.balance.side("vector").bot
    bot = BotAdaptive("vector")
    bot.style = "tech"
    bot.memory.reactor_sec = 0.0
    sim.state.elapsed_ms = round(spec.tech_window_sec * 1000) + 1000
    bot._counter(sim)
    assert not bot.waves
    bot.memory.reactor_sec = sim.state.elapsed_ms / 1000 - 10
    bot._counter(sim)
    assert len(bot.waves) == 1
