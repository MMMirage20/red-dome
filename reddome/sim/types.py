"""Типы состояния игры."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Side = Literal["player", "vector"]
SIDES: tuple[Side, ...] = ("player", "vector")

#: Уровни сложности партии (этап 2). Множители каждого — в balance.json → difficulty.
Difficulty = Literal["easy", "normal", "hard"]
DIFFICULTIES: tuple[Difficulty, ...] = ("easy", "normal", "hard")

ResourceKey = Literal["energy", "water", "oxygen", "metal"]
RESOURCE_KEYS: tuple[ResourceKey, ...] = ("energy", "water", "oxygen", "metal")

BuildingType = Literal[
    "dome", "solar", "ice_drill", "oxy_gen", "regolith", "hangar", "turret", "reactor", "great_dome"
]
BUILDING_TYPES: tuple[BuildingType, ...] = (
    "dome", "solar", "ice_drill", "oxy_gen", "regolith", "hangar", "turret", "reactor", "great_dome"
)

UnitType = Literal["drone", "guard_rover", "rocket_rover"]
UNIT_TYPES: tuple[UnitType, ...] = ("drone", "guard_rover", "rocket_rover")

#: Номер миссии кампании (этап 3): 1 «Высадка», 2 «Война за лёд», 3 «Последний купол».
MISSIONS: tuple[int, ...] = (1, 2, 3)

TileKind = Literal["ground", "ice", "ore", "rock"]

#: ice_held — удержаны ледяные поля (миссия 2), great_dome — достроен Большой купол (миссия 3).
OutcomeReason = Literal["dome_destroyed", "oxygen", "ice_held", "great_dome"]

#: Задачи юнита. Рабочие состояния дрона описаны в sim/workers.py, боевые — в sim/combat.py.
UnitTask = Literal[
    "idle",
    "moving",
    "to_resource",
    "gathering",
    "waiting",
    "returning",
    "to_site",
    "building",
    "repairing",
    "attacking",
    "attack_move",
]

#: Задачи, после которых дрон сам возвращается к добыче.
GATHER_TASKS: tuple[UnitTask, ...] = ("to_resource", "gathering", "waiting", "returning")

EventKind = Literal[
    "dropoff",
    "shot",
    "unit_destroyed",
    "building_destroyed",
    "construction_complete",
    "unit_trained",
    "deposit_depleted",
    "panel_dusted",
    "meteor_warning",
    "meteor_impact",
    "storm_warning",
    "storm_start",
    "storm_end",
    "flare_warning",
    "flare_start",
    "flare_end",
]


def opponent_of(side: Side) -> Side:
    return "vector" if side == "player" else "player"


@dataclass(frozen=True)
class Point:
    x: int
    y: int


@dataclass
class GameMap:
    width: int
    height: int
    #: Клетки построчно: индекс = y * width + x.
    tiles: list[TileKind]
    bases: dict[Side, Point]
    #: Клетки каждого рудного поля: сначала поля игрока, потом зеркальные поля ВЕКТОРа.
    ore_fields: list[list[Point]] = field(default_factory=list)
    #: Ледяные поля (этап 3): связные группы клеток льда, от ближнего к базе игрока до ближнего к ВЕКТОРу.
    ice_fields: list[list[Point]] = field(default_factory=list)


@dataclass
class QueueItem:
    type: UnitType
    remaining_ms: int


@dataclass
class Building:
    id: int
    side: Side
    type: BuildingType
    x: int
    y: int
    hp: float
    #: False — здание отключено из-за нехватки энергии или воды.
    powered: bool = True
    #: False — стройплощадка: ничего не производит, не даёт лимит армии и не тратит энергию.
    complete: bool = True
    #: Прогресс стройки от 0 до 1.
    build_progress: float = 1.0
    #: Очередь сборки юнитов (купол и ангар).
    queue: list[QueueItem] = field(default_factory=list)
    #: Точка сбора новых юнитов.
    rally: Point | None = None
    #: Сколько ещё мс солнечная панель засыпана пылью вихря (W3-15); 0 — чистая.
    dust_ms: int = 0
    #: Турель (этап 3): цель, таймер выстрела для эффектов и угол ствола.
    target_id: int | None = None
    fire_ms: int = 0
    aim: float = 0.0


@dataclass
class Unit:
    id: int
    side: Side
    type: UnitType
    #: Позиция в клетках, во время движения дробная.
    x: float
    y: float
    hp: float
    #: Оставшиеся точки пути без текущей клетки.
    path: list[Point] = field(default_factory=list)
    task: UnitTask = "idle"
    #: Цель задачи: id поля руды, здания или вражеского юнита — зависит от task.
    target_id: int | None = None
    #: Сколько металла несёт дрон.
    carry: int = 0
    #: Таймер текущей работы (добыча), мс.
    work_ms: int = 0
    #: Поле, к которому дрон возвращается после сдачи груза.
    home_deposit: int | None = None
    #: Вернуться к добыче после стройки или ремонта.
    resume_gathering: bool = False
    #: Точка, к которой идёт атака с движением.
    attack_point: Point | None = None
    #: Через сколько мс можно снова пересчитать путь к движущейся цели.
    repath_ms: int = 0
    #: Таймер для событий выстрела (для эффектов), мс.
    fire_ms: int = 0
    #: Направление корпуса и турели, радианы (для отрисовки).
    facing: float = 0.0
    aim: float = 0.0


@dataclass
class Deposit:
    id: int
    tiles: list[Point]
    amount: int
    initial: int


def empty_resources() -> dict[ResourceKey, int]:
    return dict.fromkeys(RESOURCE_KEYS, 0)


@dataclass
class DustDevil:
    """Пылевой вихрь (ФТ-18): идёт по прямой к точке маршрута, дойдя — выбирает следующую."""

    x: float
    y: float
    target: Point
    #: Сколько точек маршрута уже пройдено: от него и seed зависит следующая точка.
    leg: int = 0
    #: Сколько мс вихрь уже живёт.
    age_ms: int = 0
    #: Номер вихря за партию: у каждого свой маршрут.
    number: int = 0


@dataclass
class Meteor:
    """Метеорит (миссия 3): метка на земле появляется заранее, удар — в impact_ms."""

    x: int
    y: int
    impact_ms: int
    number: int


@dataclass
class Colony:
    side: Side
    resources: dict[ResourceKey, int]
    colonists: int
    #: Сколько солов подряд кислорода не хватило.
    oxygen_deficit_sols: int = 0
    #: Изменение ресурсов за последний сол — для HUD.
    last_delta: dict[ResourceKey, int] = field(default_factory=empty_resources)
    #: Металл в начале сола: он меняется добычей и тратами в течение сола, а не раз в сол.
    sol_start_metal: int = 0
    #: Солы в «зелёной зоне» — для очков (W3-10), считается в economy.apply_sol.
    green_sols: int = 0


@dataclass
class SideStats:
    """Счётчики для экрана итогов."""

    metal_mined: int = 0
    units_trained: int = 0
    units_lost: int = 0
    buildings_built: int = 0
    enemy_units_killed: int = 0
    enemy_buildings_destroyed: int = 0


@dataclass(frozen=True)
class Outcome:
    winner: Side
    reason: OutcomeReason


@dataclass
class GameState:
    seed: int
    map: GameMap
    colonies: dict[Side, Colony]
    buildings: list[Building] = field(default_factory=list)
    units: list[Unit] = field(default_factory=list)
    deposits: list[Deposit] = field(default_factory=list)
    stats: dict[Side, SideStats] = field(default_factory=lambda: {side: SideStats() for side in SIDES})
    tick: int = 0
    elapsed_ms: int = 0
    sol: int = 0
    sol_elapsed_ms: int = 0
    next_id: int = 1
    outcome: Outcome | None = None
    difficulty: Difficulty = "normal"
    #: Текущий пылевой вихрь (не больше одного) и сколько их уже было.
    dust_devil: DustDevil | None = None
    dust_devils_spawned: int = 0
    #: Миссия кампании (этап 3).
    mission: int = 1
    #: Сколько солов подряд сторона держит нужное число ледяных полей (миссия 2).
    ice_hold_sols: dict[Side, int] = field(default_factory=lambda: dict.fromkeys(SIDES, 0))
    #: Метеориты с меткой на земле, ещё не упавшие, и сколько их уже назначено (миссия 3).
    meteors: list[Meteor] = field(default_factory=list)
    meteors_spawned: int = 0
    #: Идёт ли сейчас буря и вспышка: нужно, чтобы событие начала и конца пришло один раз.
    storm_active: bool = False
    flare_active: bool = False

@dataclass(frozen=True)
class SimEvent:
    """Событие для отрисовки и отчётов. Хранится вне GameState и на логику не влияет."""

    kind: EventKind
    side: Side
    x: float
    y: float
    #: Для выстрела — куда.
    tx: float = 0.0
    ty: float = 0.0
    #: Сколько металла сдано и т.п.
    value: int = 0
    #: Тип здания или юнита.
    subject: str = ""


@dataclass(frozen=True)
class CommandResult:
    ok: bool
    reason: str = ""
    id: int | None = None

    @staticmethod
    def success(id: int | None = None) -> CommandResult:
        return CommandResult(ok=True, id=id)

    @staticmethod
    def failure(reason: str) -> CommandResult:
        return CommandResult(ok=False, reason=reason)
