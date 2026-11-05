"""Фоны экранов (B5): звёздное небо, планета для загрузки и панорама кратера с куполом для меню.

Всё рисуется один раз при входе на экран; в кадре — только blit и пыль.
"""

from __future__ import annotations

import math
import random

import pygame

from reddome.render import art
from reddome.render.draw import angle_index, glow, radial_disc
from reddome.render.lighting import Lighting, phase_values
from reddome.render.sprites import ANGLES, SHADOW_OFFSET, SpriteBank
from reddome.render.terrain import Terrain
from reddome.sim.types import Point
from reddome.ui import theme

#: Постройки витрины на панораме меню: тип и клетка (рядом с базой игрока).
SHOWCASE: tuple[tuple[str, Point], ...] = (
    ("dome", Point(4, 27)),
    ("solar", Point(6, 29)),
    ("solar", Point(7, 27)),
    ("oxy_gen", Point(2, 25)),
    ("hangar", Point(6, 25)),
    ("regolith", Point(8, 21)),
)


def starfield(size: tuple[int, int], seed: int = 3) -> pygame.Surface:
    rng = random.Random(seed)
    surface = pygame.Surface(size)
    for y in range(size[1]):
        t = y / size[1]
        pygame.draw.line(surface, theme.mix((6, 8, 18), (40, 16, 12), t ** 2), (0, y), (size[0], y))
    for _ in range(260):
        v = rng.randint(90, 255)
        surface.set_at((rng.randrange(size[0]), rng.randrange(size[1])), (v, v, min(255, v + 20)))
    return surface


def planet(radius: int, seed: int = 5) -> pygame.Surface:
    """Марс: шар с пятнами, кратерами и тенью ночной стороны. Ореол атмосферы — planet_halo()."""
    rng = random.Random(seed)
    size = radius * 2 + 4
    c = size / 2
    body = pygame.Surface((size, size), pygame.SRCALPHA)
    radial_disc(body, (c, c), radius, theme.RUST_LIGHT, theme.RUST_DARK, light=(-0.4, -0.4))
    spots = pygame.Surface((12, 12), pygame.SRCALPHA)
    for y in range(12):
        for x in range(12):
            spots.set_at((x, y), (*rng.choice([theme.RUST_DARK, theme.DUST, theme.GROUND]), rng.randint(0, 90)))
    body.blit(pygame.transform.smoothscale(spots, (size, size)), (0, 0))
    # Кратеры и шапка — на отдельном слое: pygame.draw заменяет альфу, а не смешивает.
    marks = pygame.Surface((size, size), pygame.SRCALPHA)
    for _ in range(18):
        a = rng.uniform(0, math.tau)
        d = rng.uniform(0, radius * 0.85)
        r = rng.uniform(radius * 0.03, radius * 0.09)
        p = (c + math.cos(a) * d, c + math.sin(a) * d)
        pygame.draw.circle(marks, (*theme.RUST_DARK, 120), p, r)
        pygame.draw.circle(marks, (*theme.DUST, 90), (p[0] - r * 0.25, p[1] - r * 0.25), r * 0.7, 1)
    pygame.draw.ellipse(marks, (240, 236, 230, 200), (c - radius * 0.3, c - radius * 0.98, radius * 0.6, radius * 0.22))
    body.blit(marks, (0, 0))
    # Тень ночной стороны.
    shade = pygame.Surface((size, size), pygame.SRCALPHA)
    # Кольца от большого к малому: pygame.draw не смешивает альфу, а заменяет, поэтому центр темнее.
    reach = int(radius * 1.6)
    for i in range(reach, 0, -2):
        k = i / reach
        pygame.draw.circle(shade, (0, 0, 0, int(215 * (1 - k) ** 0.7)), (c + radius * 0.55, c + radius * 0.55), i)
    body.blit(shade, (0, 0))
    mask = pygame.Surface((size, size), pygame.SRCALPHA)
    pygame.draw.circle(mask, (255, 255, 255, 255), (c, c), radius)
    body.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    return body


def planet_halo(radius: int) -> pygame.Surface:
    """Свечение атмосферы вокруг планеты — рисуется с BLEND_ADD."""
    return glow(int(radius * 1.35), (255, 110, 50))


def panorama(terrain: Terrain, sprites: SpriteBank, seed: int = 1) -> pygame.Surface:
    """Кадр кратера у базы игрока в закатном свете: здания витрины, огни, виньетка."""
    w, h = theme.SCREEN_SIZE
    tile = theme.TILE
    left = 0
    top = terrain.size[1] - h
    surface = pygame.Surface((w, h))
    surface.blit(terrain.ground, (-left, -top))
    for (_, level), (sprite, (x, y)) in terrain.ore_sprites.items():
        if level == 3:
            surface.blit(sprite, (x - left, y - top))
    for type_, p in SHOWCASE:
        x, y = (p.x + 0.5) * tile - left, (p.y + 0.5) * tile - top
        shadow = sprites.get_sprite(type_, "player", "shadow")
        surface.blit(shadow, shadow.get_rect(center=(x + SHADOW_OFFSET[0], y + SHADOW_OFFSET[1])))
        sprite = sprites.get_sprite(type_, "player", "on")
        surface.blit(sprite, sprite.get_rect(center=(x, y)))
    color, alpha, lights = phase_values(0.62)
    tint = pygame.Surface((w, h))
    tint.fill(color)
    tint.set_alpha(alpha)
    surface.blit(tint, (0, 0))
    for type_, p in SHOWCASE:
        x, y = (p.x + 0.5) * tile - left, (p.y + 0.5) * tile - top
        light = art.building_light_color(type_, "player")
        for dx, dy, radius in art.BUILDING_LIGHTS[type_]:
            image = sprites.glow(radius, light).copy()
            v = int(255 * lights)
            image.fill((v, v, v), special_flags=pygame.BLEND_MULT)
            surface.blit(image, (x + dx - radius, y + dy - radius), special_flags=pygame.BLEND_ADD)
    Lighting(theme.SCREEN_SIZE, seed).draw_vignette(surface)
    return surface


def showcase_drone_path() -> tuple[tuple[float, float], tuple[float, float]]:
    """Отрезок, по которому летают дроны на панораме: от купола к руде (в пикселях экрана)."""
    w, h = theme.SCREEN_SIZE
    tile = theme.TILE
    top = 32 * tile - h
    dome, ore = SHOWCASE[0][1], Point(8, 21)
    return ((dome.x + 0.5) * tile, (dome.y + 0.5) * tile - top), ((ore.x + 0.5) * tile, (ore.y + 1.5) * tile - top)


def drone_frame(sprites: SpriteBank, angle: float, carrying: bool) -> pygame.Surface:
    return sprites.get_sprite("drone", "player", "carry" if carrying else "idle", angle_index(angle, ANGLES))
