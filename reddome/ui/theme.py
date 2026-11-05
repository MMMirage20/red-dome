"""Палитра из Game Concept Document (раздел 7), шрифты и вывод текста."""

from __future__ import annotations

from pathlib import Path

import pygame

SCREEN_SIZE = (1280, 720)
TILE = 32
FPS = 60

Color = tuple[int, int, int]

# Основные цвета ГКД.
GROUND = (180, 71, 28)
GROUND_ALT = (188, 77, 32)
ROCK = (90, 30, 18)
ICE = (205, 235, 247)
ORE = (140, 140, 153)
PANEL = (15, 27, 45)
ACCENT = (79, 195, 247)
SAND = (232, 177, 122)
TEXT = (245, 240, 235)
TEXT_QUIET = (207, 216, 227)
ALARM = (255, 77, 79)
SUCCESS = (123, 199, 77)
PLAYER = (245, 240, 235)
PLAYER_OUTLINE = (193, 68, 14)
VECTOR = (28, 28, 34)
VECTOR_OUTLINE = (181, 23, 158)

# Расширенные оттенки (основные цвета выше не меняются).
RUST_DARK = (122, 44, 18)
RUST_MID = (161, 63, 26)
RUST_LIGHT = (204, 104, 52)
DUST = (226, 160, 112)
PANEL_LIGHT = (28, 46, 72)
PANEL_EDGE = (58, 98, 140)
WARNING = (255, 201, 60)
ENERGY = (255, 201, 60)
WATER = (58, 134, 255)
OXYGEN = (46, 196, 182)
METAL = (176, 184, 196)
HULL_PLAYER = (232, 228, 220)
HULL_PLAYER_DARK = (150, 146, 140)
HULL_VECTOR = (54, 54, 64)
HULL_VECTOR_DARK = (22, 22, 28)
TEAM_PLAYER = (243, 118, 44)
TEAM_VECTOR = (214, 46, 196)
GLASS = (120, 205, 240)

FONTS_DIR = Path(__file__).resolve().parents[2] / "assets" / "fonts"
#: Заголовки и числа — Russo One, текст — Exo 2 (OFL, см. assets/fonts). Без файлов — системный шрифт.
FONT_FILES = {"title": "RussoOne-Regular.ttf", "text": "Exo2-Variable.ttf"}
#: Системные шрифты с кириллицей на случай, если файлов нет или в шрифте нет символа.
SYSTEM_FONTS = "segoeui,arial,dejavusans"

_fonts: dict[tuple[str, int], pygame.font.Font] = {}
_fallback: dict[int, pygame.font.Font] = {}
_text_cache: dict[tuple[str, int, Color, str], pygame.Surface] = {}
TEXT_CACHE_LIMIT = 800


def reset_fonts() -> None:
    """Сбросить кэш шрифтов: после pygame.quit() старые объекты Font недействительны (новый App, тесты)."""
    _fonts.clear()
    _fallback.clear()
    _text_cache.clear()


def font(size: int, kind: str = "text") -> pygame.font.Font:
    key = (kind, size)
    if key not in _fonts:
        path = FONTS_DIR / FONT_FILES.get(kind, FONT_FILES["text"])
        _fonts[key] = pygame.font.Font(path, size) if path.exists() else _system_font(size)
    return _fonts[key]


def _system_font(size: int) -> pygame.font.Font:
    if size not in _fallback:
        _fallback[size] = pygame.font.SysFont(SYSTEM_FONTS, size)
    return _fallback[size]


def render_text(text: str, size: int = 20, color: Color = TEXT, kind: str = "text") -> pygame.Surface:
    """Текст с кэшем: одни и те же подписи не рендерятся заново каждый кадр."""
    key = (text, size, color, kind)
    cached = _text_cache.get(key)
    if cached is not None:
        return cached
    chosen = font(size, kind)
    if any(m is None for m in chosen.metrics(text)):
        chosen = _system_font(size)  # в шрифте нет какого-то символа
    surface = chosen.render(text, True, color)
    if len(_text_cache) > TEXT_CACHE_LIMIT:
        _text_cache.clear()
    _text_cache[key] = surface
    return surface


def draw_text(
    surface: pygame.Surface,
    text: str,
    pos: tuple[float, float],
    size: int = 20,
    color: Color = TEXT,
    anchor: str = "topleft",
    kind: str = "text",
    shadow: bool = False,
) -> pygame.Rect:
    """Рисует строку текста; anchor — атрибут Rect: topleft, center, midtop, bottomright…"""
    rendered = render_text(text, size, color, kind)
    rect = rendered.get_rect(**{anchor: pos})
    if shadow:
        surface.blit(render_text(text, size, (0, 0, 0), kind), rect.move(1, 2))
    surface.blit(rendered, rect)
    return rect


def dim(color: Color, factor: float = 0.45) -> Color:
    """Приглушённый цвет — для отключённых зданий."""
    return (int(color[0] * factor), int(color[1] * factor), int(color[2] * factor))


def mix(a: Color, b: Color, t: float) -> Color:
    t = max(0.0, min(1.0, t))
    return (int(a[0] + (b[0] - a[0]) * t), int(a[1] + (b[1] - a[1]) * t), int(a[2] + (b[2] - a[2]) * t))


def team_color(side: str) -> Color:
    return TEAM_PLAYER if side == "player" else TEAM_VECTOR
