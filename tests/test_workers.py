"""Рабочие-дроны: добыча, истощение полей, стройка, очередь сборки (часть A)."""

from __future__ import annotations

from reddome.config.balance import Balance
from reddome.sim.economy import supply_cap
from reddome.sim.map import tile_at
from reddome.sim.simulation import TICK_MS, Simulation
from reddome.sim.state import add_building, add_unit, deposit_by_id
from reddome.sim.types import Building, CommandResult, Point
from reddome.sim.workers import gatherers_on
from tests.helpers import neighbors, open_spot, run_until

PLAYER_NEAR_DEPOSIT = 1


def player_drones(sim: Simulation) -> list:
    return [u for u in sim.state.units if u.side == "player" and u.type == "drone"]


def test_gather_cycle_adds_exactly_carry(balance: Balance) -> None:
    sim = Simulation(balance, seed=1)
    drone = player_drones(sim)[0]
    deposit = deposit_by_id(sim.state, PLAYER_NEAR_DEPOSIT)
    assert deposit is not None
    metal = sim.state.colonies["player"].resources["metal"]

    assert sim.gather("player", [drone.id], deposit.id).ok
    events = run_until(sim, lambda ev: any(e.kind == "dropoff" for e in ev))

    dropoffs = [e for e in events if e.kind == "dropoff"]
    assert [e.value for e in dropoffs] == [balance.workers.carry]
    assert dropoffs[0].subject == "dome"
    assert sim.state.colonies["player"].resources["metal"] == metal + balance.workers.carry
    assert deposit.amount == deposit.initial - balance.workers.carry
    # Цикл повторяется сам: дрон снова идёт к своему полю.
    assert drone.task == "to_resource" and drone.home_deposit == deposit.id


