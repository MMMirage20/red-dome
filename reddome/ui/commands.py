"""Сетка команд 3×3 (как в Warcraft III): что можно сделать с выделенным и по какой клавише.

W, A, S, D заняты камерой, поэтому команды на других клавишах:
G — добывать, B — строить, E — чинить, X — стоп, R — вернуться, F — атака,
Q — собрать юнита, T — точка сбора. В меню стройки: P, I, O, E, H; Esc — назад.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pygame

from reddome.config.balance import Balance
from reddome.sim.types import Building, BuildingType, Unit
from reddome.ui import theme
from reddome.ui.theme import Color

BUILDING_NAMES: dict[str, str] = {
    "dome": "Командный купол",
    "solar": "Солнечная панель",
    "ice_drill": "Ледяной бур",
    "oxy_gen": "Генератор кислорода",
    "regolith": "Переработчик реголита",
    "hangar": "Ангар",
}
UNIT_NAMES: dict[str, str] = {"drone": "Дрон", "guard_rover": "Охранный ровер"}
DIFFICULTY_NAMES: dict[str, str] = {"easy": "Лёгкий", "normal": "Обычный", "hard": "Сложный"}


def difficulty_line(difficulty: str) -> str:
    """Строка для паузы и итогов: «Сложность: Обычный»."""
    return f"Сложность: {DIFFICULTY_NAMES[difficulty]}"
BUILD_KEYS: tuple[tuple[BuildingType, int, str], ...] = (
    ("solar", pygame.K_p, "P"),
    ("ice_drill", pygame.K_i, "I"),
    ("oxy_gen", pygame.K_o, "O"),
    ("regolith", pygame.K_e, "E"),
    ("hangar", pygame.K_h, "H"),
)
RESOURCE_NAMES = {"energy": "энергии", "water": "воды", "oxygen": "кислорода", "metal": "металла"}


@dataclass
class Command:
    slot: int
    key: int
    key_label: str
    icon: str
    title: str
    #: Что сделать: gather, return, repair, build_menu, back, place, stop, attack, train,
    #: cancel_build, cancel_train, rally.
    action: str
    arg: str = ""
    lines: list[tuple[str, Color]] = field(default_factory=list)
    cost: int | None = None
    enabled: bool = True


def building_lines(balance: Balance, type: str) -> list[tuple[str, Color]]:
    """Что даёт здание за сол — из balance.json, без своих чисел."""
    spec = balance.buildings[type]
    lines: list[tuple[str, Color]] = []
    effects = []
    for key in ("energy", "water", "oxygen"):
        value = getattr(spec, key)
        if value:
            effects.append((f"{value:+d} {RESOURCE_NAMES[key]}", theme.SUCCESS if value > 0 else theme.ALARM))
    if effects:
        lines.append(("За сол: " + ", ".join(text for text, _ in effects), theme.TEXT_QUIET))
    if spec.supply:
        lines.append((f"+{spec.supply} к лимиту армии", theme.TEXT_QUIET))
    if type == "regolith":
        bonus = round(balance.workers.refinery_bonus * 100)
        lines.append((f"Пункт сдачи руды: +{bonus} % к грузу", theme.SUCCESS))
    if type == "hangar":
        lines.append(("Собирает охранных роверов", theme.TEXT_QUIET))
    if spec.needs == "ice":
        lines.append(("Ставится только на лёд", theme.WARNING))
    elif spec.needs == "ore":
        lines.append(("Ставится только на рудный выход", theme.WARNING))
    if spec.build_time_sec:
        lines.append((f"Стройка {spec.build_time_sec:g} с одним дроном", theme.TEXT_QUIET))
    return lines


def unit_lines(balance: Balance, type: str) -> list[tuple[str, Color]]:
    spec = balance.units[type]
    if type == "drone":
        lines = [("Добывает руду, строит и чинит", theme.TEXT_QUIET),
                 (f"Груз {balance.workers.carry} металла за рейс", theme.TEXT_QUIET)]
    else:
        lines = [(f"Урон {spec.dps:g}/с, дальность {spec.range:g}", theme.TEXT_QUIET)]
    lines.append((f"Сборка {spec.build_time_sec:g} с · лимит армии {spec.supply}", theme.TEXT_QUIET))
    return lines


def commands_for(balance: Balance, metal: int, units: list[Unit], building: Building | None,
                 menu: str) -> list[Command]:
    """Команды для выделенных юнитов игрока или его здания."""
    if building is not None:
        return _building_commands(balance, metal, building)
    drones = [u for u in units if u.type == "drone"]
    fighters = [u for u in units if balance.units[u.type].dps > 0]
    if not units:
        return []
    if menu == "build" and drones:
        commands = []
        for slot, (type_, key, label) in enumerate(BUILD_KEYS):
            cost = balance.buildings[type_].cost
            commands.append(Command(slot, key, label, type_, BUILDING_NAMES[type_], "place", type_,
                                    building_lines(balance, type_), cost, metal >= cost))
        commands.append(Command(8, pygame.K_ESCAPE, "Esc", "back", "Назад", "back",
                                lines=[("Вернуться к командам дрона", theme.TEXT_QUIET)]))
        return commands
    commands = [Command(4, pygame.K_x, "X", "stop", "Стоп", "stop", lines=[("Прекратить текущий приказ", theme.TEXT_QUIET)])]
    if drones:
        commands += [
            Command(0, pygame.K_g, "G", "gather", "Добывать", "gather",
                    lines=[("Щёлкните по рудному полю", theme.TEXT_QUIET),
                           ("Дрон сам носит руду на базу", theme.TEXT_QUIET)]),
            Command(1, pygame.K_r, "R", "return", "Вернуть груз", "return",
                    lines=[("Отнести руду в купол или переработчик", theme.TEXT_QUIET)]),
            Command(2, pygame.K_e, "E", "repair", "Чинить", "repair",
                    lines=[("Щёлкните по своему зданию", theme.TEXT_QUIET),
                           (f"{balance.workers.repair_metal_per_100_hp:g} металла за 100 HP", theme.TEXT_QUIET)]),
            Command(3, pygame.K_b, "B", "build", "Строить", "build_menu",
                    lines=[("Открыть список зданий", theme.TEXT_QUIET)]),
        ]
    if fighters:
        commands.append(Command(5 if drones else 0, pygame.K_f, "F", "attack", "Атаковать", "attack",
                                lines=[("Щёлкните по врагу — атака цели", theme.TEXT_QUIET),
                                       ("По земле — атака с движением", theme.TEXT_QUIET)]))
        if not drones:
            commands.append(Command(1, pygame.K_r, "R", "return", "Отступить", "return",
                                    lines=[("Отойти к командному куполу", theme.TEXT_QUIET)]))
    return commands


def _building_commands(balance: Balance, metal: int, building: Building) -> list[Command]:
    if not building.complete:
        refund = round(balance.buildings[building.type].cost * balance.construction.refund_ratio)
        return [Command(8, pygame.K_x, "X", "cancel", "Отменить стройку", "cancel_build",
                        lines=[(f"Вернётся {refund} металла", theme.TEXT_QUIET)])]
    produces = {"dome": "drone", "hangar": "guard_rover"}.get(building.type)
    if produces is None:
        return []
    cost = balance.units[produces].cost
    commands = [
        Command(0, pygame.K_q, "Q", produces, f"Собрать: {UNIT_NAMES[produces].lower()}", "train", produces,
                unit_lines(balance, produces), cost, metal >= cost),
        Command(2, pygame.K_t, "T", "rally", "Точка сбора", "rally",
                lines=[("Куда пойдут новые юниты", theme.TEXT_QUIET),
                       ("Точка на руде — дроны сразу добывают", theme.TEXT_QUIET)]),
    ]
    if building.queue:
        commands.append(Command(8, pygame.K_x, "X", "cancel", "Отменить сборку", "cancel_train",
                                lines=[("Последний в очереди, металл вернётся", theme.TEXT_QUIET)]))
    return commands
