"""Банк спрайтов: get_sprite(kind, side, state, angle) с подменой на PNG из assets/sprites/.

Имя файла для подмены: {kind}_{side}_{state}_{angle}.png, например guard_rover_player_body_4.png
или hangar_vector_on_0.png. Если файла нет, спрайт рисуется процедурно (render/art.py).
Всё рисуется один раз и хранится в кэше; prerender_jobs() отдаёт задания для полосы загрузки.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pygame

from reddome.render import art
from reddome.render.draw import ellipse_shadow, glow, rotated_variants, soft_shadow
from reddome.sim.types import BUILDING_TYPES, SIDES

SPRITES_DIR = Path(__file__).resolve().parents[2] / "assets" / "sprites"
ANGLES = 16

#: Тени зданий смещены вниз-вправо, как от низкого солнца.
SHADOW_OFFSET = (5, 6)
SHADOW_BLUR = 4


class SpriteBank:
    def __init__(self) -> None:
        self._cache: dict[tuple[str, str, str, int], pygame.Surface] = {}

    def get_sprite(self, kind: str, side: str, state: str, angle: int = 0) -> pygame.Surface:
        key = (kind, side, state, angle)
        sprite = self._cache.get(key)
        if sprite is None:
            sprite = self._load_file(key) or self._paint(key)
            self._cache[key] = sprite
        return sprite

    def _load_file(self, key: tuple[str, str, str, int]) -> pygame.Surface | None:
        path = SPRITES_DIR / f"{key[0]}_{key[1]}_{key[2]}_{key[3]}.png"
        if not path.exists():
            return None
        return pygame.image.load(path).convert_alpha()

    def _paint(self, key: tuple[str, str, str, int]) -> pygame.Surface:
        kind, side, state, angle = key
        if kind in BUILDING_TYPES:
            if state in ("on", "off"):
                return art.building_sprite(kind, side, state == "on")
            if state == "shadow":
                return soft_shadow(self.get_sprite(kind, side, "on"), SHADOW_BLUR)
            if state == "scaffold":
                return art.scaffold(kind)
        if kind == "drone":
            if state == "shadow":
                return ellipse_shadow(16, 10, alpha=90, blur=3)
            return self._rotations(kind, side, state, art.drone_sprite(side, state == "carry"))[angle]
        if kind == "guard_rover":
            if state == "shadow":
                return ellipse_shadow(26, 18, alpha=120, blur=3)
            painter = art.rover_turret if state == "turret" else art.rover_chassis
            return self._rotations(kind, side, state, painter(side))[angle]
        if kind == "drill_rotor":
            return pygame.transform.rotozoom(art.drill_rotor(side), -360 * angle / ANGLES, 1.0)
        if kind == "glow":
            # state — радиус, side — цвет «r,g,b».
            r, g, b = (int(v) for v in side.split(","))
            return glow(int(state), (r, g, b))
        raise KeyError(f"Неизвестный спрайт: {key}")

    def _rotations(self, kind: str, side: str, state: str, base: pygame.Surface) -> list[pygame.Surface]:
        """Все 16 поворотов сразу в кэш: рисуем юнита один раз, а не на каждый угол."""
        variants = rotated_variants(base, ANGLES)
        for i, sprite in enumerate(variants):
            self._cache.setdefault((kind, side, state, i), sprite)
        return variants

    def glow(self, radius: int, color: tuple[int, int, int]) -> pygame.Surface:
        return self.get_sprite("glow", f"{color[0]},{color[1]},{color[2]}", str(radius))

    def prerender_jobs(self) -> list[Callable[[], object]]:
        """Задания пре-рендера для экрана загрузки: каждое — один спрайт."""
        jobs: list[Callable[[], object]] = []

        def job(kind: str, side: str, state: str, angle: int = 0) -> Callable[[], object]:
            return lambda: self.get_sprite(kind, side, state, angle)

        for side in SIDES:
            for type_ in BUILDING_TYPES:
                for state in ("on", "off", "shadow", "scaffold"):
                    jobs.append(job(type_, side, state))
                for dx, dy, radius in art.BUILDING_LIGHTS[type_]:
                    color = art.building_light_color(type_, side)
                    jobs.append(lambda radius=radius, color=color: self.glow(radius, color))
            for angle in range(ANGLES):
                jobs.append(job("drone", side, "idle", angle))
                jobs.append(job("drone", side, "carry", angle))
                jobs.append(job("guard_rover", side, "body", angle))
                jobs.append(job("guard_rover", side, "turret", angle))
                jobs.append(job("drill_rotor", side, "spin", angle))
            jobs.append(job("drone", side, "shadow"))
            jobs.append(job("guard_rover", side, "shadow"))
        return jobs
