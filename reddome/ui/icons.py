"""Процедурные иконки интерфейса (B4): ресурсы, здания, юниты и команды.

Рисуются один раз в SS раз крупнее, уменьшаются smoothscale и хранятся в кэше по (имя, размер).
Иконки зданий и юнитов — уменьшенные спрайты из render/art.py, поэтому совпадают с картой.
"""

from __future__ import annotations

import math
from collections.abc import Callable

import pygame

from reddome.render import art
from reddome.render.draw import SS, bevel_polygon, canvas, radial_disc, shrink
from reddome.sim.types import BUILDING_TYPES, UNIT_TYPES
from reddome.ui import theme
from reddome.ui.theme import Color, mix

_cache: dict[tuple[str, int], pygame.Surface] = {}


def icon(name: str, size: int) -> pygame.Surface:
    key = (name, size)
    image = _cache.get(key)
    if image is None:
        image = _paint(name, size)
        _cache[key] = image
    return image


def _paint(name: str, size: int) -> pygame.Surface:
    if name in BUILDING_TYPES:
        sprite = art.building_sprite(name, "player", True)
        return pygame.transform.smoothscale(sprite, (size, size))
    if name in UNIT_TYPES:
        if name == "drone":
            sprite = art.drone_sprite("player", False)
        else:
            sprite = art.rover_chassis("player")
            sprite.blit(art.rover_turret("player"), (0, 0))
        sprite = pygame.transform.rotozoom(sprite, 45, 1.0)
        return pygame.transform.smoothscale(sprite, (size, size))
    painter = PAINTERS.get(name)
    if painter is None:
        raise KeyError(f"Неизвестная иконка: {name}")
    surface = canvas(size, size)
    painter(surface, size * SS)
    return shrink(surface, size, size)


# --- Ресурсы ---------------------------------------------------------------------


def _energy(s: pygame.Surface, n: float) -> None:
    bolt = [(0.58, 0.04), (0.2, 0.56), (0.46, 0.56), (0.36, 0.96), (0.8, 0.4), (0.53, 0.4), (0.66, 0.04)]
    bevel_polygon(s, [(x * n, y * n) for x, y in bolt], theme.ENERGY, width=max(1, int(n * 0.04)))


def _water(s: pygame.Surface, n: float) -> None:
    c = (n * 0.5, n * 0.62)
    r = n * 0.3
    pygame.draw.polygon(s, theme.WATER, [(n * 0.5, n * 0.06), (c[0] - r * 0.92, c[1] - r * 0.3), (c[0] + r * 0.92, c[1] - r * 0.3)])
    radial_disc(s, c, r, mix(theme.WATER, (255, 255, 255), 0.55), mix(theme.WATER, (0, 0, 40), 0.25))


def _oxygen(s: pygame.Surface, n: float) -> None:
    for cx, cy, r in ((0.4, 0.58, 0.3), (0.72, 0.3, 0.17), (0.78, 0.72, 0.11)):
        radial_disc(s, (cx * n, cy * n), r * n, mix(theme.OXYGEN, (255, 255, 255), 0.6), mix(theme.OXYGEN, (0, 30, 30), 0.3))
        pygame.draw.circle(s, mix(theme.OXYGEN, (255, 255, 255), 0.3), (cx * n, cy * n), r * n, max(1, int(n * 0.03)))


def _metal(s: pygame.Surface, n: float) -> None:
    top = [(0.22, 0.38), (0.78, 0.38), (0.92, 0.62), (0.08, 0.62)]
    bevel_polygon(s, [(x * n, y * n) for x, y in top], theme.METAL, width=max(1, int(n * 0.04)))
    pygame.draw.polygon(s, mix(theme.METAL, (0, 0, 0), 0.35), [(0.08 * n, 0.62 * n), (0.92 * n, 0.62 * n), (0.92 * n, 0.74 * n), (0.08 * n, 0.74 * n)])
    pygame.draw.line(s, (255, 255, 255), (0.3 * n, 0.44 * n), (0.6 * n, 0.44 * n), max(1, int(n * 0.04)))


