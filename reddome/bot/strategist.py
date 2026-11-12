"""Бот «ВЕКТОР» «Стратег» — противник миссии 2 «Война за лёд» (этап 3, ФТ-26).

Играет по тем же правилам, что игрок, и в дополнение к «ВЕКТОРу» v0:
- ставит буры на своё и центральное ледяное поле, а позже — и на поле соперника;
- прикрывает бур на центральном поле турелью;
- строит реактор и собирает ракетных роверов вперемешку с охранными;
- волны бьют по бурам соперника на ледяных полях, а свободные роверы защищают базу и свои буры.

Числа волн — те же balance.side(сторона).bot, что у v0, поэтому сложность действует и здесь.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from reddome.bot.bot_v0 import BotV0, BuildStep
from reddome.sim.build import can_place
from reddome.sim.objectives import drills_on, field_owner
from reddome.sim.state import distance, find_free_tile_near
from reddome.sim.types import Building, BuildingType, Point, Unit, opponent_of

if TYPE_CHECKING:
    from reddome.sim.simulation import Simulation

#: Свободные роверы идут на помощь, если враг подошёл к своему зданию ближе стольких клеток.
DEFEND_RADIUS = 6
#: Турель ставится не дальше стольких клеток от бура, который прикрывает.
TURRET_RADIUS = 2
#: Не больше стольких роверов в очереди ангаров.
ROVER_QUEUE = 2


def _step(kind: str, type_: str, where: str = "") -> BuildStep:
    return BuildStep(kind, type_, where)  # type: ignore[arg-type]


STRATEGIST_ORDER: tuple[BuildStep, ...] = (
    _step("unit", "drone"),
    _step("building", "oxy_gen"),
    _step("unit", "drone"),
    _step("building", "solar"),
    _step("building", "ice_drill", "own"),
    _step("building", "regolith"),
    _step("building", "hangar"),
    _step("building", "solar"),
    _step("building", "reactor"),
    _step("building", "oxy_gen"),
)
#: Центральное поле и турель у бура там занимает _contest_ice — не раньше bot.center_from_sec.


class BotStrategist(BotV0):
    build_order = STRATEGIST_ORDER
    #: True — занимать ледяные поля, не дожидаясь center_from_sec и enemy_field_from_sec («Адаптивный»).
    early_fields = False

    # --- Поля льда --------------------------------------------------------------

    def ice_field(self, sim: Simulation, which: str) -> list[Point]:
        """Поле по роли для этой стороны: own — своё, center — центральное, enemy — у базы соперника."""
        fields = sim.state.map.ice_fields
        if not fields:
            return []
        own, enemy = (fields[0], fields[-1]) if self.side == "player" else (fields[-1], fields[0])
        if which == "own":
            return own
        if which == "enemy":
            return enemy
        return fields[len(fields) // 2]

    def _has_site_on(self, sim: Simulation, field: list[Point]) -> bool:
        tiles = set(field)
        return any(b.side == self.side and b.type == "ice_drill" and Point(b.x, b.y) in tiles for b in sim.state.buildings)

    # --- Решения ------------------------------------------------------------------

    def think(self, sim: Simulation) -> None:
        super().think(sim)
        self._defend(sim)

    def _grow(self, sim: Simulation) -> None:
        state = sim.state
        colony = state.colonies[self.side]
        building_now = {b.type for b in state.buildings if b.side == self.side and not b.complete}
        # Энергия: реактор, если его нет, иначе солнечная панель.
        if colony.last_delta["energy"] < 0 and colony.resources["energy"] < 60 and not building_now & {"solar", "reactor"}:
            if not self._own_buildings(sim, "reactor") and self._try_build(sim, "reactor"):
                return
            if self._try_build(sim, "solar"):
                return
        if self._contest_ice(sim, building_now):
            return
        super()._grow(sim)

    def _contest_ice(self, sim: Simulation, building_now: set[str]) -> bool:
        """Бур на центральном поле, когда его там нет; после 5-й минуты — и на поле соперника."""
        if "ice_drill" in building_now:
            return False
        spec = self.spec(sim)
        for which in ("center", "enemy"):
            start_sec = spec.center_from_sec if which == "center" else spec.enemy_field_from_sec
            if not self.early_fields and sim.state.elapsed_ms < start_sec * 1000:
                continue
            field = self.ice_field(sim, which)
            if not field or self._has_site_on(sim, field):
                continue
            if field_owner(sim.state, field) == opponent_of(self.side):
                continue  # Сначала волна выбьет бур соперника (wave_target).
            if self._try_build(sim, "ice_drill", which):
                return True
        if self._needs_turret(sim) and "turret" not in building_now:
            return self._try_build(sim, "turret", "center")
        return False

    def _needs_turret(self, sim: Simulation) -> bool:
        drill = self._drill_on(sim, "center")
        if drill is None:
            return False
        return not any(
            b.side == self.side and b.type == "turret" and distance(b.x, b.y, drill.x, drill.y) <= TURRET_RADIUS + 0.5
            for b in sim.state.buildings
        )

    def _drill_on(self, sim: Simulation, which: str) -> Building | None:
        tiles = set(self.ice_field(sim, which))
        return next(
            (b for b in sim.state.buildings if b.side == self.side and b.type == "ice_drill" and Point(b.x, b.y) in tiles),
            None,
        )

    def train_rover(self, sim: Simulation) -> None:
        """Охранные и ракетные роверы вперемешку: ракетный — когда их меньше половины охранных."""
        rockets = len(self._own_units(sim, "rocket_rover")) + self._queued(sim, "rocket_rover")
        guards = len(self._own_units(sim, "guard_rover")) + self._queued(sim, "guard_rover")
        if rockets * 2 < guards and sim.train(self.side, "rocket_rover").ok:
            return
        sim.train(self.side, "guard_rover")

    def _queued_rovers(self, sim: Simulation) -> int:
        return self._queued(sim, "guard_rover") + self._queued(sim, "rocket_rover")

    def fighters(self, sim: Simulation) -> list[Unit]:
        return [u for u in sim.state.units if u.side == self.side and sim.is_fighter(u)]

    def _defend(self, sim: Simulation) -> None:
        """Свободные роверы идут к своему зданию, у которого враг."""
        state = sim.state
        enemy = opponent_of(self.side)
        idle = [u for u in self.fighters(sim) if u.task == "idle"]
        if not idle:
            return
        for building in sorted((b for b in state.buildings if b.side == self.side), key=lambda b: b.id):
            threat = next(
                (u for u in state.units if u.side == enemy and sim.is_fighter(u)
                 and distance(u.x, u.y, building.x, building.y) <= DEFEND_RADIUS),
                None,
            )
            if threat is not None:
                sim.attack_move(self.side, [u.id for u in idle], Point(round(threat.x), round(threat.y)))
                return

    # --- Волны --------------------------------------------------------------------

    def _ready_fighters(self, sim: Simulation) -> list[Unit]:
        return [u for u in self.fighters(sim) if u.task == "idle"]

    def _send_waves(self, sim: Simulation) -> None:
        state, bot = sim.state, self.spec(sim)
        if self.next_wave_ms is None:
            self.next_wave_ms = int(bot.first_wave_sec * 1000)
        # Соперник давно держит ледяные поля — бьём сразу, не дожидаясь таймера волны.
        urgent = sim.mission.goal == "hold_ice" and state.ice_hold_sols[opponent_of(self.side)] >= bot.rush_hold_sols
        if state.elapsed_ms < self.next_wave_ms and not urgent:
            return
        size = bot.wave_size(self.waves_sent)
        ready = self._ready_fighters(sim)
        if len(ready) < size:
            return
        target = self.wave_target(sim)
        if target is None:
            return
        wave = sorted(ready, key=lambda u: (-u.hp, u.id))[:size]
        sim.attack_move(self.side, [u.id for u in wave], target)
        self.waves.append((state.elapsed_ms, len(wave)))
        self.waves_sent += 1
        self.next_wave_ms = max(self.next_wave_ms, state.elapsed_ms) + int(bot.wave_interval_sec * 1000)

    def wave_target(self, sim: Simulation) -> Point | None:
        """Бур соперника на ледяном поле, ближайший к базе бота; если таких нет — как у v0."""
        state = sim.state
        base = state.map.bases[self.side]
        enemy = opponent_of(self.side)
        ice = {p for field in state.map.ice_fields for p in field}
        drills = [b for b in state.buildings if b.side == enemy and b.type == "ice_drill" and Point(b.x, b.y) in ice]
        if drills:
            target = min(drills, key=lambda b: (distance(base.x, base.y, b.x, b.y), b.id))
            return find_free_tile_near(state, Point(target.x, target.y), 2)
        return super().wave_target(sim)

    # --- Места для зданий -------------------------------------------------------------

    def find_spot(self, sim: Simulation, type: BuildingType, where: str = "") -> Point | None:
        state, balance = sim.state, sim.balance
        base = state.map.bases[self.side]
        if type == "ice_drill" and where:
            field = self.ice_field(sim, where)
            for p in sorted(field, key=lambda p: (distance(base.x, base.y, p.x, p.y), p.y, p.x)):
                if can_place(state, balance, self.side, type, p.x, p.y).ok:
                    return p
            return None
        if type == "turret" and where:
            anchor = self._turret_anchor(sim, where)
            if anchor is None:
                return None
            candidates = [
                Point(anchor.x + dx, anchor.y + dy)
                for dy in range(-TURRET_RADIUS, TURRET_RADIUS + 1)
                for dx in range(-TURRET_RADIUS, TURRET_RADIUS + 1)
                if (dx or dy)
            ]
            # Турель — со стороны соперника: ближе к его базе.
            enemy_base = state.map.bases[opponent_of(self.side)]
            candidates.sort(key=lambda p: (distance(enemy_base.x, enemy_base.y, p.x, p.y), p.y, p.x))
            for p in candidates:
                if self._next_to_building(sim, p):
                    continue
                if can_place(state, balance, self.side, type, p.x, p.y).ok:
                    return p
            return None
        return super().find_spot(sim, type, where)

    def _turret_anchor(self, sim: Simulation, where: str) -> Point | None:
        if where == "base":
            base = sim.state.map.bases[self.side]
            enemy_base = sim.state.map.bases[opponent_of(self.side)]
            # Три клетки от купола в сторону соперника.
            dx, dy = enemy_base.x - base.x, enemy_base.y - base.y
            norm = max(1.0, (dx * dx + dy * dy) ** 0.5)
            return Point(round(base.x + dx / norm * 3), round(base.y + dy / norm * 3))
        drill = self._drill_on(sim, where)
        return Point(drill.x, drill.y) if drill is not None else None

    def _next_to_building(self, sim: Simulation, p: Point) -> bool:
        return any(max(abs(b.x - p.x), abs(b.y - p.y)) <= 1 for b in sim.state.buildings)

    # --- Счёт полей (для отчётов и отладки) ------------------------------------------

    def drills_by_field(self, sim: Simulation) -> list[int]:
        return [drills_on(sim.state, field, self.side) for field in sim.state.map.ice_fields]
