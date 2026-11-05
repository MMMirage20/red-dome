"""Приёмы рисования, которые убирают «1980-е» (B1): сглаживание, градиенты, мягкие тени, свечение."""

from __future__ import annotations

import math

import pygame

from reddome.ui.theme import Color, mix

#: Во сколько раз крупнее рисуем перед уменьшением smoothscale — так края получаются гладкими.
SS = 3

RGBA = tuple[int, int, int, int]


def canvas(width: int, height: int) -> pygame.Surface:
    """Прозрачный холст в SS раз крупнее итогового размера."""
    return pygame.Surface((width * SS, height * SS), pygame.SRCALPHA)


def shrink(surface: pygame.Surface, width: int, height: int) -> pygame.Surface:
    return pygame.transform.smoothscale(surface, (width, height))


def radial_disc(surface: pygame.Surface, center: tuple[float, float], radius: float, inner: Color, outer: Color,
                light: tuple[float, float] = (-0.35, -0.35)) -> None:
    """Шар/купол: круг с градиентом от светлой точки (light — смещение блика в долях радиуса)."""
    steps = max(8, int(radius))
    cx, cy = center
    for i in range(steps, 0, -1):
        t = i / steps
        r = radius * t
        offset = 1 - t
        pos = (cx + light[0] * radius * offset, cy + light[1] * radius * offset)
        pygame.draw.circle(surface, mix(inner, outer, t), pos, r)


def vertical_gradient_rect(surface: pygame.Surface, rect: pygame.Rect, top: Color, bottom: Color,
                           radius: int = 0) -> None:
    """Прямоугольник с вертикальным градиентом; radius — скругление углов."""
    layer = pygame.Surface(rect.size, pygame.SRCALPHA)
    for y in range(rect.height):
        pygame.draw.line(layer, mix(top, bottom, y / max(1, rect.height - 1)), (0, y), (rect.width, y))
    if radius:
        mask = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(mask, (255, 255, 255, 255), mask.get_rect(), border_radius=radius)
        layer.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    surface.blit(layer, rect)


def bevel_polygon(surface: pygame.Surface, points: list[tuple[float, float]], base: Color,
                  edge_light: Color | None = None, edge_dark: Color | None = None, width: int = 2) -> None:
    """Многоугольник с объёмом: заливка, светлая кромка сверху-слева и тёмная снизу-справа."""
    pygame.draw.polygon(surface, base, points)
    light = edge_light or mix(base, (255, 255, 255), 0.35)
    dark = edge_dark or mix(base, (0, 0, 0), 0.45)
    n = len(points)
    for i in range(n):
        a, b = points[i], points[(i + 1) % n]
        normal_y = a[0] - b[0]  # грань смотрит вверх, если нормаль направлена вверх
        normal_x = b[1] - a[1]
        lit = (normal_x * -0.7 + normal_y * -0.7) > 0
        pygame.draw.line(surface, light if lit else dark, a, b, width)


def soft_shadow(sprite: pygame.Surface, blur: int, alpha: int = 120) -> pygame.Surface:
    """Мягкая тень по силуэту спрайта: тёмная копия, размытая gaussian_blur."""
    pad = blur * 2
    silhouette = pygame.mask.from_surface(sprite, 16).to_surface(
        setcolor=(10, 4, 2, alpha), unsetcolor=(0, 0, 0, 0)
    )
    padded = pygame.Surface((sprite.get_width() + pad * 2, sprite.get_height() + pad * 2), pygame.SRCALPHA)
    padded.blit(silhouette, (pad, pad))
    return pygame.transform.gaussian_blur(padded, blur)


def ellipse_shadow(width: int, height: int, alpha: int = 110, blur: int = 4) -> pygame.Surface:
    """Размытый эллипс — тень под юнитом или зданием."""
    pad = blur * 2
    surface = pygame.Surface((width + pad * 2, height + pad * 2), pygame.SRCALPHA)
    pygame.draw.ellipse(surface, (10, 4, 2, alpha), (pad, pad, width, height))
    return pygame.transform.gaussian_blur(surface, blur)


def glow(radius: int, color: Color, strength: float = 1.0) -> pygame.Surface:
    """Пятно света для BLEND_ADD: яркое в центре и плавно гаснущее к краю."""
    surface = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
    for r in range(radius, 0, -1):
        t = 1 - r / radius
        k = (t ** 2) * strength
        pygame.draw.circle(surface, (int(color[0] * k), int(color[1] * k), int(color[2] * k), 255), (radius, radius), r)
    return surface


def soft_glow(radius: int, color: Color, alpha: int = 255) -> pygame.Surface:
    """Ореол для обычного blit (не BLEND_ADD): цвет один, непрозрачность растёт к центру."""
    surface = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
    for r in range(radius, 0, -1):
        t = 1 - r / radius
        pygame.draw.circle(surface, (*color, int(alpha * t ** 2)), (radius, radius), r)
    return surface


def rounded_panel(size: tuple[int, int], radius: int, fill: RGBA, border: RGBA | None = None,
                  top_light: bool = True) -> pygame.Surface:
    """Полупрозрачная скруглённая панель интерфейса с тонкой светлой кромкой сверху."""
    surface = pygame.Surface(size, pygame.SRCALPHA)
    rect = surface.get_rect()
    pygame.draw.rect(surface, fill, rect, border_radius=radius)
    if top_light:
        highlight = pygame.Surface(size, pygame.SRCALPHA)
        for y in range(min(size[1], radius * 3)):
            a = int(40 * (1 - y / (radius * 3)))
            pygame.draw.line(highlight, (255, 255, 255, a), (0, y), (size[0], y))
        mask = pygame.Surface(size, pygame.SRCALPHA)
        pygame.draw.rect(mask, (255, 255, 255, 255), rect, border_radius=radius)
        highlight.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
        surface.blit(highlight, (0, 0))
    if border:
        pygame.draw.rect(surface, border, rect, width=1, border_radius=radius)
    return surface


def rotated_variants(sprite: pygame.Surface, count: int = 16, scale: float = 1.0) -> list[pygame.Surface]:
    """Повороты спрайта (смотрит вправо = 0 рад) на count углов, со сглаживанием rotozoom."""
    return [pygame.transform.rotozoom(sprite, -360 * i / count, scale) for i in range(count)]


def angle_index(angle_rad: float, count: int = 16) -> int:
    return round((angle_rad % math.tau) / math.tau * count) % count