def _colonists(s: pygame.Surface, n: float) -> None:
    color = theme.SAND
    radial_disc(s, (0.5 * n, 0.3 * n), 0.18 * n, mix(color, (255, 255, 255), 0.4), mix(color, (0, 0, 0), 0.2))
    body = pygame.Rect(0.18 * n, 0.52 * n, 0.64 * n, 0.5 * n)
    pygame.draw.ellipse(s, color, body)
    pygame.draw.rect(s, (0, 0, 0, 0), (0, 0.9 * n, n, n))


def _army(s: pygame.Surface, n: float) -> None:
    shield = [(0.5, 0.06), (0.88, 0.2), (0.82, 0.62), (0.5, 0.94), (0.18, 0.62), (0.12, 0.2)]
    bevel_polygon(s, [(x * n, y * n) for x, y in shield], theme.TEAM_PLAYER, width=max(1, int(n * 0.04)))
    pygame.draw.line(s, theme.TEXT, (0.5 * n, 0.22 * n), (0.5 * n, 0.76 * n), max(1, int(n * 0.07)))
    pygame.draw.line(s, theme.TEXT, (0.3 * n, 0.42 * n), (0.7 * n, 0.42 * n), max(1, int(n * 0.07)))


# --- Команды ---------------------------------------------------------------------


def _w(n: float, k: float = 0.08) -> int:
    return max(1, int(n * k))


def _stop(s: pygame.Surface, n: float) -> None:
    pts = [(0.5 * n + math.cos(a) * 0.4 * n, 0.5 * n + math.sin(a) * 0.4 * n)
           for a in (math.pi / 8 + i * math.tau / 8 for i in range(8))]
    bevel_polygon(s, pts, (196, 52, 52), width=_w(n, 0.04))
    pygame.draw.rect(s, theme.TEXT, (0.26 * n, 0.44 * n, 0.48 * n, 0.12 * n))


def _gather(s: pygame.Surface, n: float) -> None:
    # Кирка: ручка и изогнутое лезвие.
    pygame.draw.line(s, (150, 104, 64), (0.22 * n, 0.86 * n), (0.62 * n, 0.3 * n), _w(n, 0.1))
    blade = pygame.Rect(0.2 * n, 0.08 * n, 0.72 * n, 0.5 * n)
    pygame.draw.arc(s, theme.METAL, blade, math.radians(20), math.radians(160), _w(n, 0.12))
    pygame.draw.circle(s, theme.ORE, (0.78 * n, 0.76 * n), 0.13 * n)
    pygame.draw.circle(s, (230, 236, 248), (0.74 * n, 0.72 * n), 0.04 * n)


def _build(s: pygame.Surface, n: float) -> None:
    # Молоток.
    pygame.draw.line(s, (150, 104, 64), (0.24 * n, 0.86 * n), (0.6 * n, 0.4 * n), _w(n, 0.11))
    head = [(0.36, 0.26), (0.66, 0.04), (0.92, 0.34), (0.62, 0.56)]
    bevel_polygon(s, [(x * n, y * n) for x, y in head], theme.METAL, width=_w(n, 0.04))


def _repair(s: pygame.Surface, n: float) -> None:
    # Гаечный ключ.
    pygame.draw.line(s, theme.METAL, (0.22 * n, 0.8 * n), (0.6 * n, 0.42 * n), _w(n, 0.14))
    pygame.draw.circle(s, theme.METAL, (0.66 * n, 0.34 * n), 0.22 * n)
    pygame.draw.circle(s, (0, 0, 0, 0), (0.78 * n, 0.22 * n), 0.12 * n)
    pygame.draw.circle(s, theme.SUCCESS, (0.24 * n, 0.78 * n), 0.08 * n)


