"""Загрузка (B5): планета, логотип и полоса прогресса, которая отражает настоящий пре-рендер —
спрайты зданий и юнитов на 16 углов, иконки и карту кратера. Задания выполняются частями,
чтобы окно не зависало: за кадр — сколько успеем за BUDGET_MS.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from typing import Any

import pygame

from reddome.render.backdrop import planet, planet_halo, starfield
from reddome.scenes.base import Scene
from reddome.ui import icons, theme

BUDGET_MS = 25
MIN_SHOW_MS = 600
BAR_WIDTH = 420
PLANET_RADIUS = 150


class BootScene(Scene):
    def enter(self, **data: Any) -> None:
        self.elapsed_ms = 0.0
        self.done = False
        self.sky = starfield(theme.SCREEN_SIZE)
        self.planet = planet(PLANET_RADIUS)
        self.halo = planet_halo(PLANET_RADIUS)
        terrain = self.app.terrain_for(self.app.seed, build=False)
        groups: list[tuple[str, list[Callable[[], object]]]] = [
            ("Спрайты зданий и юнитов", self.app.sprites.prerender_jobs()),
            ("Иконки интерфейса", icons.prerender_jobs()),
            ("Карта кратера", terrain.build_steps()),
        ]
        self.jobs = [(label, job) for label, jobs in groups for job in jobs]
        self.total = len(self.jobs)
        self.index = 0

    def update(self, dt_ms: float) -> None:
        self.elapsed_ms += dt_ms
        started = time.perf_counter()
        while self.index < self.total and (time.perf_counter() - started) * 1000 < BUDGET_MS:
            self.jobs[self.index][1]()
            self.index += 1
        if self.index >= self.total and self.elapsed_ms >= MIN_SHOW_MS and not self.done:
            self.done = True
            self.app.start("menu")

    def draw(self, surface: pygame.Surface) -> None:
        w, h = theme.SCREEN_SIZE
        surface.blit(self.sky, (0, 0))
        center = (w // 2, h // 2 + 250)
        surface.blit(self.halo, self.halo.get_rect(center=center), special_flags=pygame.BLEND_ADD)
        surface.blit(self.planet, self.planet.get_rect(center=center))
        # Купол-маячок на горизонте планеты.
        pulse = 0.6 + 0.4 * math.sin(self.elapsed_ms / 300)
        dome = (center[0], center[1] - PLANET_RADIUS + 2)
        pygame.draw.circle(surface, theme.mix(theme.GLASS, (255, 255, 255), pulse * 0.5), dome, 7, draw_top_right=True, draw_top_left=True)
        theme.draw_text(surface, "КРАСНЫЙ КУПОЛ", (w // 2, 150), 64, theme.SAND, anchor="center", kind="title", shadow=True)
        theme.draw_text(surface, "AI-колония на Марсе", (w // 2, 205), 20, theme.TEXT_QUIET, anchor="center")
        progress = self.index / max(1, self.total)
        bar = pygame.Rect(0, 0, BAR_WIDTH, 10)
        bar.center = (w // 2, 270)
        pygame.draw.rect(surface, (10, 14, 24), bar, border_radius=5)
        fill = bar.copy()
        fill.width = max(10, int(BAR_WIDTH * progress))
        pygame.draw.rect(surface, theme.ACCENT, fill, border_radius=5)
        pygame.draw.rect(surface, theme.PANEL_EDGE, bar, 1, border_radius=5)
        label = self.jobs[min(self.index, self.total - 1)][0] if self.total else ""
        theme.draw_text(surface, f"{label}… {round(progress * 100)} %", (w // 2, 292), 15, theme.TEXT_QUIET, anchor="midtop")
