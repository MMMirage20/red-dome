"""Рабочие-дроны: добыча руды, сдача груза, стройка и ремонт (как рабочие в Warcraft III).

Состояния дрона (Unit.task):
    idle         — стоит и ждёт приказа;
    moving       — идёт по приказу;
    to_resource  — идёт к рудному полю (target_id = id поля);
    waiting      — поле занято (max_workers), ждёт рядом своей очереди;
    gathering    — добывает gather_time_sec, потом берёт carry металла;
    returning    — несёт груз к ближайшему куполу или переработчику (target_id = id здания);
    to_site      — идёт к стройплощадке (target_id = id здания);
    building     — строит; прогресс считает sim/build.py;
    repairing    — идёт к повреждённому зданию и чинит его за металл.

Цикл добычи повторяется сам: после сдачи груза дрон возвращается к своему полю (home_deposit),
а если поле опустело — к ближайшему непустому.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from reddome.sim.state import (
    building_by_id,
    chebyshev,
    deplete_deposit,
    deposit_by_id,
    distance,
    is_blocked,
    path_unit_next_to,
    path_unit_to,
)
from reddome.sim.types import GATHER_TASKS, Building, Deposit, GameState, Point, SimEvent, Unit

if TYPE_CHECKING:
    from reddome.config.balance import Balance

#: Здания, которые принимают руду.
DROPOFF_TYPES = ("dome", "regolith")


def is_worker(unit: Unit) -> bool:
    return unit.type == "drone"


def gatherers_on(state: GameState, deposit_id: int) -> int:
    return sum(1 for u in state.units if u.task == "gathering" and u.target_id == deposit_id)


def nearest_deposit(state: GameState, x: float, y: float) -> Deposit | None:
    """Ближайшее непустое месторождение; при равенстве — с меньшим id."""
    best: tuple[float, int] | None = None
    result = None
    for deposit in state.deposits:
        if deposit.amount <= 0:
            continue
        d = min(distance(x, y, p.x, p.y) for p in deposit.tiles)
        if best is None or (d, deposit.id) < best:
            best, result = (d, deposit.id), deposit
    return result


def nearest_dropoff(state: GameState, unit: Unit) -> Building | None:
    candidates = [
        b
        for b in state.buildings
        if b.side == unit.side and b.complete and b.hp > 0 and b.type in DROPOFF_TYPES
    ]
    return min(candidates, key=lambda b: (distance(unit.x, unit.y, b.x, b.y), b.id), default=None)


def nearest_ore_tile(state: GameState, deposit: Deposit, unit: Unit) -> Point | None:
    free = [p for p in deposit.tiles if not is_blocked(state, p.x, p.y)]
    return min(free, key=lambda p: (distance(unit.x, unit.y, p.x, p.y), p.y, p.x), default=None)


def set_idle(unit: Unit) -> None:
    unit.task = "idle"
    unit.target_id = None
    unit.path = []
    unit.work_ms = 0


# --- Начало задач (вызываются командами и автоматом) ---------------------------


def start_returning(state: GameState, unit: Unit) -> bool:
    dropoff = nearest_dropoff(state, unit)
    if dropoff is None or not path_unit_next_to(state, unit, dropoff.x, dropoff.y):
        set_idle(unit)
        return False
    unit.task = "returning"
    unit.target_id = dropoff.id
    return True


def start_gathering(state: GameState, unit: Unit, deposit: Deposit) -> bool:
    """Отправить дрона добывать на поле. Если он несёт груз, сначала отнесёт его."""
    unit.home_deposit = deposit.id
    unit.resume_gathering = False
    unit.work_ms = 0
    if unit.carry > 0:
        return start_returning(state, unit)
    tile = nearest_ore_tile(state, deposit, unit)
    if tile is None or not path_unit_to(state, unit, tile):
        set_idle(unit)
        return False
    unit.task = "to_resource"
    unit.target_id = deposit.id
    return True


def gather_nearest(state: GameState, unit: Unit) -> bool:
    deposit = nearest_deposit(state, unit.x, unit.y)
    if deposit is None:
        if unit.carry > 0:
            return start_returning(state, unit)
        set_idle(unit)
        return False
    return start_gathering(state, unit, deposit)


def start_building(state: GameState, unit: Unit, site: Building) -> bool:
    """Дрон идёт строить. Если до этого добывал, после стройки вернётся к добыче."""
    resume = unit.task in GATHER_TASKS and unit.home_deposit is not None
    if not path_unit_next_to(state, unit, site.x, site.y):
        return False
    unit.resume_gathering = resume or unit.resume_gathering
    unit.task = "to_site"
    unit.target_id = site.id
    unit.work_ms = 0
    return True


def start_repair(state: GameState, unit: Unit, building: Building) -> bool:
    resume = unit.task in GATHER_TASKS and unit.home_deposit is not None
    if not path_unit_next_to(state, unit, building.x, building.y):
        return False
    unit.resume_gathering = resume or unit.resume_gathering
    unit.task = "repairing"
    unit.target_id = building.id
    unit.work_ms = 0
    return True


def finish_job(state: GameState, unit: Unit) -> None:
    """После стройки или ремонта: вернуться к добыче, отнести груз или встать."""
    deposit = deposit_by_id(state, unit.home_deposit)
    resume = unit.resume_gathering
    unit.resume_gathering = False
    if resume and deposit is not None and deposit.amount > 0:
        start_gathering(state, unit, deposit)
    elif resume:
        gather_nearest(state, unit)
    elif unit.carry > 0:
        start_returning(state, unit)
    else:
        set_idle(unit)


# --- Шаг автомата -------------------------------------------------------------


def deliver(state: GameState, balance: Balance, unit: Unit, building: Building, events: list[SimEvent]) -> None:
    amount = unit.carry
    if building.type == "regolith" and building.powered:
        amount = int(unit.carry * (1 + balance.workers.refinery_bonus))
    state.colonies[unit.side].resources["metal"] += amount
    state.stats[unit.side].metal_mined += amount
    unit.carry = 0
    events.append(SimEvent("dropoff", unit.side, building.x, building.y, value=amount, subject=building.type))


def _gather_again(state: GameState, unit: Unit) -> None:
    deposit = deposit_by_id(state, unit.home_deposit)
    if deposit is not None and deposit.amount > 0:
        start_gathering(state, unit, deposit)
    else:
        gather_nearest(state, unit)


def _step_gathering(state: GameState, balance: Balance, unit: Unit, dt_ms: int, events: list[SimEvent]) -> None:
    deposit = deposit_by_id(state, unit.target_id)
    if deposit is None or deposit.amount <= 0:
        gather_nearest(state, unit)
        return
    unit.work_ms += dt_ms
    if unit.work_ms < balance.workers.gather_time_sec * 1000:
        return
    take = min(balance.workers.carry, deposit.amount)
    deposit.amount -= take
    unit.carry = take
    unit.work_ms = 0
    if deposit.amount == 0:
        deplete_deposit(state, deposit)
        tile = deposit.tiles[0]
        events.append(SimEvent("deposit_depleted", unit.side, tile.x, tile.y))
    start_returning(state, unit)


def _step_repair(state: GameState, balance: Balance, unit: Unit, building: Building, dt_ms: int) -> None:
    max_hp = balance.max_hp(building.side, building.type)
    hp_per_metal = 100 / balance.workers.repair_metal_per_100_hp
    gain = min(balance.workers.repair_hp_per_sec * dt_ms / 1000, max_hp - building.hp)
    building.hp += gain
    # work_ms здесь копит починенное здоровье в тысячных долях; за каждые hp_per_metal списывается 1 металл.
    unit.work_ms += round(gain * 1000)
    colony = state.colonies[unit.side]
    while unit.work_ms >= hp_per_metal * 1000:
        if colony.resources["metal"] < 1:
            finish_job(state, unit)
            return
        colony.resources["metal"] -= 1
        unit.work_ms -= round(hp_per_metal * 1000)
    if building.hp >= max_hp:
        finish_job(state, unit)


def worker_step(state: GameState, balance: Balance, dt_ms: int, events: list[SimEvent]) -> None:
    """Один тик автомата для всех дронов. Пока дрон идёт по пути, автомат его не трогает."""
    for unit in list(state.units):
        if not is_worker(unit) or unit.path:
            continue
        task = unit.task
        if task == "moving":
            set_idle(unit)
        elif task in ("to_resource", "waiting"):
            deposit = deposit_by_id(state, unit.target_id)
            if deposit is None or deposit.amount <= 0:
                gather_nearest(state, unit)
            elif gatherers_on(state, deposit.id) < balance.deposit.max_workers:
                unit.task = "gathering"
                unit.work_ms = 0
            else:
                unit.task = "waiting"
        elif task == "gathering":
            _step_gathering(state, balance, unit, dt_ms, events)
        elif task == "returning":
            dropoff = building_by_id(state, unit.target_id)
            ready = dropoff is not None and dropoff.complete and dropoff.side == unit.side
            if ready and dropoff is not None and chebyshev(unit.x, unit.y, dropoff.x, dropoff.y) <= 1:
                deliver(state, balance, unit, dropoff, events)
                _gather_again(state, unit)
            else:
                start_returning(state, unit)
        elif task in ("to_site", "building"):
            site = building_by_id(state, unit.target_id)
            if site is None or site.complete or site.side != unit.side:
                finish_job(state, unit)
            elif task == "to_site":
                if chebyshev(unit.x, unit.y, site.x, site.y) <= 1:
                    unit.task = "building"
                elif not path_unit_next_to(state, unit, site.x, site.y):
                    set_idle(unit)
        elif task == "repairing":
            building = building_by_id(state, unit.target_id)
            if building is None or building.side != unit.side or not building.complete:
                finish_job(state, unit)
            elif chebyshev(unit.x, unit.y, building.x, building.y) <= 1:
                _step_repair(state, balance, unit, building, dt_ms)
            elif not path_unit_next_to(state, unit, building.x, building.y):
                set_idle(unit)