def _return(s: pygame.Surface, n: float) -> None:
    # Купол и стрелка к нему.
    radial_disc(s, (0.62 * n, 0.66 * n), 0.28 * n, (225, 248, 255), mix(theme.GLASS, (10, 30, 60), 0.5))
    pygame.draw.rect(s, (0, 0, 0, 0), (0, 0.72 * n, n, n))
    pygame.draw.line(s, theme.HULL_PLAYER, (0.3 * n, 0.72 * n), (0.94 * n, 0.72 * n), _w(n, 0.06))
    pygame.draw.line(s, theme.SUCCESS, (0.12 * n, 0.12 * n), (0.42 * n, 0.42 * n), _w(n, 0.09))
    pygame.draw.polygon(s, theme.SUCCESS, [(0.5 * n, 0.5 * n), (0.24 * n, 0.46 * n), (0.46 * n, 0.24 * n)])


def _attack(s: pygame.Surface, n: float) -> None:
    c = (0.5 * n, 0.5 * n)
    pygame.draw.circle(s, theme.ALARM, c, 0.34 * n, _w(n, 0.07))
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        pygame.draw.line(s, theme.ALARM, (c[0] + dx * 0.16 * n, c[1] + dy * 0.16 * n),
                         (c[0] + dx * 0.46 * n, c[1] + dy * 0.46 * n), _w(n, 0.07))
    pygame.draw.circle(s, theme.TEXT, c, 0.05 * n)


def _cancel(s: pygame.Surface, n: float) -> None:
    for a, b in (((0.2, 0.2), (0.8, 0.8)), ((0.8, 0.2), (0.2, 0.8))):
        pygame.draw.line(s, theme.ALARM, (a[0] * n, a[1] * n), (b[0] * n, b[1] * n), _w(n, 0.13))


def _back(s: pygame.Surface, n: float) -> None:
    pygame.draw.line(s, theme.TEXT_QUIET, (0.3 * n, 0.5 * n), (0.84 * n, 0.5 * n), _w(n, 0.1))
    pygame.draw.polygon(s, theme.TEXT_QUIET, [(0.12 * n, 0.5 * n), (0.42 * n, 0.24 * n), (0.42 * n, 0.76 * n)])


def _rally(s: pygame.Surface, n: float) -> None:
    pygame.draw.line(s, theme.TEXT, (0.3 * n, 0.08 * n), (0.3 * n, 0.92 * n), _w(n, 0.07))
    pygame.draw.polygon(s, theme.TEAM_PLAYER, [(0.32 * n, 0.1 * n), (0.86 * n, 0.26 * n), (0.32 * n, 0.44 * n)])


def _move(s: pygame.Surface, n: float) -> None:
    pygame.draw.line(s, theme.SUCCESS, (0.16 * n, 0.84 * n), (0.66 * n, 0.34 * n), _w(n, 0.1))
    pygame.draw.polygon(s, theme.SUCCESS, [(0.86 * n, 0.14 * n), (0.48 * n, 0.24 * n), (0.76 * n, 0.52 * n)])


def _lock(s: pygame.Surface, n: float) -> None:
    """Замок закрытой миссии: дужка и корпус с замочной скважиной."""
    pygame.draw.arc(s, theme.TEXT_QUIET, pygame.Rect(0.28 * n, 0.1 * n, 0.44 * n, 0.5 * n), 0, math.pi, _w(n, 0.09))
    for x in (0.3, 0.7):
        pygame.draw.line(s, theme.TEXT_QUIET, (x * n, 0.35 * n), (x * n, 0.48 * n), _w(n, 0.09))
    body = pygame.Rect(0.18 * n, 0.44 * n, 0.64 * n, 0.48 * n)
    pygame.draw.rect(s, theme.SAND, body, border_radius=int(0.08 * n))
    pygame.draw.rect(s, theme.PANEL_EDGE, body, _w(n, 0.04), border_radius=int(0.08 * n))
    pygame.draw.circle(s, theme.PANEL, (0.5 * n, 0.62 * n), 0.07 * n)
    pygame.draw.line(s, theme.PANEL, (0.5 * n, 0.64 * n), (0.5 * n, 0.8 * n), _w(n, 0.06))


