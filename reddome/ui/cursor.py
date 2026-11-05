"""Свои курсоры (обычный, атака, добыча, стройка, ремонт) и кольцо-маркер приказа (B4).

Курсор — системный цветной (pygame.cursors.Cursor из Surface), поэтому не отстаёт от мыши
и не стоит ничего в кадре. Без окна (SDL dummy) set_cursor может не сработать — тогда молча
остаётся стандартный.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pygame

from reddome.render.draw import SS, canvas, shrink
from reddome.ui import theme
from reddome.ui.icons import icon
from reddome.ui.theme import Color

CURSOR_SIZE = 32
MARKER_MS = 450


def _arrow(color: Color) -> pygame.Surface:
    s = canvas(CURSOR_SIZE, CURSOR_SIZE)
    pts = [(2, 2), (2, 24), (8, 18), (12, 28), (16, 26), (12, 17), (20, 17)]
    pts = [(x * SS, y * SS) for x, y in pts]
    pygame.draw.polygon(s, color, pts)
    pygame.draw.polygon(s, (20, 14, 12), pts, SS)
    pygame.draw.line(s, (255, 255, 255), (3 * SS, 4 * SS), (3 * SS, 20 * SS), SS)
    return shrink(s, CURSOR_SIZE, CURSOR_SIZE)


def _crosshair(color: Color) -> pygame.Surface:
    s = canvas(CURSOR_SIZE, CURSOR_SIZE)
    c = CURSOR_SIZE / 2 * SS
    pygame.draw.circle(s, (20, 14, 12), (c, c), 11 * SS, 4 * SS)
    pygame.draw.circle(s, color, (c, c), 11 * SS, 2 * SS)
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        a = (c + dx * 5 * SS, c + dy * 5 * SS)
        b = (c + dx * 15 * SS, c + dy * 15 * SS)
        pygame.draw.line(s, (20, 14, 12), a, b, 4 * SS)
        pygame.draw.line(s, color, a, b, 2 * SS)
    return shrink(s, CURSOR_SIZE, CURSOR_SIZE)


def _with_badge(base: pygame.Surface, painter: str) -> pygame.Surface:
    image = base.copy()
    image.blit(icon(painter, 16), (CURSOR_SIZE - 17, CURSOR_SIZE - 17))
    return image


@dataclass(frozen=True)
class CursorSpec:
    image: pygame.Surface
    hotspot: tuple[int, int]


class CursorManager:
    """Меняет системный курсор только когда вид действительно сменился."""

    def __init__(self) -> None:
        arrow = _arrow(theme.SAND)
        self.specs = {
            "normal": CursorSpec(arrow, (2, 2)),
            "attack": CursorSpec(_crosshair(theme.ALARM), (16, 16)),
            "target": CursorSpec(_crosshair(theme.ACCENT), (16, 16)),
            "gather": CursorSpec(_with_badge(_arrow(theme.SUCCESS), "gather"), (2, 2)),
            "build": CursorSpec(_with_badge(_arrow(theme.ACCENT), "build"), (2, 2)),
            "repair": CursorSpec(_with_badge(_arrow(theme.SUCCESS), "repair"), (2, 2)),
        }
        self.kind = ""
        self._cursors: dict[str, pygame.cursors.Cursor] = {}

    def set(self, kind: str) -> None:
        if kind == self.kind:
            return
        self.kind = kind
        spec = self.specs.get(kind, self.specs["normal"])
        try:
            cursor = self._cursors.get(kind)
            if cursor is None:
                cursor = pygame.cursors.Cursor(spec.hotspot, spec.image)
                self._cursors[kind] = cursor
            pygame.mouse.set_cursor(cursor)
        except pygame.error:
            pass


@dataclass
class OrderMarker:
    """Сжимающееся кольцо там, куда отдан приказ: зелёное — идти, красное — атака, жёлтое — добыча."""

    x: float
    y: float
    color: Color
    age_ms: float = 0.0


def draw_markers(surface: pygame.Surface, markers: list[OrderMarker], camera: tuple[float, float]) -> None:
    for m in markers:
        t = m.age_ms / MARKER_MS
        radius = 14 * (1 - t) + 3
        center = (m.x - camera[0], m.y - camera[1])
        rect = pygame.Rect(0, 0, radius * 2.2, radius * 1.2)
        rect.center = (round(center[0]), round(center[1]))
        pygame.draw.ellipse(surface, m.color, rect, 2)
        if t < 0.5:
            inner = rect.inflate(-rect.width * 0.5, -rect.height * 0.5)
            pygame.draw.ellipse(surface, m.color, inner, 1)
        for i in range(4):
            a = i * math.tau / 4 + t * 2
            p = (center[0] + math.cos(a) * radius * 1.2, center[1] + math.sin(a) * radius * 0.65)
            pygame.draw.circle(surface, m.color, p, 1.5)


def update_markers(markers: list[OrderMarker], dt_ms: float) -> list[OrderMarker]:
    for m in markers:
        m.age_ms += dt_ms
    return [m for m in markers if m.age_ms < MARKER_MS]
