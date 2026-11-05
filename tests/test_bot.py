"""Бот «ВЕКТОР» v0 (W3-11) и детерминизм партии с ботами."""

from __future__ import annotations

from dataclasses import asdict

from reddome.bot.bot_v0 import BotV0
from reddome.config.balance import Balance
from reddome.sim.simulation import Simulation
from reddome.sim.types import SIDES


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