def test_refinery_gives_bonus(balance: Balance) -> None:
    sim = Simulation(balance, seed=1)
    deposit = deposit_by_id(sim.state, PLAYER_NEAR_DEPOSIT)
    assert deposit is not None
    center = deposit.tiles[len(deposit.tiles) // 2]
    add_building(sim.state, balance, "player", "regolith", center)
    drone = player_drones(sim)[0]

    sim.gather("player", [drone.id], deposit.id)
    events = run_until(sim, lambda ev: any(e.kind == "dropoff" for e in ev))

    dropoff = next(e for e in events if e.kind == "dropoff")
    assert dropoff.subject == "regolith"
    assert dropoff.value == int(balance.workers.carry * (1 + balance.workers.refinery_bonus))


def test_depleted_deposit_turns_to_ground_and_drone_moves_on(balance: Balance) -> None:
    sim = Simulation(balance, seed=1)
    deposit = deposit_by_id(sim.state, PLAYER_NEAR_DEPOSIT)
    assert deposit is not None
    deposit.amount = balance.workers.carry
    drone = player_drones(sim)[0]

    sim.gather("player", [drone.id], deposit.id)
    events = run_until(sim, lambda _: deposit.amount == 0 and drone.carry == 0 and drone.task == "to_resource")

    assert any(e.kind == "deposit_depleted" for e in events)
    assert all(tile_at(sim.state.map, p.x, p.y) == "ground" for p in deposit.tiles)
    assert drone.home_deposit != deposit.id


def test_worker_limit_per_deposit(balance: Balance) -> None:
    sim = Simulation(balance, seed=1)
    deposit = deposit_by_id(sim.state, PLAYER_NEAR_DEPOSIT)
    assert deposit is not None
    base = sim.state.map.bases["player"]
    for _ in range(3):
        add_unit(sim.state, balance, "player", "drone", open_spot(sim.state, base))
    drones = player_drones(sim)
    assert len(drones) == 6
    sim.gather("player", [d.id for d in drones], deposit.id)

    saw_waiting = False
    for _ in range(600):
        sim.update(TICK_MS)
        assert gatherers_on(sim.state, deposit.id) <= balance.deposit.max_workers
        saw_waiting |= any(d.task == "waiting" for d in drones)
    assert saw_waiting


def test_site_gives_nothing_until_complete(balance: Balance) -> None:
    sim = Simulation(balance, seed=1)
    spot = open_spot(sim.state, sim.state.map.bases["player"])
    result = sim.build("player", "oxy_gen", spot.x, spot.y)
    assert result.ok
    site = next(b for b in sim.state.buildings if b.id == result.id)

    sim.update(5_000)
    assert not site.complete
    assert supply_cap(sim.state, balance, "player") == balance.buildings["dome"].supply
    # Недостроенное здание не производит юнитов.
    assert sim.train("player", "drone").ok  # купол собирает
    assert site.queue == []

    run_until(sim, lambda _: site.complete)
    expected = balance.buildings["dome"].supply + balance.buildings["oxy_gen"].supply
    assert supply_cap(sim.state, balance, "player") == expected


def build_time_with(balance: Balance, builders: int) -> int:
    """Сколько мс строится панель, если вокруг площадки уже стоят builders дронов."""
    sim = Simulation(balance, seed=1)
    spot = open_spot(sim.state, sim.state.map.bases["player"])
    site: Building = add_building(sim.state, balance, "player", "solar", spot, complete=False)
    ids = [add_unit(sim.state, balance, "player", "drone", p).id for p in neighbors(spot)[:builders]]
    assert sim.help_build("player", ids, site.id).ok
    start = sim.state.elapsed_ms
    run_until(sim, lambda _: site.complete)
    return sim.state.elapsed_ms - start


def test_more_builders_build_faster_up_to_limit(balance: Balance) -> None:
    one, two = build_time_with(balance, 1), build_time_with(balance, 2)
    at_limit = build_time_with(balance, balance.construction.max_builders)
    over_limit = build_time_with(balance, balance.construction.max_builders + 1)

    assert abs(two - one / 2) <= 2 * TICK_MS
    assert over_limit == at_limit
    assert at_limit < two


def test_cancel_construction_refunds_part(balance: Balance) -> None:
    sim = Simulation(balance, seed=1)
    metal = sim.state.colonies["player"].resources["metal"]
    spot = open_spot(sim.state, sim.state.map.bases["player"])
    result = sim.build("player", "solar", spot.x, spot.y)
    assert result.ok and result.id is not None

    assert sim.cancel_construction("player", result.id).ok

    cost = balance.buildings["solar"].cost
    refund = int(cost * balance.construction.refund_ratio)
    assert sim.state.colonies["player"].resources["metal"] == metal - cost + refund
    assert all(b.id != result.id for b in sim.state.buildings)


def test_production_queue_limit_time_and_refund(balance: Balance) -> None:
    sim = Simulation(balance, seed=1)
    add_building(sim.state, balance, "player", "oxy_gen", open_spot(sim.state, sim.state.map.bases["player"]))
    sim.state.colonies["player"].resources["metal"] = 1000
    limit = balance.production.queue_limit
    for _ in range(limit):
        assert sim.train("player", "drone").ok
    assert sim.train("player", "drone") == CommandResult.failure(f"Очередь заполнена ({limit})")

    dome = next(b for b in sim.state.buildings if b.side == "player" and b.type == "dome")
    drones_before = len(player_drones(sim))
    build_ms = int(balance.units["drone"].build_time_sec * 1000)
    sim.update(build_ms - TICK_MS)
    assert len(player_drones(sim)) == drones_before
    sim.update(TICK_MS)
    assert len(player_drones(sim)) == drones_before + 1
    assert len(dome.queue) == limit - 1

    metal = sim.state.colonies["player"].resources["metal"]
    assert sim.cancel_training("player", dome.id).ok
    assert sim.state.colonies["player"].resources["metal"] == metal + balance.units["drone"].cost
    assert len(dome.queue) == limit - 2


def test_rally_point_on_ore_sends_new_drone_to_gather(balance: Balance) -> None:
    sim = Simulation(balance, seed=1)
    dome = next(b for b in sim.state.buildings if b.side == "player" and b.type == "dome")
    deposit = deposit_by_id(sim.state, PLAYER_NEAR_DEPOSIT)
    assert deposit is not None
    assert sim.set_rally("player", dome.id, deposit.tiles[0]).ok
    assert sim.train("player", "drone").ok

    run_until(sim, lambda _: len(player_drones(sim)) == 4)

    newest = max(player_drones(sim), key=lambda u: u.id)
    assert newest.task == "to_resource" and newest.target_id == deposit.id


def test_drone_returns_to_gathering_after_building(balance: Balance) -> None:
    sim = Simulation(balance, seed=1)
    drone = player_drones(sim)[0]
    sim.gather("player", [drone.id], PLAYER_NEAR_DEPOSIT)
    sim.update(2_000)
    spot = open_spot(sim.state, sim.state.map.bases["player"])

    result = sim.build("player", "solar", spot.x, spot.y, worker_id=drone.id)
    assert result.ok
    site = next(b for b in sim.state.buildings if b.id == result.id)
    run_until(sim, lambda _: site.complete)
    sim.update(TICK_MS)

    assert drone.task in ("to_resource", "returning", "gathering", "waiting")
    assert drone.home_deposit == PLAYER_NEAR_DEPOSIT


def test_only_drones_can_build(balance: Balance) -> None:
    sim = Simulation(balance, seed=1)
    rover = add_unit(sim.state, balance, "player", "guard_rover", open_spot(sim.state, sim.state.map.bases["player"]))
    spot = open_spot(sim.state, Point(rover.x + 4, rover.y))
    assert sim.build("player", "solar", spot.x, spot.y, worker_id=rover.id) == CommandResult.failure(
        "Строить может только дрон"
    )
