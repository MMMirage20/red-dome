"""Бот «ВЕКТОР» v0 (W3-11) и детерминизм партии с ботами."""

from __future__ import annotations

from dataclasses import asdict, replace

from reddome.bot.bot_v0 import BotV0
from reddome.config.balance import Balance
from reddome.sim.simulation import Simulation
from reddome.sim.types import SIDES
from tests.helpers import add_rovers


def test_bot_builds_hangar_and_rover_within_five_minutes(balance: Balance) -> None:
    sim = Simulation(balance, seed=1)
    sim.add_controller(BotV0("vector"))

    events = []
    for _ in range(300):
        sim.update(1000)
        events.extend(sim.drain_events())

    assert any(e.kind == "construction_complete" and e.side == "vector" and e.subject == "hangar" for e in events)
    assert any(e.kind == "unit_trained" and e.side == "vector" and e.subject == "guard_rover" for e in events)
    # Бот не получает бесплатных ресурсов: весь его металл — стартовый плюс добытый.
    stats = sim.state.stats["vector"]
    assert stats.metal_mined > 0


def test_bot_keeps_drones_gathering(balance: Balance) -> None:
    sim = Simulation(balance, seed=1)
    sim.add_controller(BotV0("vector"))
    sim.update(60_000)

    drones = [u for u in sim.state.units if u.side == "vector" and u.type == "drone"]
    assert drones and all(d.task != "idle" for d in drones)


def run_bot_game(balance: Balance, frame_ms: int, total_ms: int) -> Simulation:
    sim = Simulation(balance, seed=7)
    for side in SIDES:
        sim.add_controller(BotV0(side))
    for _ in range(total_ms // frame_ms):
        sim.update(frame_ms)
    return sim


def test_bot_game_is_deterministic_at_any_frame_rate(balance: Balance) -> None:
    """Бот действует внутри тика, поэтому разный шаг кадра даёт одну и ту же партию."""
    fast = run_bot_game(balance, frame_ms=16, total_ms=240_000)
    slow = run_bot_game(balance, frame_ms=100, total_ms=240_000)
    assert asdict(fast.state) == asdict(slow.state)


def test_waves_grow_every_other_wave(balance: Balance) -> None:
    sizes = [balance.bot.wave_size(n) for n in range(6)]
    assert balance.bot.wave_growth_every == 2
    assert sizes == [2, 2, 3, 3, 4, 4]


def test_wave_size_ratio_rounds_and_never_drops_to_zero(balance: Balance) -> None:
    bot = replace(balance.bot, wave_size_start=2, wave_growth=1, wave_growth_every=2)
    assert [replace(bot, wave_size_ratio=0.75).wave_size(n) for n in range(6)] == [2, 2, 2, 2, 3, 3]
    assert [replace(bot, wave_size_ratio=1.25).wave_size(n) for n in range(6)] == [3, 3, 4, 4, 5, 5]
    assert replace(bot, wave_size_start=1, wave_size_ratio=0.1).wave_size(0) == 1


def test_bot_sends_exactly_wave_size_and_keeps_the_rest_home(balance: Balance) -> None:
    sim = Simulation(balance, seed=1)
    rovers = add_rovers(sim, "vector", 5)
    bot = BotV0("vector")
    sim.add_controller(bot)
    # Числа партии — с правками миссии 1 (balance.json → missions.1.overrides).
    first_wave_ms = int(sim.balance.side("vector").bot.first_wave_sec * 1000)
    sim.state.elapsed_ms = first_wave_ms - 1000
    sim.update(2000)
    size = sim.balance.side("vector").bot.wave_size(0)
    assert len(bot.waves) == 1 and bot.waves[0][1] == size
    home = [r for r in rovers if r.task == "idle"]
    assert len(home) == len(rovers) - size
