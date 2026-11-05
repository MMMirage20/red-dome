"""Очередь сборки юнитов (ФТ-08): купол собирает дронов, ангар — охранных роверов."""

from __future__ import annotations

from typing import TYPE_CHECKING

from reddome.sim.economy import supply_cap, supply_reserved, supply_used
from reddome.sim.state import add_unit, building_by_id, deposit_at, find_free_tile_near, path_unit_to
from reddome.sim.types import Building, BuildingType, CommandResult, GameState, Point, QueueItem, SimEvent, Side, Unit, UnitType
from reddome.sim.workers import start_gathering

if TYPE_CHECKING:
    from reddome.config.balance import Balance

PRODUCER: dict[UnitType, BuildingType] = {"drone": "dome", "guard_rover": "hangar"}


def _producers(state: GameState, side: Side, type: UnitType) -> list[Building]:
    return [b for b in state.buildings if b.side == side and b.type == PRODUCER[type] and b.hp > 0]


def train_unit(
    state: GameState, balance: Balance, side: Side, type: UnitType, producer_id: int | None = None
) -> CommandResult:
    """Поставить юнита в очередь. Металл списывается сразу, лимит армии резервируется сразу.

    Без producer_id выбирается готовое здание стороны с самой короткой очередью.
    """
    spec = balance.units[type]
    if producer_id is not None:
        producer = building_by_id(state, producer_id)
        if producer is None or producer.side != side or producer.type != PRODUCER[type]:
            return CommandResult.failure("Это здание не собирает такой юнит")
        candidates = [producer]
    else:
        candidates = _producers(state, side, type)
        if not candidates:
            return CommandResult.failure("Нужен ангар" if type == "guard_rover" else "Нет командного купола")
    ready = [b for b in candidates if b.complete]
    if not ready:
        return CommandResult.failure("Здание ещё строится")
    powered = [b for b in ready if b.powered]
    if not powered:
        return CommandResult.failure("Производитель без энергии")
    producer = min(powered, key=lambda b: (len(b.queue), b.id))
    if len(producer.queue) >= balance.production.queue_limit:
        return CommandResult.failure(f"Очередь заполнена ({balance.production.queue_limit})")
    if state.colonies[side].resources["metal"] < spec.cost:
        return CommandResult.failure("Не хватает металла")
    taken = supply_used(state, balance, side) + supply_reserved(state, balance, side)
    if taken + spec.supply > supply_cap(state, balance, side):
        return CommandResult.failure("Нужен генератор кислорода")
    state.colonies[side].resources["metal"] -= spec.cost
    producer.queue.append(QueueItem(type=type, remaining_ms=int(spec.build_time_sec * 1000)))
    return CommandResult.success(producer.id)


def cancel_training(state: GameState, balance: Balance, side: Side, building_id: int, index: int = -1) -> CommandResult:
    """Убрать юнита из очереди с полным возвратом металла (по умолчанию — последнего)."""
    producer = building_by_id(state, building_id)
    if producer is None or producer.side != side or not producer.queue:
        return CommandResult.failure("Очередь пуста")
    try:
        item = producer.queue.pop(index)
    except IndexError:
        return CommandResult.failure("Нет такого места в очереди")
    state.colonies[side].resources["metal"] += balance.units[item.type].cost
    return CommandResult.success()


def set_rally(state: GameState, side: Side, building_id: int, point: Point) -> CommandResult:
    producer = building_by_id(state, building_id)
    if producer is None or producer.side != side or producer.type not in PRODUCER.values():
        return CommandResult.failure("Точку сбора можно задать только куполу или ангару")
    producer.rally = point
    return CommandResult.success()


def _send_to_rally(state: GameState, unit: Unit, rally: Point | None) -> None:
    if rally is None:
        return
    deposit = deposit_at(state, rally.x, rally.y)
    if unit.type == "drone" and deposit is not None:
        start_gathering(state, unit, deposit)
    elif path_unit_to(state, unit, rally):
        unit.task = "moving"


def production_step(state: GameState, balance: Balance, dt_ms: int, events: list[SimEvent]) -> None:
    """Сборка идёт у первого юнита в очереди готового запитанного здания."""
    for producer in state.buildings:
        if not producer.queue or not producer.complete or not producer.powered:
            continue
        item = producer.queue[0]
        item.remaining_ms = max(0, item.remaining_ms - dt_ms)
        if item.remaining_ms > 0:
            continue
        spot = find_free_tile_near(state, Point(producer.x, producer.y))
        if spot is None:
            continue  # Ждём, пока место у здания освободится.
        producer.queue.pop(0)
        unit = add_unit(state, balance, producer.side, item.type, spot)
        state.stats[producer.side].units_trained += 1
        events.append(SimEvent("unit_trained", producer.side, spot.x, spot.y, subject=item.type))
        _send_to_rally(state, unit, producer.rally)
