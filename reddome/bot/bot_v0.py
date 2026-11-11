"""Бот «ВЕКТОР» v0 — скриптовый противник для MVP 1 (ФТ-10, W3-11).

Играет через своих дронов по тем же правилам, что игрок:
- держит дронов на добыче и докупает их до bot.target_drones;
- строит по BUILD_ORDER на ближайшей к базе подходящей клетке;
- после ангара собирает роверов и следит за лимитом армии и энергией;
- отправляет волны атак по таймингам из balance.bot: в волну уходит ровно BotSpec.wave_size(n)
  самых здоровых свободных роверов, остальные остаются у базы охраной.

Числа бота берутся из balance.side(сторона).bot: там уже учтена сложность партии.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, cast

from reddome.sim.build import can_place
from reddome.sim.economy import supply_cap, supply_reserved, supply_used
from reddome.sim.simulation import TICK_MS
from reddome.sim.state import distance, find_free_tile_near
from reddome.sim.types import Building, BuildingType, Point, Side, Unit, UnitType, opponent_of
from reddome.sim.workers import nearest_deposit

if TYPE_CHECKING:
    from reddome.config.balance import BotSpec
    from reddome.sim.simulation import Simulation

#: Радиус поиска места для обычных зданий вокруг купола, клетки.
BUILD_RADIUS = 9


@dataclass(frozen=True)
class BuildStep:
    kind: Literal["unit", "building"]
    type: str


#: Порядок стройки. Отличается от исходного ТЗ: лимит армии купола мал (3 стартовых дрона + 2),
#: поэтому генератор кислорода нужен рано, а без солнечной панели быстро кончается энергия.
BUILD_ORDER: tuple[BuildStep, ...] = (
    BuildStep("unit", "drone"),
    BuildStep("building", "oxy_gen"),
    BuildStep("unit", "drone"),
    BuildStep("building", "solar"),
    BuildStep("building", "ice_drill"),
    BuildStep("building", "regolith"),
    BuildStep("building", "hangar"),
    BuildStep("building", "solar"),
)


class BotV0:
    def __init__(self, side: Side = "vector", params: BotSpec | None = None) -> None:
        self.side = side
        #: Свои числа бота вместо balance.side(side).bot — генератор датасета их слегка меняет (ФТ-17).
        self.params = params
        self.step = 0
        self.ticks = 0
        self.waves_sent = 0
        self.next_wave_ms: int | None = None
        #: Отправленные волны: (время партии в мс, сколько роверов ушло) — для отчётов баланса.
        self.waves: list[tuple[int, int]] = []

    def spec(self, sim: Simulation) -> BotSpec:
        return self.params if self.params is not None else sim.balance.side(self.side).bot

    def on_tick(self, sim: Simulation) -> None:
        self.ticks += 1
        if self.ticks % max(1, self.spec(sim).think_interval_ms // TICK_MS) == 0:
            self.think(sim)

    # --- Решения ------------------------------------------------------------------

    def think(self, sim: Simulation) -> None:
        self._keep_drones_busy(sim)
        if self.step < len(BUILD_ORDER):
            self._follow_build_order(sim)
        else:
            self._grow(sim)
        self._send_waves(sim)

    def _own_units(self, sim: Simulation, type: UnitType) -> list[Unit]:
        return [u for u in sim.state.units if u.side == self.side and u.type == type]

    def _own_buildings(self, sim: Simulation, type: BuildingType) -> list[Building]:
        return [b for b in sim.state.buildings if b.side == self.side and b.type == type]

    def _queued(self, sim: Simulation, type: UnitType) -> int:
        return sum(1 for b in sim.state.buildings if b.side == self.side for item in b.queue if item.type == type)

    def _metal(self, sim: Simulation) -> int:
        return sim.state.colonies[self.side].resources["metal"]

    def _keep_drones_busy(self, sim: Simulation) -> None:
        for drone in self._own_units(sim, "drone"):
            if drone.task == "idle":
                deposit = nearest_deposit(sim.state, drone.x, drone.y)
                if deposit is not None:
                    sim.gather(self.side, [drone.id], deposit.id)

    def _follow_build_order(self, sim: Simulation) -> None:
        item = BUILD_ORDER[self.step]
        if item.kind == "unit":
            if sim.train(self.side, cast(UnitType, item.type)).ok:
                self.step += 1
            return
        if self._try_build(sim, cast(BuildingType, item.type)):
            self.step += 1

    def _try_build(self, sim: Simulation, type: BuildingType) -> bool:
        if self._metal(sim) < sim.balance.buildings[type].cost:
            return False
        spot = self.find_spot(sim, type)
        return spot is not None and sim.build(self.side, type, spot.x, spot.y).ok

    def _grow(self, sim: Simulation) -> None:
        """После порядка стройки: энергия, лимит армии, дроны, роверы — в таком приоритете."""
        state, balance = sim.state, sim.balance
        colony = state.colonies[self.side]
        building_now = {b.type for b in state.buildings if b.side == self.side and not b.complete}

        if colony.last_delta["energy"] < 0 and colony.resources["energy"] < 60 and "solar" not in building_now:
            if self._try_build(sim, "solar"):
                return
        taken = supply_used(state, balance, self.side) + supply_reserved(state, balance, self.side)
        if taken >= supply_cap(state, balance, self.side) and not building_now & {"oxy_gen", "ice_drill"}:
            generators = len(self._own_buildings(sim, "oxy_gen"))
            drills = len(self._own_buildings(sim, "ice_drill"))
            if self._try_build(sim, "ice_drill" if generators >= drills else "oxy_gen"):
                return
        drones = len(self._own_units(sim, "drone")) + self._queued(sim, "drone")
        if drones < self.spec(sim).target_drones:
            sim.train(self.side, "drone")
        if self._queued(sim, "guard_rover") < 2:
            sim.train(self.side, "guard_rover")

    def _send_waves(self, sim: Simulation) -> None:
        state, bot = sim.state, self.spec(sim)
        if self.next_wave_ms is None:
            self.next_wave_ms = int(bot.first_wave_sec * 1000)
        if state.elapsed_ms < self.next_wave_ms:
            return
        size = bot.wave_size(self.waves_sent)
        ready = [u for u in self._own_units(sim, "guard_rover") if u.task == "idle"]
        if len(ready) < size:
            return
        target = self.wave_target(sim)
        if target is None:
            return
        wave = sorted(ready, key=lambda u: (-u.hp, u.id))[:size]
        sim.attack_move(self.side, [u.id for u in wave], target)
        self.waves.append((state.elapsed_ms, len(wave)))
        self.waves_sent += 1
        self.next_wave_ms += int(bot.wave_interval_sec * 1000)

    # --- Поиск мест ---------------------------------------------------------------

    def wave_target(self, sim: Simulation) -> Point | None:
        """Свободная клетка рядом с ближайшим к базе бота зданием противника."""
        base = sim.state.map.bases[self.side]
        enemy = opponent_of(self.side)
        targets = [b for b in sim.state.buildings if b.side == enemy]
        if not targets:
            return None
        target = min(targets, key=lambda b: (distance(base.x, base.y, b.x, b.y), b.id))
        return find_free_tile_near(sim.state, Point(target.x, target.y), 2)

    def find_spot(self, sim: Simulation, type: BuildingType) -> Point | None:
        """Ближайшая к базе подходящая клетка. Обычные здания ставятся с зазором в клетку,
        чтобы не замуровать купол и проходы."""
        state, balance = sim.state, sim.balance
        base = state.map.bases[self.side]
        needs = balance.buildings[type].needs
        if needs == "ore":
            deposit = nearest_deposit(state, base.x, base.y)
            candidates = list(deposit.tiles) if deposit is not None else []
        elif needs == "ice":
            candidates = [
                Point(i % state.map.width, i // state.map.width)
                for i, tile in enumerate(state.map.tiles)
                if tile == "ice"
            ]
        else:
            candidates = [
                Point(base.x + dx, base.y + dy)
                for dy in range(-BUILD_RADIUS, BUILD_RADIUS + 1)
                for dx in range(-BUILD_RADIUS, BUILD_RADIUS + 1)
            ]
        candidates.sort(key=lambda p: (distance(base.x, base.y, p.x, p.y), p.y, p.x))
        for p in candidates:
            if needs is None and self._crowded(sim, p):
                continue
            if can_place(state, balance, self.side, type, p.x, p.y).ok:
                return p
        return None

    def _crowded(self, sim: Simulation, p: Point) -> bool:
        if any(max(abs(b.x - p.x), abs(b.y - p.y)) <= 1 for b in sim.state.buildings):
            return True
        # Не перегораживаем рудные поля обычными зданиями.
        return any(max(abs(t.x - p.x), abs(t.y - p.y)) <= 1 for d in sim.state.deposits for t in d.tiles)
