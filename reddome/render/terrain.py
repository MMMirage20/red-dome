"""Поверхность Марса (B2): шум по seed вместо шахматки, кратеры, камни, следы ветра,
объёмные скалы, кристаллы льда и рудные жилы с мягкими краями.

Шум делается без numpy: маленькая поверхность со случайными цветами растягивается smoothscale —
получается плавный value-noise; несколько таких слоёв разного масштаба дают fBm.
Грунт рисуется один раз; руда рисуется отдельными спрайтами по месторождениям и «худеет»
по мере истощения (3 уровня).
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable

import pygame

from reddome.render.draw import SS, canvas, ellipse_shadow, shrink, soft_shadow
from reddome.sim.types import Deposit, GameMap, Point
from reddome.ui import theme
from reddome.ui.theme import Color, mix

TILE = theme.TILE
ICE_BASE = (196, 226, 238)
ICE_LIGHT = (232, 248, 255)
ICE_SHADE = (120, 170, 200)
ORE_BASE = (86, 84, 92)
ORE_VEIN = (196, 202, 216)
ORE_DARK = (52, 50, 58)


def ore_level(deposit: Deposit) -> int:
    """3 — полное поле, 2 — половина, 1 — почти пусто, 0 — истощено."""
    if deposit.amount <= 0:
        return 0
    share = deposit.amount / deposit.initial
    return 3 if share > 2 / 3 else 2 if share > 1 / 3 else 1


def _noise_layer(rng: random.Random, size: tuple[int, int], cells: tuple[int, int], colors: list[Color],
                 alpha: tuple[int, int]) -> pygame.Surface:
    small = pygame.Surface(cells, pygame.SRCALPHA)
    for y in range(cells[1]):
        for x in range(cells[0]):
            small.set_at((x, y), (*rng.choice(colors), rng.randint(*alpha)))
    return pygame.transform.smoothscale(small, size)


def _blob_polygon(rng: random.Random, cx: float, cy: float, radius: float, points: int = 8) -> list[tuple[float, float]]:
    return [
        (
            cx + math.cos(i / points * math.tau) * radius * rng.uniform(0.7, 1.0),
            cy + math.sin(i / points * math.tau) * radius * rng.uniform(0.65, 0.95),
        )
        for i in range(points)
    ]


class Terrain:
    """Грунт, скалы и лёд — одна большая поверхность; руда — спрайты по месторождениям."""

    def __init__(self, game_map: GameMap, deposits: list[Deposit], seed: int) -> None:
        self.map = game_map
        self.seed = seed
        self.size = (game_map.width * TILE, game_map.height * TILE)
        self.ground = pygame.Surface(self.size)
        self.ore_sprites: dict[tuple[int, int], tuple[pygame.Surface, tuple[int, int]]] = {}
        self._deposits = deposits

    # --- Построение по шагам (для полосы загрузки) ------------------------------

    def build_steps(self) -> list[Callable[[], object]]:
        rng = random.Random(self.seed * 7919 + 17)
        steps: list[Callable[[], object]] = [
            lambda: self._paint_noise(rng),
            lambda: self._paint_details(rng),
            lambda: self._paint_pads(),
            lambda: self._paint_rocks(rng),
            lambda: self._paint_ice(rng),
        ]
        for deposit in self._deposits:
            for level in (3, 2, 1):
                steps.append(lambda d=deposit, lv=level: self._paint_ore(d, lv))
        return steps

    def build(self) -> Terrain:
        for step in self.build_steps():
            step()
        return self

    def _tiles(self, kind: str) -> list[Point]:
        w = self.map.width
        return [Point(i % w, i // w) for i, tile in enumerate(self.map.tiles) if tile == kind]

    def _paint_noise(self, rng: random.Random) -> None:
        self.ground.fill(theme.RUST_MID)
        tones = [theme.RUST_DARK, theme.RUST_MID, theme.RUST_LIGHT, theme.GROUND]
        for cells, alpha in (((10, 7), (90, 160)), ((24, 16), (40, 90)), ((60, 40), (20, 50))):
            self.ground.blit(_noise_layer(rng, self.size, cells, tones, alpha), (0, 0))
        grain = _noise_layer(rng, self.size, (self.size[0] // 3, self.size[1] // 3), [theme.RUST_DARK, theme.DUST], (0, 26))
        self.ground.blit(grain, (0, 0))

    def _free_ground(self, rng: random.Random) -> tuple[float, float]:
        while True:
            x, y = rng.uniform(0, self.size[0]), rng.uniform(0, self.size[1])
            tile = self.map.tiles[int(y // TILE) * self.map.width + int(x // TILE)]
            near_base = any(math.hypot(x - (b.x + 0.5) * TILE, y - (b.y + 0.5) * TILE) < 4 * TILE for b in self.map.bases.values())
            if tile == "ground" and not near_base:
                return x, y

    def _paint_details(self, rng: random.Random) -> None:
        layer = pygame.Surface(self.size, pygame.SRCALPHA)
        # Следы ветра — длинные светлые полосы под одним углом.
        for _ in range(70):
            x, y = rng.uniform(0, self.size[0]), rng.uniform(0, self.size[1])
            length = rng.uniform(40, 110)
            streak = pygame.Surface((int(length), 6), pygame.SRCALPHA)
            pygame.draw.ellipse(streak, (*theme.DUST, rng.randint(14, 30)), streak.get_rect())
            streak = pygame.transform.rotate(streak, 18 + rng.uniform(-4, 4))
            layer.blit(streak, (x, y))
        # Кратеры: тёмная чаша, светлый край снизу-справа, тень сверху-слева.
        for _ in range(22):
            x, y = self._free_ground(rng)
            r = rng.uniform(9, 26)
            crater = canvas(int(r * 2 + 8), int(r * 2 + 8))
            c = (crater.get_width() / 2, crater.get_height() / 2)
            pygame.draw.circle(crater, (*theme.DUST, 70), (c[0] + 2 * SS, c[1] + 2 * SS), r * SS)
            pygame.draw.circle(crater, (*theme.RUST_DARK, 150), c, r * SS * 0.92)
            pygame.draw.circle(crater, (*mix(theme.RUST_DARK, theme.RUST_MID, 0.5), 160), (c[0] + 1.5 * SS, c[1] + 1.5 * SS), r * SS * 0.7)
            crater = shrink(crater, crater.get_width() // SS, crater.get_height() // SS)
            layer.blit(pygame.transform.gaussian_blur(crater, 1), (x - crater.get_width() / 2, y - crater.get_height() / 2))
        # Мелкие камни.
        for _ in range(520):
            x, y = self._free_ground(rng)
            r = rng.uniform(0.8, 2.4)
            pygame.draw.circle(layer, (*theme.RUST_DARK, 170), (x + 0.8, y + 0.8), r)
            pygame.draw.circle(layer, (*mix(theme.RUST_LIGHT, theme.DUST, 0.5), 150), (x, y), r * 0.8)
        self.ground.blit(layer, (0, 0))

    def _paint_pads(self) -> None:
        """Посадочные площадки под куполами."""
        for base in self.map.bases.values():
            cx, cy = (base.x + 0.5) * TILE, (base.y + 0.5) * TILE
            pad = canvas(110, 110)
            c = pad.get_width() / 2
            pygame.draw.circle(pad, (*mix(theme.RUST_DARK, (60, 56, 54), 0.6), 200), (c, c), 50 * SS)
            pygame.draw.circle(pad, (160, 150, 140, 90), (c, c), 50 * SS, int(1.5 * SS))
            pygame.draw.circle(pad, (160, 150, 140, 60), (c, c), 44 * SS, int(1 * SS))
            pad = pygame.transform.gaussian_blur(shrink(pad, 110, 110), 1)
            self.ground.blit(pad, (cx - 55, cy - 55))

    def _paint_rocks(self, rng: random.Random) -> None:
        under = pygame.Surface(self.size, pygame.SRCALPHA)
        for p in self._tiles("rock"):
            pygame.draw.circle(under, (*theme.RUST_DARK, 120), ((p.x + 0.5) * TILE, (p.y + 0.5) * TILE), TILE * 0.7)
        self.ground.blit(pygame.transform.gaussian_blur(under, 6), (0, 0))
        for p in self._tiles("rock"):
            for i in range(rng.choice((1, 2, 2))):
                size = 52
                boulder = canvas(size, size)
                c = size * SS / 2
                r = (rng.uniform(13, 16) if i == 0 else rng.uniform(7, 10)) * SS
                poly = _blob_polygon(rng, c, c, r, 9)
                pygame.draw.polygon(boulder, mix(theme.ROCK, (0, 0, 0), 0.25), poly)
                inner = [(c + (x - c) * 0.78 - 0.12 * r, c + (y - c) * 0.72 - 0.16 * r) for x, y in poly]
                pygame.draw.polygon(boulder, mix(theme.ROCK, theme.RUST_LIGHT, 0.35), inner)
                top = [(c + (x - c) * 0.45 - 0.25 * r, c + (y - c) * 0.4 - 0.3 * r) for x, y in poly]
                pygame.draw.polygon(boulder, mix(theme.ROCK, theme.DUST, 0.45), top)
                boulder = shrink(boulder, size, size)
                shadow = soft_shadow(boulder, 3, alpha=150)
                ox = (p.x + 0.5) * TILE + rng.uniform(-4, 4) - size / 2
                oy = (p.y + 0.5) * TILE + rng.uniform(-4, 4) - size / 2
                self.ground.blit(shadow, (ox + 4 - 6, oy + 5 - 6))
                self.ground.blit(boulder, (ox, oy))

    def _paint_ice(self, rng: random.Random) -> None:
        patch = pygame.Surface(self.size, pygame.SRCALPHA)
        tiles = self._tiles("ice")
        for p in tiles:
            pygame.draw.circle(patch, (*ICE_BASE, 235), ((p.x + 0.5) * TILE, (p.y + 0.5) * TILE), TILE * 0.78)
        self.ground.blit(pygame.transform.gaussian_blur(patch, 5), (0, 0))
        for p in tiles:
            for _ in range(rng.randint(3, 5)):
                size = 20
                shard = canvas(size, size)
                c = size * SS / 2
                length = rng.uniform(5, 9) * SS
                width = rng.uniform(1.8, 3) * SS
                body = [(c, c - length), (c + width, c - length * 0.3), (c + width * 0.8, c + length * 0.6),
                        (c, c + length * 0.75), (c - width * 0.8, c + length * 0.6), (c - width, c - length * 0.3)]
                pygame.draw.polygon(shard, ICE_SHADE, body)
                pygame.draw.polygon(shard, ICE_LIGHT, body[:3] + [(c, c + length * 0.75)])
                pygame.draw.line(shard, (255, 255, 255), body[0], (c, c + length * 0.75), int(0.6 * SS))
                shard = shrink(shard, size, size)
                shard = pygame.transform.rotate(shard, rng.uniform(-35, 35))
                x = (p.x + 0.5) * TILE + rng.uniform(-11, 11) - shard.get_width() / 2
                y = (p.y + 0.5) * TILE + rng.uniform(-11, 11) - shard.get_height() / 2
                self.ground.blit(ellipse_shadow(10, 5, alpha=70, blur=2), (x + 4, y + shard.get_height() - 6))
                self.ground.blit(shard, (x, y))

    def _paint_ore(self, deposit: Deposit, level: int) -> None:
        rng = random.Random(self.seed * 31 + deposit.id * 101 + level)
        xs = [p.x for p in deposit.tiles]
        ys = [p.y for p in deposit.tiles]
        pad = 20
        left, top = min(xs) * TILE - pad, min(ys) * TILE - pad
        width = (max(xs) - min(xs) + 1) * TILE + pad * 2
        height = (max(ys) - min(ys) + 1) * TILE + pad * 2
        layer = pygame.Surface((width, height), pygame.SRCALPHA)
        shrink_by = {3: 1.0, 2: 0.8, 1: 0.6}[level]
        for p in deposit.tiles:
            c = ((p.x + 0.5) * TILE - left, (p.y + 0.5) * TILE - top)
            pygame.draw.circle(layer, (*ORE_BASE, 220), c, TILE * 0.75 * shrink_by)
        layer = pygame.transform.gaussian_blur(layer, 5)
        detail = pygame.Surface((width * SS, height * SS), pygame.SRCALPHA)
        for p in deposit.tiles:
            cx, cy = ((p.x + 0.5) * TILE - left) * SS, ((p.y + 0.5) * TILE - top) * SS
            for _ in range({3: 3, 2: 2, 1: 1}[level]):
                # Глыба руды с металлическим бликом.
                r = rng.uniform(5, 8) * SS * shrink_by
                ox, oy = cx + rng.uniform(-9, 9) * SS, cy + rng.uniform(-9, 9) * SS
                poly = _blob_polygon(rng, ox, oy, r, 7)
                pygame.draw.polygon(detail, ORE_DARK, poly)
                pygame.draw.polygon(detail, (128, 130, 144), [(ox + (x - ox) * 0.7 - r * 0.15, oy + (y - oy) * 0.65 - r * 0.2) for x, y in poly])
            for _ in range({3: 4, 2: 3, 1: 1}[level]):
                # Жила: ломаная светлая линия.
                x, y = cx + rng.uniform(-12, 12) * SS, cy + rng.uniform(-12, 12) * SS
                points = [(x, y)]
                for _ in range(3):
                    x += rng.uniform(-7, 7) * SS
                    y += rng.uniform(-5, 5) * SS
                    points.append((x, y))
                pygame.draw.lines(detail, ORE_DARK, False, [(a + SS, b + SS) for a, b in points], int(2 * SS))
                pygame.draw.lines(detail, ORE_VEIN, False, points, int(1.3 * SS))
            for _ in range({3: 5, 2: 3, 1: 1}[level]):
                sx, sy = cx + rng.uniform(-12, 12) * SS, cy + rng.uniform(-12, 12) * SS
                pygame.draw.circle(detail, (255, 255, 255, 230), (sx, sy), rng.uniform(0.6, 1.2) * SS)
        layer.blit(shrink(detail, width, height), (0, 0))
        self.ore_sprites[(deposit.id, level)] = (layer, (left, top))

    # --- Кадр -----------------------------------------------------------------------

    def draw(self, surface: pygame.Surface, camera: tuple[float, float], deposits: list[Deposit]) -> None:
        cx, cy = camera
        surface.blit(self.ground, (-cx, -cy))
        for deposit in deposits:
            level = ore_level(deposit)
            if level:
                sprite, (left, top) = self.ore_sprites[(deposit.id, level)]
                surface.blit(sprite, (left - cx, top - cy))

    def minimap(self, size: tuple[int, int], deposits: list[Deposit]) -> pygame.Surface:
        image = pygame.transform.smoothscale(self.ground, size)
        sx, sy = size[0] / self.map.width, size[1] / self.map.height
        for deposit in deposits:
            if deposit.amount > 0:
                for p in deposit.tiles:
                    pygame.draw.rect(image, theme.METAL, (p.x * sx, p.y * sy, math.ceil(sx), math.ceil(sy)))
        return image
