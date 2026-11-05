"""Процедурные спрайты зданий и юнитов (B3).

Корпус — в общей палитре (белёсый металл у людей, графит у ВЕКТОРа), цвет команды — только акцентом:
полосы, огни, кольцо. Рисуем в SS раз крупнее и уменьшаем smoothscale.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pygame

from reddome.render.draw import SS, bevel_polygon, canvas, radial_disc, shrink, vertical_gradient_rect
from reddome.ui import theme
from reddome.ui.theme import Color, mix

#: Размеры спрайтов в пикселях экрана (клетка — 32 px).
BUILDING_SIZE = 44
DOME_SIZE = 78
DRONE_SIZE = 26
ROVER_SIZE = 34


@dataclass(frozen=True)
class Light:
    """Огонь здания: смещение от центра клетки в пикселях, радиус свечения и цвет."""

    dx: float
    dy: float
    radius: int
    color: Color


def palette(side: str) -> tuple[Color, Color, Color, Color]:
    """Корпус светлый, корпус тёмный, цвет команды, цвет окон."""
    if side == "player":
        return theme.HULL_PLAYER, theme.HULL_PLAYER_DARK, theme.TEAM_PLAYER, (255, 214, 140)
    return theme.HULL_VECTOR, theme.HULL_VECTOR_DARK, theme.TEAM_VECTOR, (255, 140, 236)


def _s(v: float) -> float:
    return v * SS


# --- Здания ---------------------------------------------------------------------


def _footing(surface: pygame.Surface, cx: float, cy: float, w: float, h: float, dark: Color) -> None:
    rect = pygame.Rect(0, 0, _s(w), _s(h))
    rect.center = (_s(cx), _s(cy))
    pygame.draw.rect(surface, mix(dark, (0, 0, 0), 0.3), rect, border_radius=int(_s(3)))


def _dome(side: str, powered: bool) -> pygame.Surface:
    hull, dark, team, window = palette(side)
    size = DOME_SIZE
    surface = canvas(size, size)
    c = _s(size / 2)
    # Опорное кольцо с огнями и цветом команды.
    pygame.draw.circle(surface, mix(dark, (0, 0, 0), 0.35), (c, c + _s(2)), _s(35))
    radial_disc(surface, (c, c), _s(34), mix(hull, (255, 255, 255), 0.2), dark)
    pygame.draw.circle(surface, team, (c, c), _s(31), int(_s(2.2)))
    # Стеклянный купол.
    glass_hi = (225, 248, 255) if powered else (150, 170, 180)
    glass_lo = mix(theme.GLASS, (10, 30, 60), 0.55) if powered else (40, 52, 62)
    radial_disc(surface, (c, c), _s(28), glass_hi, glass_lo, light=(-0.45, -0.5))
    frame = (*mix(hull, (255, 255, 255), 0.2), 150)
    layer = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
    for k in (0.35, 0.68):
        pygame.draw.ellipse(layer, frame, pygame.Rect(c - _s(28) * k, c - _s(28), _s(56) * k, _s(56)), int(_s(0.8)))
        pygame.draw.ellipse(layer, frame, pygame.Rect(c - _s(28), c - _s(28) * k, _s(56), _s(56) * k), int(_s(0.8)))
    pygame.draw.circle(layer, frame, (c, c), _s(28), int(_s(1)))
    pygame.draw.ellipse(layer, (255, 255, 255, 120), pygame.Rect(c - _s(18), c - _s(22), _s(16), _s(9)))
    surface.blit(layer, (0, 0))
    # Огни на кольце.
    for i in range(8):
        a = i / 8 * math.tau + math.pi / 8
        p = (c + math.cos(a) * _s(31.5), c + math.sin(a) * _s(31.5))
        pygame.draw.circle(surface, window if powered else (70, 60, 50), p, _s(1.8))
    return shrink(surface, size, size)


def _solar(side: str, powered: bool) -> pygame.Surface:
    hull, dark, team, _ = palette(side)
    size = BUILDING_SIZE
    surface = canvas(size, size)
    _footing(surface, 22, 26, 8, 6, dark)
    # Наклонная панель из ячеек.
    top, bottom = _s(9), _s(33)
    pts = [(_s(7), top + _s(3)), (_s(37), top), (_s(39), bottom), (_s(5), bottom + _s(3))]
    bevel_polygon(surface, pts, hull, width=int(_s(1.2)))
    inner = [(_s(9), top + _s(5)), (_s(35), top + _s(2.5)), (_s(36.5), bottom - _s(2)), (_s(7.5), bottom + _s(0.5))]
    pygame.draw.polygon(surface, (22, 46, 92), inner)
    cells_x, cells_y = 4, 3
    for i in range(cells_x + 1):
        t = i / cells_x
        a = (inner[0][0] + (inner[1][0] - inner[0][0]) * t, inner[0][1] + (inner[1][1] - inner[0][1]) * t)
        b = (inner[3][0] + (inner[2][0] - inner[3][0]) * t, inner[3][1] + (inner[2][1] - inner[3][1]) * t)
        pygame.draw.line(surface, (96, 140, 200), a, b, int(_s(0.6)))
    for j in range(cells_y + 1):
        t = j / cells_y
        a = (inner[0][0] + (inner[3][0] - inner[0][0]) * t, inner[0][1] + (inner[3][1] - inner[0][1]) * t)
        b = (inner[1][0] + (inner[2][0] - inner[1][0]) * t, inner[1][1] + (inner[2][1] - inner[1][1]) * t)
        pygame.draw.line(surface, (96, 140, 200), a, b, int(_s(0.6)))
    shine = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
    pygame.draw.polygon(shine, (255, 255, 255, 70), [(_s(12), top + _s(4)), (_s(20), top + _s(3)), (_s(14), bottom), (_s(8), bottom)])
    surface.blit(shine, (0, 0))
    pygame.draw.line(surface, team, pts[3], pts[2], int(_s(1.6)))
    return shrink(surface, size, size)


def _ice_drill(side: str, powered: bool) -> pygame.Surface:
    hull, dark, team, _ = palette(side)
    size = BUILDING_SIZE
    surface = canvas(size, size)
    base = pygame.Rect(_s(8), _s(24), _s(28), _s(14))
    vertical_gradient_rect(surface, base, hull, dark, radius=int(_s(3)))
    pygame.draw.line(surface, team, (base.left + _s(3), base.bottom - _s(3)), (base.right - _s(3), base.bottom - _s(3)), int(_s(1.5)))
    # Вышка-ферма.
    apex = (_s(22), _s(4))
    left, right = (_s(11), _s(25)), (_s(33), _s(25))
    for a, b in ((left, apex), (right, apex), (left, right)):
        pygame.draw.line(surface, mix(hull, (0, 0, 0), 0.25), a, b, int(_s(1.4)))
    for k in (0.33, 0.66):
        p1 = (left[0] + (apex[0] - left[0]) * k, left[1] + (apex[1] - left[1]) * k)
        p2 = (right[0] + (apex[0] - right[0]) * k, right[1] + (apex[1] - right[1]) * k)
        pygame.draw.line(surface, mix(hull, (0, 0, 0), 0.35), p1, p2, int(_s(1)))
    pygame.draw.circle(surface, (150, 225, 255) if powered else (70, 90, 100), (_s(22), _s(31)), _s(3))
    return shrink(surface, size, size)


def drill_rotor(side: str) -> pygame.Surface:
    """Вращающаяся головка бура: рисуется отдельно и поворачивается в кадре."""
    hull, dark, team, _ = palette(side)
    size = 14
    surface = canvas(size, size)
    c = _s(size / 2)
    for i in range(3):
        a = i / 3 * math.tau
        tip = (c + math.cos(a) * _s(6.5), c + math.sin(a) * _s(6.5))
        side_a = (c + math.cos(a + 0.5) * _s(2), c + math.sin(a + 0.5) * _s(2))
        pygame.draw.polygon(surface, mix(hull, (0, 0, 0), 0.2), [side_a, tip, (c, c)])
    pygame.draw.circle(surface, team, (c, c), _s(2.2))
    return shrink(surface, size, size)


def _oxy_gen(side: str, powered: bool) -> pygame.Surface:
    hull, dark, team, _ = palette(side)
    size = BUILDING_SIZE
    surface = canvas(size, size)
    _footing(surface, 22, 30, 32, 14, dark)
    for x in (9, 23):
        tank = pygame.Rect(_s(x), _s(8), _s(12), _s(26))
        layer = pygame.Surface(tank.size, pygame.SRCALPHA)
        for i in range(tank.width):
            t = abs(i / tank.width - 0.35) * 1.6
            pygame.draw.line(layer, mix(mix(hull, (255, 255, 255), 0.25), dark, t), (i, 0), (i, tank.height))
        mask = pygame.Surface(tank.size, pygame.SRCALPHA)
        pygame.draw.rect(mask, (255, 255, 255, 255), mask.get_rect(), border_radius=int(_s(5)))
        layer.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
        surface.blit(layer, tank)
        pygame.draw.line(surface, team, (tank.left + _s(1), tank.top + _s(8)), (tank.right - _s(1), tank.top + _s(8)), int(_s(1.4)))
        pygame.draw.circle(surface, theme.OXYGEN if powered else (40, 70, 70), (tank.centerx, tank.top + _s(17)), _s(2))
    pygame.draw.line(surface, mix(hull, (0, 0, 0), 0.4), (_s(21), _s(22)), (_s(23), _s(22)), int(_s(3)))
    return shrink(surface, size, size)


def _regolith(side: str, powered: bool) -> pygame.Surface:
    hull, dark, team, _ = palette(side)
    size = BUILDING_SIZE
    surface = canvas(size, size)
    body = pygame.Rect(_s(6), _s(12), _s(32), _s(24))
    vertical_gradient_rect(surface, body, mix(hull, (255, 255, 255), 0.1), dark, radius=int(_s(3)))
    # Бункер для руды.
    pygame.draw.polygon(surface, (58, 52, 50), [(_s(9), _s(6)), (_s(23), _s(6)), (_s(20), _s(15)), (_s(12), _s(15))])
    pygame.draw.polygon(surface, (120, 110, 104), [(_s(9), _s(6)), (_s(23), _s(6)), (_s(20), _s(15)), (_s(12), _s(15))], int(_s(1)))
    # Конвейер.
    belt = pygame.Rect(_s(8), _s(28), _s(28), _s(5))
    pygame.draw.rect(surface, (40, 38, 40), belt)
    for i in range(7):
        x = belt.left + _s(2) + i * _s(4)
        pygame.draw.line(surface, (110, 104, 100), (x, belt.top), (x, belt.bottom), int(_s(0.8)))
    furnace = pygame.Rect(_s(26), _s(16), _s(9), _s(8))
    pygame.draw.rect(surface, (255, 150, 60) if powered else (70, 40, 30), furnace, border_radius=int(_s(2)))
    pygame.draw.line(surface, team, (body.left + _s(2), body.top + _s(2)), (body.right - _s(2), body.top + _s(2)), int(_s(1.5)))
    return shrink(surface, size, size)


def _hangar(side: str, powered: bool) -> pygame.Surface:
    hull, dark, team, window = palette(side)
    size = BUILDING_SIZE
    surface = canvas(size, size)
    body = pygame.Rect(_s(3), _s(8), _s(38), _s(30))
    vertical_gradient_rect(surface, body, mix(hull, (255, 255, 255), 0.15), dark, radius=int(_s(8)))
    for i in range(1, 4):
        y = body.top + _s(4) * i
        pygame.draw.line(surface, mix(hull, (0, 0, 0), 0.2), (body.left + _s(4), y), (body.right - _s(4), y), int(_s(0.8)))
    door = pygame.Rect(_s(11), _s(22), _s(22), _s(16))
    pygame.draw.rect(surface, (30, 30, 36), door, border_top_left_radius=int(_s(4)), border_top_right_radius=int(_s(4)))
    for i in range(4):
        x = door.left + _s(2) + i * _s(5.5)
        pygame.draw.polygon(surface, team, [(x, door.top + _s(4)), (x + _s(3), door.top + _s(4)), (x + _s(4.5), door.top + _s(7)), (x + _s(1.5), door.top + _s(7))])
    for x in (door.left - _s(2), door.right + _s(2)):
        pygame.draw.circle(surface, window if powered else (70, 60, 50), (x, door.top + _s(2)), _s(1.6))
    return shrink(surface, size, size)


BUILDING_PAINTERS = {
    "dome": _dome,
    "solar": _solar,
    "ice_drill": _ice_drill,
    "oxy_gen": _oxy_gen,
    "regolith": _regolith,
    "hangar": _hangar,
}

#: Огни зданий для свечения (смещения от центра клетки, px).
BUILDING_LIGHTS: dict[str, list[tuple[float, float, int]]] = {
    "dome": [(0, 0, 40)],
    "solar": [(0, 12, 10)],
    "ice_drill": [(0, 9, 14)],
    "oxy_gen": [(-7, 3, 10), (7, 3, 10)],
    "regolith": [(8, -2, 16)],
    "hangar": [(-11, 1, 10), (11, 1, 10)],
}


def building_light_color(type: str, side: str) -> Color:
    if type == "ice_drill":
        return (120, 210, 255)
    if type == "oxy_gen":
        return theme.OXYGEN
    if type == "regolith":
        return (255, 140, 50)
    return palette(side)[3]


def building_sprite(type: str, side: str, powered: bool) -> pygame.Surface:
    return BUILDING_PAINTERS[type](side, powered)


def scaffold(type: str) -> pygame.Surface:
    """Леса стройплощадки: решётка поверх проявляющегося здания."""
    size = DOME_SIZE if type == "dome" else BUILDING_SIZE
    surface = canvas(size, size)
    color = (220, 200, 160, 210)
    m = _s(6)
    full = _s(size)
    step = _s(8)
    pygame.draw.rect(surface, color, pygame.Rect(m, m, full - 2 * m, full - 2 * m), int(_s(1)))
    x = m
    while x < full - m:
        pygame.draw.line(surface, color, (x, m), (x, full - m), int(_s(0.6)))
        x += step
    y = m
    while y < full - m:
        pygame.draw.line(surface, color, (m, y), (full - m, y), int(_s(0.6)))
        y += step
    pygame.draw.line(surface, color, (m, m), (full - m, full - m), int(_s(0.6)))
    return shrink(surface, size, size)


# --- Юниты (рисуются носом вправо, потом поворачиваются на 16 углов) ---------------


def drone_sprite(side: str, carrying: bool) -> pygame.Surface:
    hull, dark, team, _ = palette(side)
    size = DRONE_SIZE
    surface = canvas(size, size)
    c = _s(size / 2)
    # Винты по диагоналям.
    for dx, dy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
        p = (c + dx * _s(7), c + dy * _s(7))
        pygame.draw.circle(surface, (*mix(dark, (0, 0, 0), 0.3), 150), p, _s(4.5))
        pygame.draw.circle(surface, (200, 210, 220, 120), p, _s(4.5), int(_s(0.6)))
        pygame.draw.line(surface, mix(dark, (0, 0, 0), 0.2), (c, c), p, int(_s(1.4)))
    if carrying:
        crate = pygame.Rect(0, 0, _s(8), _s(8))
        crate.center = (c - _s(1), c)
        pygame.draw.rect(surface, (196, 118, 58), crate, border_radius=int(_s(1.5)))
        pygame.draw.rect(surface, (120, 64, 30), crate, int(_s(0.8)), border_radius=int(_s(1.5)))
    # Корпус-капля носом вправо.
    body = [(c + _s(7), c), (c + _s(1), c - _s(4)), (c - _s(5), c - _s(3)), (c - _s(5), c + _s(3)), (c + _s(1), c + _s(4))]
    bevel_polygon(surface, body, hull, width=int(_s(0.8)))
    pygame.draw.circle(surface, (150, 220, 255), (c + _s(3.5), c), _s(1.4))
    pygame.draw.circle(surface, team, (c - _s(3.5), c), _s(1.5))
    return shrink(surface, size, size)


def rover_chassis(side: str) -> pygame.Surface:
    hull, dark, team, _ = palette(side)
    size = ROVER_SIZE
    surface = canvas(size, size)
    c = _s(size / 2)
    for dx in (-7.5, 0, 7.5):
        for dy in (-8, 8):
            wheel = pygame.Rect(0, 0, _s(6), _s(4))
            wheel.center = (c + _s(dx), c + _s(dy))
            pygame.draw.rect(surface, (26, 24, 24), wheel, border_radius=int(_s(1.5)))
            pygame.draw.rect(surface, (70, 66, 64), wheel, int(_s(0.6)), border_radius=int(_s(1.5)))
    body = pygame.Rect(0, 0, _s(24), _s(14))
    body.center = (c, c)
    vertical_gradient_rect(surface, body, mix(hull, (255, 255, 255), 0.1), dark, radius=int(_s(4)))
    pygame.draw.line(surface, team, (body.left + _s(3), c + _s(4.5)), (body.right - _s(3), c + _s(4.5)), int(_s(1.4)))
    pygame.draw.line(surface, team, (body.left + _s(3), c - _s(4.5)), (body.right - _s(3), c - _s(4.5)), int(_s(1.4)))
    for dy in (-3.5, 3.5):
        pygame.draw.circle(surface, (255, 236, 180), (body.right - _s(1.5), c + _s(dy)), _s(1.1))
    return shrink(surface, size, size)


def rover_turret(side: str) -> pygame.Surface:
    hull, dark, team, _ = palette(side)
    size = ROVER_SIZE
    surface = canvas(size, size)
    c = _s(size / 2)
    barrel = pygame.Rect(c, c - _s(1.4), _s(12), _s(2.8))
    pygame.draw.rect(surface, mix(dark, (0, 0, 0), 0.2), barrel, border_radius=int(_s(1)))
    radial_disc(surface, (c, c), _s(5.5), mix(hull, (255, 255, 255), 0.3), dark)
    pygame.draw.circle(surface, team, (c - _s(1.5), c), _s(1.6))
    return shrink(surface, size, size)
