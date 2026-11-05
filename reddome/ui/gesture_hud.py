"""Обратная связь по жестам (W3-12, ФТ-14): индикатор удержания над портретом Аяна,
отладочный оверлей F9 и иконка камеры в верхней панели.

Превью камеры приходит numpy-массивом из потока камеры; Surface из него создаётся здесь,
в игровом потоке, и только для показа — на диск кадр не попадает.
"""

from __future__ import annotations

import math

import pygame

from reddome.input.gestures import COMMAND_TITLES, GESTURE_TITLES, HAND_TITLES, GestureFired, HoldState
from reddome.input.service import GestureService
from reddome.render.draw import rounded_panel
from reddome.ui import theme
from reddome.ui.hud import HUD_HEIGHT
from reddome.ui.icons import GESTURE_ICONS, icon
from reddome.ui.panel import IDLE_RECT, PANEL_TOP

INDICATOR_SIZE = (232, 46)
INDICATOR_LEFT = IDLE_RECT.right + 12
FLASH_MS = 700
OVERLAY_SIZE = (372, 196)
PREVIEW_SIZE = (160, 120)
CAMERA_ICON_POS = (1062, HUD_HEIGHT // 2 - 11)
HAND_SHORT = {"left": "Л", "right": "П"}

_panels: dict[tuple[int, int, bool], pygame.Surface] = {}


def _panel(size: tuple[int, int], lit: bool) -> pygame.Surface:
    key = (size[0], size[1], lit)
    image = _panels.get(key)
    if image is None:
        border = theme.SUCCESS if lit else theme.PANEL_EDGE
        image = rounded_panel(size, 10, (*theme.PANEL, 235), (*border, 255))
        _panels[key] = image
    return image


def _ring(surface: pygame.Surface, center: tuple[int, int], radius: int, progress: float, color: theme.Color) -> None:
    """Кольцо прогресса удержания: дуга от верха по часовой стрелке."""
    pygame.draw.circle(surface, (20, 30, 46), center, radius, 4)
    if progress <= 0:
        return
    steps = max(2, int(48 * progress))
    points = [
        (center[0] + math.sin(progress * math.tau * i / steps) * radius,
         center[1] - math.cos(progress * math.tau * i / steps) * radius)
        for i in range(steps + 1)
    ]
    pygame.draw.lines(surface, color, False, points, 4)


def describe(fired: GestureFired) -> str:
    """«ладонь, левая» — для подсказки о сработавшем жесте."""
    return f"{GESTURE_TITLES.get(fired.gesture, fired.gesture)}, {HAND_TITLES[fired.hand]}"


def draw_indicator(surface: pygame.Surface, service: GestureService, last: GestureFired | None,
                   fired_ms: float, now_ms: float) -> None:
    """Удержания рук над портретом (до двух плашек снизу вверх) и вспышка сработавшей команды."""
    holds: list[HoldState] = [h for h in service.holds() if not h.fired]
    flashing = last is not None and now_ms - fired_ms < FLASH_MS
    items: list[tuple[str, str, str, float, bool]] = [
        (h.gesture, h.hand, h.command, h.progress, False) for h in holds
    ]
    if flashing and last is not None:
        items.insert(0, (last.gesture, last.hand, last.command, 1.0, True))
    for i, (gesture, hand, command, progress, lit) in enumerate(items[:2]):
        rect = pygame.Rect(INDICATOR_LEFT, PANEL_TOP - 52 - i * (INDICATOR_SIZE[1] + 6), *INDICATOR_SIZE)
        surface.blit(_panel(INDICATOR_SIZE, lit), rect)
        center = (rect.x + 25, rect.centery)
        color = theme.SUCCESS if lit else theme.ACCENT
        _ring(surface, center, 19, progress, color)
        surface.blit(icon(GESTURE_ICONS[gesture], 28), (center[0] - 14, center[1] - 14))
        theme.draw_text(surface, f"{HAND_SHORT[hand]} · {GESTURE_TITLES[gesture]}", (rect.x + 52, rect.y + 5), 14,
                        theme.TEXT_QUIET)
        theme.draw_text(surface, COMMAND_TITLES[command], (rect.x + 52, rect.y + 22), 16,
                        theme.SUCCESS if lit else theme.TEXT, kind="title")


def draw_camera_icon(surface: pygame.Surface, service: GestureService) -> None:
    """Серая перечёркнутая — жесты с камеры не работают, жёлтая — запускается, зелёная — работает."""
    status = service.status
    name = "camera_on" if status == "running" else "camera_wait" if status == "starting" else "camera_off"
    surface.blit(icon(name, 22), CAMERA_ICON_POS)


def draw_overlay(surface: pygame.Surface, service: GestureService) -> None:
    """ФТ-14, клавиша F9: превью, жест, рука, уверенность, частота распознавания и статус."""
    rect = pygame.Rect(theme.SCREEN_SIZE[0] - OVERLAY_SIZE[0] - 12, HUD_HEIGHT + 10, *OVERLAY_SIZE)
    surface.blit(_panel(OVERLAY_SIZE, False), rect)
    preview = pygame.Rect(rect.x + 10, rect.y + 34, *PREVIEW_SIZE)
    pygame.draw.rect(surface, (6, 10, 16), preview)
    if service.preview is not None and service.camera is not None and service.status == "running":
        array = service.preview
        image = pygame.image.frombuffer(array.tobytes(), (array.shape[1], array.shape[0]), "RGB")
        surface.blit(pygame.transform.scale(image, PREVIEW_SIZE), preview)
    else:
        surface.blit(icon("camera_off", 36), (preview.centerx - 18, preview.centery - 26))
        theme.draw_text(surface, "нет кадра", (preview.centerx, preview.centery + 22), 14, theme.TEXT_QUIET, "center")
    pygame.draw.rect(surface, theme.PANEL_EDGE, preview, 1)
    theme.draw_text(surface, "Жесты · F9", (rect.x + 10, rect.y + 8), 17, theme.TEXT, kind="title")
    status_color = theme.SUCCESS if service.status == "running" else theme.WARNING if service.status == "starting" else theme.ALARM
    x = preview.right + 12
    lines: list[tuple[str, theme.Color]] = [
        (f"Камера: {service.status}", status_color),
        (f"Распознавание: {service.fps:.0f} к/с", theme.TEXT_QUIET),
        (f"Источник: {service.source or '—'}", theme.TEXT_QUIET),
    ]
    by_hand = {frame.hand: frame for frame in service.frames}
    for hand in ("left", "right"):
        frame = by_hand.get(hand)
        text = f"{HAND_SHORT[hand]}: {frame.gesture} {frame.score:.2f}" if frame is not None else f"{HAND_SHORT[hand]}: —"
        lines.append((text, theme.TEXT))
    if service.keys is not None:
        lines.append(("F1–F8 — эмуляция", theme.TEXT_QUIET))
    for i, (text, color) in enumerate(lines):
        theme.draw_text(surface, text, (x, preview.y + i * 20), 15, color)
    # Причина недоступности — во всю ширину под превью, чтобы длинный текст поместился.
    theme.draw_text(surface, service.status_text, (rect.x + 10, preview.bottom + 10), 14,
                    status_color if service.status != "running" else theme.TEXT_QUIET)
