"""Этап 3: миссии, турель, реактор, ракетный ровер, ледяные поля, Большой купол, буря, метеориты, вспышки."""

from __future__ import annotations

import pytest

from reddome.config.balance import Balance
from reddome.sim.economy import apply_sol
from reddome.sim.hazards import meteor_impact_ms
from reddome.sim.objectives import field_owner, fields_held
from reddome.sim.simulation import TICK_MS, Simulation
from reddome.sim.state import add_building, add_unit, find_free_tile_near
from reddome.sim.types import Point
from tests.helpers import open_spot, run_until


def complete(sim: Simulation, side: str, type_: str, at: Point):
    return add_building(sim.state, sim.balance, side, type_, at)  # type: ignore[arg-type]


def test_missions_are_loaded_from_balance(balance: Balance) -> None:
    assert sorted(balance.missions) == [1, 2, 3]
    assert balance.mission(1).goal == "destroy_dome" and balance.mission(1).bot == "novice"
    assert balance.mission(2).goal == "hold_ice" and balance.mission(2).hold_fields == 2
    assert balance.mission(3).goal == "great_dome" and "great_dome" in balance.mission(3).buildings
    with pytest.raises(ValueError):
        balance.mission(4)


def test_mission_one_keeps_stage_two_content(balance: Balance) -> None:
    mission = balance.mission(1)
    assert set(mission.buildings) == {"solar", "ice_drill", "oxy_gen", "regolith", "hangar"}
    assert set(mission.units) == {"drone", "guard_rover"}
    assert mission.events == ("dust_devil",)


def test_turret_is_not_available_in_mission_one(balance: Balance) -> None:
    sim = Simulation(balance, seed=1)
    spot = open_spot(sim.state, sim.state.map.bases["player"])
    result = sim.build("player", "turret", spot.x, spot.y)
    assert not result.ok and "недоступно" in result.reason


def test_mission_two_ore_is_poorer(balance: Balance) -> None:
    sim = Simulation(balance, seed=1, mission=2)
    assert {d.amount for d in sim.state.deposits} == {balance.mission(2).ore_amount}


def test_rocket_rover_needs_reactor(balance: Balance) -> None:
    sim = Simulation(balance, seed=1, mission=2)
    state = sim.state
    state.colonies["player"].resources["metal"] = 1000
    base = state.map.bases["player"]
    complete(sim, "player", "oxy_gen", open_spot(state, base))
    complete(sim, "player", "hangar", open_spot(state, base))
    result = sim.train("player", "rocket_rover")
    assert not result.ok and result.reason == "Нужен реактор"
    complete(sim, "player", "reactor", open_spot(state, base))
    assert sim.train("player", "rocket_rover").ok


def test_turret_shoots_enemy_in_range_and_not_without_power(balance: Balance) -> None:
    sim = Simulation(balance, seed=1, mission=2)
    state = sim.state
    spot = open_spot(state, Point(24, 16))
    turret = complete(sim, "player", "turret", spot)
    enemy = add_unit(state, sim.balance, "vector", "guard_rover", Point(spot.x + 3, spot.y))
    enemy.task = "moving"  # стоит, но сам не стреляет в ответ
    hp = enemy.hp
    for _ in range(10):
        sim.update(TICK_MS)
    assert enemy.hp < hp
    assert turret.target_id == enemy.id
    turret.powered = False
    hp = enemy.hp
    for _ in range(10):
        sim.update(TICK_MS)
    assert enemy.hp == pytest.approx(hp)


def test_rocket_rover_hits_buildings_harder(balance: Balance) -> None:
    sim = Simulation(balance, seed=1, mission=2)
    state = sim.state
    spot = open_spot(state, Point(24, 16))
    target = complete(sim, "vector", "solar", spot)
    rocket = add_unit(state, sim.balance, "player", "rocket_rover", Point(spot.x - 3, spot.y))
    sim.attack("player", [rocket.id], target.id)
    start = target.hp
    for _ in range(10):  # 1 с
        sim.update(TICK_MS)
    spec = sim.balance.units["rocket_rover"]
    assert start - target.hp == pytest.approx(spec.dps * spec.building_damage, rel=0.05)


