"""Частицы и эффекты (B3): пыль из-под колёс, искры сварки, «+10» при сдаче руды,
трассеры выстрелов, вспышки и взрывы с обломками. Живут только в отрисовке и на симулятор не влияют.
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable
from dataclasses import dataclass

import pygame

from reddome.ui import theme
from reddome.ui.theme import Color

MAX_PARTICLES = 300
ALPHA_LEVELS = 8


@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    life_ms: float
    max_ms: float
    color: Color
    size: float
    #: Ускорение по y (обломки падают, дым поднимается).
    gravity: float = 0.0
    #: Как меняется размер к концу жизни (дым растёт).
    grow: float = 0.0


@dataclass
class FloatingText:
    text: str
    x: float
    y: float
    life_ms: float
    color: Color


@dataclass
class Tracer:
    x0: float
    y0: float
    x1: float
    y1: float
    life_ms: float
    color: Color


@dataclass
class Flash:
    x: float
    y: float
    life_ms: float
    max_ms: float
    radius: int
    color: Color


class Effects:
    def __init__(self, enabled: bool = True, seed: int = 7) -> None:
        self.enabled = enabled
        self.rng = random.Random(seed)
        self.particles: list[Particle] = []
        self.texts: list[FloatingText] = []
        self.tracers: list[Tracer] = []
        self.flashes: list[Flash] = []
        self._dots: dict[tuple[Color, int, int], pygame.Surface] = {}

    # --- Создание ---------------------------------------------------------------

    def _add(self, particle: Particle) -> None:
        if self.enabled and len(self.particles) < MAX_PARTICLES:
            self.particles.append(particle)

    def dust(self, x: float, y: float, count: int = 1) -> None:
        for _ in range(count):
            a = self.rng.uniform(0, math.tau)
            self._add(Particle(x, y, math.cos(a) * 12, math.sin(a) * 6 - 6, 0, self.rng.uniform(500, 900),
                               theme.DUST, self.rng.uniform(1.5, 3), grow=2.5))

    def sparks(self, x: float, y: float, count: int = 4) -> None:
        for _ in range(count):
            a = self.rng.uniform(0, math.tau)
            speed = self.rng.uniform(30, 90)
            self._add(Particle(x, y, math.cos(a) * speed, math.sin(a) * speed - 30, 0, self.rng.uniform(200, 450),
                               (255, self.rng.randint(190, 240), 120), self.rng.uniform(0.8, 1.6), gravity=160))

    def explosion(self, x: float, y: float, big: bool = False) -> None:
        self.flashes.append(Flash(x, y, 0, 380 if big else 240, 60 if big else 30, (255, 170, 80)))
        for _ in range(26 if big else 12):
            a = self.rng.uniform(0, math.tau)
            speed = self.rng.uniform(40, 160 if big else 100)
            self._add(Particle(x, y, math.cos(a) * speed, math.sin(a) * speed - 40, 0, self.rng.uniform(400, 900),
                               self.rng.choice([(70, 66, 64), (120, 110, 104), (255, 150, 60)]),
                               self.rng.uniform(1.5, 3.2), gravity=200))
        for _ in range(10 if big else 5):
            self._add(Particle(x + self.rng.uniform(-8, 8), y + self.rng.uniform(-8, 8), self.rng.uniform(-8, 8), -18, 0,
                               self.rng.uniform(900, 1500), (60, 52, 48), self.rng.uniform(4, 7), grow=8))

    def shot(self, x0: float, y0: float, x1: float, y1: float, color: Color) -> None:
        self.tracers.append(Tracer(x0, y0, x1, y1, 160, color))
        self.flashes.append(Flash(x0, y0, 0, 140, 14, color))
        self.flashes.append(Flash(x1, y1, 0, 120, 9, (255, 220, 160)))
        self.sparks(x1, y1, 3)

    def popup(self, text: str, x: float, y: float, color: Color = theme.SUCCESS) -> None:
        self.texts.append(FloatingText(text, x, y, 1100, color))

    # --- Кадр -------------------------------------------------------------------

    def update(self, dt_ms: float) -> None:
        dt = dt_ms / 1000
        alive = []
        for p in self.particles:
            p.life_ms += dt_ms
            if p.life_ms >= p.max_ms:
                continue
            p.vy += p.gravity * dt
            p.x += p.vx * dt
            p.y += p.vy * dt
            alive.append(p)
        self.particles = alive
        for t in self.texts:
            t.life_ms -= dt_ms
            t.y -= 22 * dt
        self.texts = [t for t in self.texts if t.life_ms > 0]
        for tr in self.tracers:
            tr.life_ms -= dt_ms
        self.tracers = [tr for tr in self.tracers if tr.life_ms > 0]
        for f in self.flashes:
            f.life_ms += dt_ms
        self.flashes = [f for f in self.flashes if f.life_ms < f.max_ms]

    def _dot(self, color: Color, radius: int, level: int) -> pygame.Surface:
        key = (color, radius, level)
        dot = self._dots.get(key)
        if dot is None:
            dot = pygame.Surface((radius * 2 + 2, radius * 2 + 2), pygame.SRCALPHA)
            pygame.draw.circle(dot, (*color, int(255 * (level + 1) / ALPHA_LEVELS)), (radius + 1, radius + 1), radius)
            self._dots[key] = dot
        return dot

    def draw(self, surface: pygame.Surface, camera: tuple[float, float],
             glow_of: Callable[[int, Color, float], pygame.Surface]) -> None:
        cx, cy = camera
        for p in self.particles:
            t = p.life_ms / p.max_ms
            radius = max(1, round(p.size + p.grow * t))
            level = max(0, min(ALPHA_LEVELS - 1, int((1 - t) * ALPHA_LEVELS)))
            dot = self._dot(p.color, radius, level)
            surface.blit(dot, (p.x - cx - radius, p.y - cy - radius))
        for tr in self.tracers:
            pygame.draw.line(surface, tr.color, (tr.x0 - cx, tr.y0 - cy), (tr.x1 - cx, tr.y1 - cy), 3)
            pygame.draw.line(surface, (255, 255, 255), (tr.x0 - cx, tr.y0 - cy), (tr.x1 - cx, tr.y1 - cy), 1)
        for f in self.flashes:
            k = 1 - f.life_ms / f.max_ms
            radius = max(4, int(f.radius * (0.6 + 0.4 * k)))
            image = glow_of(radius, f.color, k)
            surface.blit(image, (f.x - cx - radius, f.y - cy - radius), special_flags=pygame.BLEND_ADD)
        for t in self.texts:
            label = theme.render_text(t.text, 18, t.color, "title").copy()
            label.set_alpha(int(255 * min(1, t.life_ms / 500)))
            surface.blit(label, label.get_rect(center=(t.x - cx, t.y - cy)))
