"""Освещение (B2): смена дня и ночи по фазе сола, виньетка и плывущая пыль."""

from __future__ import annotations

import math
import random

import pygame

from reddome.ui import theme

#: Ключевые точки суток: доля сола → (цвет тонировки, непрозрачность, сила огней).
PHASES: tuple[tuple[float, tuple[int, int, int], int, float], ...] = (
    (0.00, (255, 190, 140), 0, 0.35),    # утро
    (0.45, (255, 190, 140), 0, 0.30),    # день
    (0.60, (255, 120, 60), 60, 0.65),    # закат
    (0.72, (14, 20, 64), 150, 1.00),     # ночь
    (0.92, (14, 20, 64), 150, 1.00),
    (1.00, (255, 190, 140), 0, 0.35),    # рассвет
)


def phase_values(phase: float) -> tuple[tuple[int, int, int], int, float]:
    """Тонировка и сила огней для фазы сола 0…1 с плавным переходом между ключевыми точками."""
    for (p0, c0, a0, g0), (p1, c1, a1, g1) in zip(PHASES, PHASES[1:]):
        if p0 <= phase <= p1:
            t = (phase - p0) / (p1 - p0) if p1 > p0 else 0
            return theme.mix(c0, c1, t), int(a0 + (a1 - a0) * t), g0 + (g1 - g0) * t
    return PHASES[0][1], PHASES[0][2], PHASES[0][3]


class Lighting:
    def __init__(self, size: tuple[int, int], seed: int = 1) -> None:
        self.size = size
        self.tint = pygame.Surface(size)
        self.vignette = self._make_vignette(size)
        rng = random.Random(seed)
        #: Пылинка: x, y, скорость; картинка рисуется заранее — на экране без альфа-канала draw.circle её не даст.
        self.motes: list[list[float]] = []
        self.mote_images: list[pygame.Surface] = []
        for _ in range(46):
            r = rng.uniform(1, 2.4)
            image = pygame.Surface((int(r * 2 + 2), int(r * 2 + 2)), pygame.SRCALPHA)
            pygame.draw.circle(image, (*theme.DUST, rng.randint(30, 80)), (r + 1, r + 1), r)
            self.mote_images.append(image)
            self.motes.append([rng.uniform(0, size[0]), rng.uniform(0, size[1]), rng.uniform(8, 22)])

    @staticmethod
    def _make_vignette(size: tuple[int, int]) -> pygame.Surface:
        small = pygame.Surface((64, 36), pygame.SRCALPHA)
        for y in range(36):
            for x in range(64):
                dx, dy = (x - 31.5) / 32, (y - 17.5) / 18
                d = min(1.0, math.hypot(dx, dy) / 1.25)
                small.set_at((x, y), (10, 4, 2, int(170 * d ** 2.4)))
        return pygame.transform.smoothscale(small, size)

    def apply_tint(self, surface: pygame.Surface, phase: float) -> float:
        """Накладывает тонировку времени суток; возвращает силу огней зданий (0…1)."""
        color, alpha, lights = phase_values(phase)
        if alpha > 0:
            self.tint.fill(color)
            self.tint.set_alpha(alpha)
            surface.blit(self.tint, (0, 0))
        return lights

    def update_dust(self, dt_ms: float) -> None:
        w, h = self.size
        for mote in self.motes:
            mote[0] = (mote[0] + mote[2] * dt_ms / 1000) % w
            mote[1] = (mote[1] + mote[2] * 0.25 * dt_ms / 1000) % h

    def draw_dust(self, surface: pygame.Surface) -> None:
        for (x, y, _), image in zip(self.motes, self.mote_images):
            surface.blit(image, (x, y))

    def draw_vignette(self, surface: pygame.Surface) -> None:
        surface.blit(self.vignette, (0, 0))
