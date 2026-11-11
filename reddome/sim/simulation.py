"""Фасад симулятора: игра, бот, тесты и CLI датасета общаются с миром только через него."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from reddome.sim.build import cancel_construction, construction_step, place_building
from reddome.sim.combat import apply_damage, combat_step, command_attack, command_attack_move, is_fighter
from reddome.sim.dust import dust_step
from reddome.sim.economy import apply_sol
from reddome.sim.production import cancel_training, production_step, set_rally, train_unit
from reddome.sim.rules import check_outcome
from reddome.sim.state import building_by_id, create_initial_state, deposit_by_id, path_unit_next_to
from reddome.sim.types import (
    SIDES,
    BuildingType,
    CommandResult,
    Difficulty,
    Point,
    SimEvent,
    Side,
    Unit,
    UnitType,
    opponent_of,
)
from reddome.sim.units import command_move, move_units
from reddome.sim.workers import is_worker, set_idle, start_building, start_gathering, start_repair, start_returning, worker_step

if TYPE_CHECKING:
    from reddome.config.balance import Balance

#: Шаг логики — 100 мс (НФТ-03). Экономика считается раз в сол.
TICK_MS = 100


class Controller(Protocol):
    """Тот, кто отдаёт команды изнутри тика (бот). Так партия с ботом детерминирована при любом FPS."""

    def on_tick(self, sim: Simulation) -> None: ...


class Simulation:
    """Время копится и обрабатывается фиксированными шагами, поэтому партия детерминирована.

    Партию задают seed (карта) и сложность: одинаковые seed, сложность и команды дают одинаковую партию.
    Без difficulty берётся сложность, на которой загружен balance.
    """

    def __init__(self, balance: Balance, seed: int, difficulty: Difficulty | None = None) -> None:
        self.balance = balance if difficulty is None else balance.with_difficulty(difficulty)
        self.state = create_initial_state(self.balance, seed)
        self.controllers: list[Controller] = []
        #: События для эффектов и отчётов; забираются через drain_events() и на логику не влияют.
        self.events: list[SimEvent] = []
        self._accumulator_ms = 0.0

    def add_controller(self, controller: Controller) -> None:
        self.controllers.append(controller)

    def drain_events(self) -> list[SimEvent]:
        events, self.events = self.events, []
        return events

    def update(self, dt_ms: float) -> None:
        if self.state.outcome is not None:
            return
        self._accumulator_ms += dt_ms
        while self._accumulator_ms >= TICK_MS and self.state.outcome is None:
            self._accumulator_ms -= TICK_MS
            self._tick()

    def _tick(self) -> None:
        state, balance, events = self.state, self.balance, self.events
        state.tick += 1
        state.elapsed_ms += TICK_MS

        move_units(state, balance, TICK_MS / 1000)
        worker_step(state, balance, TICK_MS, events)
        construction_step(state, balance, TICK_MS, events)
        production_step(state, balance, TICK_MS, events)
        combat_step(state, balance, TICK_MS, events)
        dust_step(state, balance, TICK_MS, events)

        state.sol_elapsed_ms += TICK_MS
        if state.sol_elapsed_ms >= balance.sol_seconds * 1000:
            state.sol_elapsed_ms = 0
            state.sol += 1
            for side in SIDES:
                apply_sol(state, balance, side)

        state.outcome = check_outcome(state)
        if state.outcome is None:
            for controller in self.controllers:
                controller.on_tick(self)

    # --- Команды ----------------------------------------------------------------

    def _own_units(self, side: Side, unit_ids: list[int]) -> list[Unit]:
        return [u for u in self.state.units if u.side == side and u.id in unit_ids]

    def build(self, side: Side, type: BuildingType, x: int, y: int, worker_id: int | None = None) -> CommandResult:
        return place_building(self.state, self.balance, side, type, x, y, worker_id)

    def cancel_construction(self, side: Side, building_id: int) -> CommandResult:
        return cancel_construction(self.state, self.balance, side, building_id)

    def help_build(self, side: Side, unit_ids: list[int], building_id: int) -> CommandResult:
        site = building_by_id(self.state, building_id)
        if site is None or site.side != side or site.complete:
            return CommandResult.failure("Это не стройплощадка")
        sent = sum(start_building(self.state, u, site) for u in self._own_units(side, unit_ids) if is_worker(u))
        return CommandResult.success() if sent else CommandResult.failure("Строить могут только дроны")

    def train(self, side: Side, type: UnitType, producer_id: int | None = None) -> CommandResult:
        return train_unit(self.state, self.balance, side, type, producer_id)

    def cancel_training(self, side: Side, building_id: int, index: int = -1) -> CommandResult:
        return cancel_training(self.state, self.balance, side, building_id, index)

    def set_rally(self, side: Side, building_id: int, point: Point) -> CommandResult:
        return set_rally(self.state, side, building_id, point)

    def move(self, side: Side, unit_ids: list[int], target: Point) -> CommandResult:
        return command_move(self.state, side, unit_ids, target)

    def gather(self, side: Side, unit_ids: list[int], deposit_id: int) -> CommandResult:
        deposit = deposit_by_id(self.state, deposit_id)
        if deposit is None or deposit.amount <= 0:
            return CommandResult.failure("Здесь нет руды")
        sent = sum(start_gathering(self.state, u, deposit) for u in self._own_units(side, unit_ids) if is_worker(u))
        return CommandResult.success() if sent else CommandResult.failure("Добывать могут только дроны")

    def repair(self, side: Side, unit_ids: list[int], building_id: int) -> CommandResult:
        building = building_by_id(self.state, building_id)
        if building is None or building.side != side or not building.complete:
            return CommandResult.failure("Чинить можно только своё готовое здание")
        sent = sum(start_repair(self.state, u, building) for u in self._own_units(side, unit_ids) if is_worker(u))
        return CommandResult.success() if sent else CommandResult.failure("Чинить могут только дроны")

    def return_home(self, side: Side, unit_ids: list[int]) -> CommandResult:
        """«Вернуться»: дрон несёт груз на базу, ровер отходит к куполу."""
        dome = next((b for b in self.state.buildings if b.side == side and b.type == "dome"), None)
        moved = 0
        for unit in self._own_units(side, unit_ids):
            if is_worker(unit) and unit.carry > 0:
                moved += start_returning(self.state, unit)
            elif dome is not None and path_unit_next_to(self.state, unit, dome.x, dome.y):
                unit.task = "moving"
                unit.target_id = None
                unit.attack_point = None
                moved += 1
        return CommandResult.success() if moved else CommandResult.failure("Некуда возвращаться")

    def stop(self, side: Side, unit_ids: list[int]) -> CommandResult:
        for unit in self._own_units(side, unit_ids):
            set_idle(unit)
            unit.attack_point = None
            unit.resume_gathering = False
        return CommandResult.success()

    def attack(self, side: Side, unit_ids: list[int], target_id: int) -> CommandResult:
        return command_attack(self.state, self.balance, side, unit_ids, target_id)

    def attack_move(self, side: Side, unit_ids: list[int], point: Point) -> CommandResult:
        return command_attack_move(self.state, self.balance, side, unit_ids, point)

    def is_fighter(self, unit: Unit) -> bool:
        return is_fighter(self.balance, unit)

    def damage_building(self, building_id: int, amount: float) -> None:
        """Урон зданию (отладка и тесты); разрушенное здание убирается с карты."""
        building = building_by_id(self.state, building_id)
        if building is None:
            return
        apply_damage(self.state, building, amount, opponent_of(building.side), self.events)
        self.state.outcome = check_outcome(self.state)