def test_three_ice_fields_from_player_to_vector(balance: Balance) -> None:
    state = Simulation(balance, seed=3, mission=2).state
    fields = state.map.ice_fields
    assert len(fields) == 3
    player, vector = state.map.bases["player"], state.map.bases["vector"]

    def dist(field, base):
        return min((p.x - base.x) ** 2 + (p.y - base.y) ** 2 for p in field)

    assert dist(fields[0], player) < dist(fields[2], player)
    assert dist(fields[2], vector) < dist(fields[0], vector)


def test_field_owner_needs_drill_without_enemy_drill(balance: Balance) -> None:
    sim = Simulation(balance, seed=1, mission=2)
    center = sim.state.map.ice_fields[1]
    assert field_owner(sim.state, center) is None
    complete(sim, "player", "ice_drill", center[0])
    assert field_owner(sim.state, center) == "player"
    complete(sim, "vector", "ice_drill", center[-1])
    assert field_owner(sim.state, center) is None


def test_holding_two_fields_wins_mission_two(balance: Balance) -> None:
    sim = Simulation(balance, seed=1, mission=2)
    fields = sim.state.map.ice_fields
    for field in fields[:2]:
        complete(sim, "player", "ice_drill", field[len(field) // 2])
    assert fields_held(sim.state, "player") == 2
    sols = sim.balance.mission(2).hold_sols
    run_until(sim, lambda _: sim.state.outcome is not None, max_ms=(sols + 1) * 30_000 + 1000)
    assert sim.state.outcome is not None
    assert sim.state.outcome.winner == "player" and sim.state.outcome.reason == "ice_held"
    assert sim.state.sol == sols


def test_great_dome_is_unique_and_wins_mission_three(balance: Balance) -> None:
    sim = Simulation(balance, seed=1, mission=3)
    state = sim.state
    state.colonies["vector"].resources["metal"] = 2000
    spot = open_spot(state, state.map.bases["vector"])
    assert sim.build("vector", "great_dome", spot.x, spot.y).ok
    other = open_spot(state, Point(spot.x - 4, spot.y - 4))
    second = sim.build("vector", "great_dome", other.x, other.y)
    assert not second.ok and "одно" in second.reason
    site = next(b for b in state.buildings if b.type == "great_dome")
    site.build_progress, site.complete = 1.0, True
    sim.update(TICK_MS)
    assert state.outcome is not None and state.outcome.winner == "vector" and state.outcome.reason == "great_dome"


def test_great_dome_not_available_in_mission_two(balance: Balance) -> None:
    sim = Simulation(balance, seed=1, mission=2)
    sim.state.colonies["player"].resources["metal"] = 2000
    spot = open_spot(sim.state, sim.state.map.bases["player"])
    assert not sim.build("player", "great_dome", spot.x, spot.y).ok


def test_storm_cuts_solar_but_not_reactor(balance: Balance) -> None:
    sim = Simulation(balance, seed=1, mission=2)
    state = sim.state
    base = state.map.bases["player"]
    complete(sim, "player", "solar", open_spot(state, base))
    complete(sim, "player", "reactor", open_spot(state, base))
    colony = state.colonies["player"]
    before = colony.resources["energy"]
    apply_sol(state, sim.balance, "player")
    calm = colony.resources["energy"] - before
    state.storm_active = True
    before = colony.resources["energy"]
    apply_sol(state, sim.balance, "player")
    stormy = colony.resources["energy"] - before
    solar = sim.balance.buildings["solar"].energy
    assert calm - stormy == solar - round(solar * (1 - sim.balance.storm.solar_penalty))


def test_storm_starts_on_schedule_with_warning(balance: Balance) -> None:
    sim = Simulation(balance, seed=1, mission=2)
    first = round(sim.balance.storm.first_sec * 1000)
    events = run_until(sim, lambda ev: any(e.kind == "storm_start" for e in ev), max_ms=first + 1000)
    kinds = [e.kind for e in events]
    assert kinds.index("storm_warning") < kinds.index("storm_start")
    assert sim.state.storm_active and sim.state.elapsed_ms == first


def test_mission_one_has_no_storm_or_meteors(balance: Balance) -> None:
    sim = Simulation(balance, seed=1)
    # Без ботов колония рано задохнётся, поэтому сразу переносимся туда, где в миссиях 2–3 уже идут события.
    sim.state.elapsed_ms = 400_000
    sim.update(TICK_MS * 20)
    kinds = {e.kind for e in sim.drain_events()}
    assert not {"storm_start", "meteor_warning", "flare_start"} & kinds
    assert not sim.state.storm_active and not sim.state.meteors


def test_meteor_is_marked_then_hits(balance: Balance) -> None:
    sim = Simulation(balance, seed=5, mission=3)
    impact = meteor_impact_ms(sim.balance, 0)
    run_until(sim, lambda ev: any(e.kind == "meteor_warning" for e in ev), max_ms=impact)
    meteor = sim.state.meteors[0]
    victim = add_unit(sim.state, sim.balance, "player", "drone", Point(meteor.x, meteor.y))
    victim.task = "moving"
    hp = victim.hp
    events = run_until(sim, lambda ev: any(e.kind == "meteor_impact" for e in ev), max_ms=10_000)
    assert sim.state.elapsed_ms == impact
    assert victim.hp < hp or any(e.kind == "unit_destroyed" for e in events)
    assert sim.state.stats["vector"].enemy_units_killed == 0  # метеорит — не победа ВЕКТОРа


def test_meteors_are_deterministic(balance: Balance) -> None:
    def spots(seed: int) -> list[tuple[int, int]]:
        sim = Simulation(balance, seed=seed, mission=3)
        events = run_until(sim, lambda _: sim.state.meteors_spawned >= 3, max_ms=400_000)
        return [(round(e.x), round(e.y)) for e in events if e.kind == "meteor_warning"]

    assert spots(7) == spots(7)


def test_flare_hurts_rovers_outside_shelter_only(balance: Balance) -> None:
    sim = Simulation(balance, seed=1, mission=3)
    state = sim.state
    base = state.map.bases["player"]
    near = add_unit(state, sim.balance, "player", "guard_rover", find_free_tile_near(state, base))
    far = add_unit(state, sim.balance, "player", "guard_rover", open_spot(state, Point(24, 16)))
    drone = add_unit(state, sim.balance, "player", "drone", open_spot(state, Point(26, 18)))
    for u in (near, far, drone):
        u.task = "moving"
    start = round(sim.balance.solar_flare.first_sec * 1000)
    state.elapsed_ms = start - TICK_MS
    state.meteors_spawned = 1000  # прыжок во времени не должен обрушить накопившиеся метеориты
    sim.update(TICK_MS * 10)
    assert state.flare_active
    assert far.hp < sim.balance.units["guard_rover"].hp
    assert near.hp == sim.balance.units["guard_rover"].hp
    assert drone.hp == sim.balance.units["drone"].hp


@pytest.mark.parametrize("mission", [2, 3])
def test_missions_with_bots_are_deterministic(balance: Balance, mission: int) -> None:
    from reddome.bot.factory import make_bot
    from reddome.bot.strategist import BotStrategist

    def play() -> tuple:
        sim = Simulation(balance, seed=4, mission=mission)
        sim.add_controller(make_bot(sim.mission.bot, "vector"))
        sim.add_controller(BotStrategist("player"))
        sim.update(240_000)
        state = sim.state
        return (
            sorted((b.side, b.type, b.x, b.y, round(b.hp, 3)) for b in state.buildings),
            sorted((u.side, u.type, round(u.x, 3), round(u.y, 3)) for u in state.units),
            dict(state.colonies["vector"].resources),
        )

    assert play() == play()