def _sol(s: pygame.Surface, n: float) -> None:
    radial_disc(s, (0.5 * n, 0.5 * n), 0.34 * n, (255, 236, 190), (255, 150, 60), light=(0, 0))
    for i in range(8):
        a = i / 8 * math.tau
        pygame.draw.line(s, (255, 190, 110), (0.5 * n + math.cos(a) * 0.4 * n, 0.5 * n + math.sin(a) * 0.4 * n),
                         (0.5 * n + math.cos(a) * 0.48 * n, 0.5 * n + math.sin(a) * 0.48 * n), _w(n, 0.05))


# --- Жесты (W3-12): кисть ладонью к зрителю, без эмодзи — их нет в шрифтах ---------------

SKIN = theme.SAND
SKIN_DARK = mix(theme.SAND, (60, 30, 20), 0.6)
#: Пальцы слева направо: указательный, средний, безымянный, мизинец — x основания и высота кончика.
FINGER_X = (0.33, 0.46, 0.59, 0.72)
FINGER_TOP = (0.14, 0.07, 0.11, 0.21)


def _capsule(s: pygame.Surface, a: tuple[float, float], b: tuple[float, float], width: float, color: Color) -> None:
    pygame.draw.line(s, color, a, b, max(1, int(width)))
    pygame.draw.circle(s, color, a, width / 2)
    pygame.draw.circle(s, color, b, width / 2)


def _hand(s: pygame.Surface, n: float, fingers: tuple[bool, bool, bool, bool], thumb_out: bool,
          spread: tuple[float, float, float, float] = (0, 0, 0, 0)) -> None:
    """Кисть: какие пальцы вытянуты, отведён ли большой палец, наклон пальцев (доли n)."""
    w, o = n * 0.13, n * 0.045

    def shapes(color: Color, grow: float) -> None:
        for x, top, up, dx in zip(FINGER_X, FINGER_TOP, fingers, spread):
            _capsule(s, (x * n, 0.52 * n), ((x + dx) * n, (top if up else 0.40) * n), w + grow, color)
        rect = pygame.Rect(0.25 * n - grow / 2, 0.44 * n - grow / 2, 0.55 * n + grow, 0.47 * n + grow)
        pygame.draw.rect(s, color, rect, border_radius=int(0.15 * n + grow / 2))
        if thumb_out:
            _capsule(s, (0.31 * n, 0.74 * n), (0.10 * n, 0.50 * n), w + grow, color)

    shapes(SKIN_DARK, o * 2)
    shapes(SKIN, 0)
    if not thumb_out:  # прижатый большой палец поперёк ладони
        _capsule(s, (0.31 * n, 0.74 * n), (0.55 * n, 0.64 * n), w + o * 1.6, SKIN_DARK)
        _capsule(s, (0.31 * n, 0.74 * n), (0.55 * n, 0.64 * n), w, SKIN)


def _gesture_palm(s: pygame.Surface, n: float) -> None:
    _hand(s, n, (True, True, True, True), True, (-0.04, -0.01, 0.01, 0.05))


def _gesture_fist(s: pygame.Surface, n: float) -> None:
    _hand(s, n, (False, False, False, False), False)


def _gesture_pointing(s: pygame.Surface, n: float) -> None:
    _hand(s, n, (True, False, False, False), False)


def _gesture_victory(s: pygame.Surface, n: float) -> None:
    _hand(s, n, (True, True, False, False), False, (-0.08, 0.07, 0, 0))


def _gesture_ily(s: pygame.Surface, n: float) -> None:
    _hand(s, n, (True, False, False, True), True, (-0.02, 0, 0, 0.04))


def _gesture_thumb_up(s: pygame.Surface, n: float) -> None:
    w, o = n * 0.14, n * 0.045

    def shapes(color: Color, grow: float) -> None:
        rect = pygame.Rect(0.26 * n - grow / 2, 0.44 * n - grow / 2, 0.52 * n + grow, 0.46 * n + grow)
        pygame.draw.rect(s, color, rect, border_radius=int(0.15 * n + grow / 2))
        _capsule(s, (0.37 * n, 0.52 * n), (0.37 * n, 0.10 * n), w + grow, color)

    shapes(SKIN_DARK, o * 2)
    shapes(SKIN, 0)
    for y in (0.56, 0.67, 0.78):  # сжатые пальцы
        pygame.draw.line(s, SKIN_DARK, (0.52 * n, y * n), (0.76 * n, y * n), max(1, int(n * 0.03)))


def _gesture_thumb_down(s: pygame.Surface, n: float) -> None:
    layer = pygame.Surface(s.get_size(), pygame.SRCALPHA)
    _gesture_thumb_up(layer, n)
    s.blit(pygame.transform.flip(layer, False, True), (0, 0))


def _camera(s: pygame.Surface, n: float, color: Color) -> None:
    body = pygame.Rect(0.1 * n, 0.3 * n, 0.62 * n, 0.46 * n)
    pygame.draw.rect(s, color, body, border_radius=int(0.08 * n))
    pygame.draw.polygon(s, color, [(0.72 * n, 0.45 * n), (0.92 * n, 0.32 * n), (0.92 * n, 0.74 * n), (0.72 * n, 0.61 * n)])
    pygame.draw.circle(s, (0, 0, 0, 0), (0.41 * n, 0.53 * n), 0.13 * n)
    pygame.draw.circle(s, color, (0.41 * n, 0.53 * n), 0.07 * n)


def _camera_on(s: pygame.Surface, n: float) -> None:
    _camera(s, n, theme.SUCCESS)


def _camera_off(s: pygame.Surface, n: float) -> None:
    _camera(s, n, (130, 136, 146))
    pygame.draw.line(s, theme.ALARM, (0.12 * n, 0.88 * n), (0.88 * n, 0.12 * n), _w(n, 0.09))


def _camera_wait(s: pygame.Surface, n: float) -> None:
    _camera(s, n, theme.WARNING)


#: Иконка для жеста mediapipe: icon(GESTURE_ICONS[name], size).
GESTURE_ICONS = {
    "Open_Palm": "gesture_palm",
    "Closed_Fist": "gesture_fist",
    "Pointing_Up": "gesture_pointing",
    "Thumb_Up": "gesture_thumb_up",
    "Thumb_Down": "gesture_thumb_down",
    "Victory": "gesture_victory",
    "ILoveYou": "gesture_ily",
}


PAINTERS: dict[str, Callable[[pygame.Surface, float], None]] = {
    "gesture_palm": _gesture_palm,
    "gesture_fist": _gesture_fist,
    "gesture_pointing": _gesture_pointing,
    "gesture_victory": _gesture_victory,
    "gesture_ily": _gesture_ily,
    "gesture_thumb_up": _gesture_thumb_up,
    "gesture_thumb_down": _gesture_thumb_down,
    "camera_on": _camera_on,
    "camera_off": _camera_off,
    "camera_wait": _camera_wait,
    "energy": _energy,
    "water": _water,
    "oxygen": _oxygen,
    "metal": _metal,
    "colonists": _colonists,
    "army": _army,
    "stop": _stop,
    "gather": _gather,
    "build": _build,
    "repair": _repair,
    "return": _return,
    "attack": _attack,
    "cancel": _cancel,
    "back": _back,
    "rally": _rally,
    "move": _move,
    "sol": _sol,
    "lock": _lock,
}

RESOURCE_COLORS: dict[str, Color] = {
    "energy": theme.ENERGY,
    "water": theme.WATER,
    "oxygen": theme.OXYGEN,
    "metal": theme.METAL,
}


def prerender_jobs() -> list[Callable[[], object]]:
    """Иконки, которые нужны в первом кадре игры, — для полосы загрузки."""
    names = [*PAINTERS, *BUILDING_TYPES, *UNIT_TYPES]
    return [lambda name=name, size=size: icon(name, size) for name in names for size in (20, 36)]
