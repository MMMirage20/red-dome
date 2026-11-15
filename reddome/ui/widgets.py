"""Кнопки, карточки и подсказки в стиле голографической панели (B4).

Фон кнопки — скруглённый градиент со светлой кромкой; при наведении — свечение акцентом.
Все состояния рисуются один раз и хранятся в кэше, в кадре только blit.
"""

from __future__ import annotations

from collections.abc import Callable

import pygame

from reddome.render.draw import rounded_panel, soft_glow
from reddome.ui import theme
from reddome.ui.icons import icon
from reddome.ui.theme import Color

_backgrounds: dict[tuple[int, int, str], pygame.Surface] = {}
_cards: dict[tuple[int, int, int], pygame.Surface] = {}


def button_background(size: tuple[int, int], state: str) -> pygame.Surface:
    """Фон кнопки: state — normal, hover, pressed или disabled."""
    key = (size[0], size[1], state)
    image = _backgrounds.get(key)
    if image is not None:
        return image
    w, h = size
    pad = 10
    image = pygame.Surface((w + pad * 2, h + pad * 2), pygame.SRCALPHA)
    if state == "hover":
        halo = pygame.transform.smoothscale(soft_glow(32, theme.ACCENT, 150), (w + pad * 2, h + pad * 2))
        image.blit(halo, (0, 0))
    top, bottom = {
        "normal": (theme.PANEL_LIGHT, theme.PANEL),
        "hover": (theme.mix(theme.PANEL_LIGHT, theme.ACCENT, 0.35), theme.PANEL_LIGHT),
        "pressed": (theme.PANEL, theme.PANEL_LIGHT),
        "disabled": (theme.mix(theme.PANEL, (40, 40, 40), 0.5), theme.PANEL),
    }[state]
    body = pygame.Surface((w, h), pygame.SRCALPHA)
    for y in range(h):
        pygame.draw.line(body, theme.mix(top, bottom, y / max(1, h - 1)), (0, y), (w, y))
    mask = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.rect(mask, (255, 255, 255, 255), mask.get_rect(), border_radius=10)
    body.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    border = theme.ACCENT if state in ("hover", "pressed") else theme.PANEL_EDGE
    if state == "disabled":
        border = theme.dim(theme.PANEL_EDGE, 0.6)
    pygame.draw.rect(body, border, body.get_rect(), width=2, border_radius=10)
    pygame.draw.line(body, (255, 255, 255, 50), (12, 3), (w - 12, 3))
    image.blit(body, (pad, pad))
    _backgrounds[key] = image
    return image


def card(size: tuple[int, int], radius: int = 14, alpha: int = 225) -> pygame.Surface:
    """Полупрозрачная скруглённая карточка для меню, паузы и итогов."""
    key = (size[0], size[1], radius * 1000 + alpha)
    image = _cards.get(key)
    if image is None:
        image = rounded_panel(size, radius, (*theme.PANEL, alpha), (*theme.PANEL_EDGE, 255))
        _cards[key] = image
    return image


class Button:
    def __init__(
        self,
        center: tuple[int, int],
        label: str,
        on_click: Callable[[], None],
        width: int = 300,
        enabled: bool = True,
        height: int = 52,
    ) -> None:
        self.rect = pygame.Rect(0, 0, width, height)
        self.rect.center = center
        self.label = label
        self.on_click = on_click
        self.enabled = enabled
        self._pressed = False
        #: Кнопка выбрана жестом (меню без мыши): рисуется как наведённая.
        self.focused = False

    def handle_event(self, event: pygame.event.Event) -> bool:
        """True, если клик пришёлся на кнопку."""
        if not self.enabled:
            return False
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self.rect.collidepoint(event.pos):
            self._pressed = True
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            pressed, self._pressed = self._pressed, False
            if self.rect.collidepoint(event.pos) and pressed:
                self.on_click()
                return True
        return False

    def draw(self, surface: pygame.Surface) -> None:
        hovered = self.enabled and (self.focused or self.rect.collidepoint(pygame.mouse.get_pos()))
        if not self.enabled:
            state = "disabled"
        elif hovered and self._pressed:
            state = "pressed"
        else:
            state = "hover" if hovered else "normal"
        background = button_background(self.rect.size, state)
        surface.blit(background, (self.rect.x - 10, self.rect.y - 10))
        color = theme.TEXT if self.enabled else theme.dim(theme.TEXT, 0.55)
        offset = 1 if state == "pressed" else 0
        theme.draw_text(surface, self.label, (self.rect.centerx, self.rect.centery + offset), 22, color,
                        anchor="center", shadow=self.enabled)


def draw_tooltip(surface: pygame.Surface, title: str, lines: list[tuple[str, Color]], anchor: tuple[int, int],
                 cost: int | None = None, cost_ok: bool = True, hotkey: str = "") -> None:
    """Подсказка над точкой anchor (нижний правый угол прижимается к экрану)."""
    title_surface = theme.render_text(title, 18, theme.TEXT, "title")
    width = title_surface.get_width() + (60 if hotkey else 0)
    for text, _ in lines:
        width = max(width, theme.render_text(text, 15).get_width())
    width = max(width + 24, 180)
    height = 16 + 24 + 20 * len(lines) + (24 if cost is not None else 0) + 4
    rect = pygame.Rect(0, 0, width, height)
    rect.bottomright = anchor
    rect.clamp_ip(surface.get_rect().inflate(-8, -8))
    surface.blit(rounded_panel(rect.size, 8, (*theme.PANEL, 240), (*theme.ACCENT, 255)), rect)
    surface.blit(title_surface, (rect.x + 12, rect.y + 8))
    if hotkey:
        theme.draw_text(surface, f"[{hotkey}]", (rect.right - 12, rect.y + 10), 16, theme.WARNING, anchor="topright", kind="title")
    y = rect.y + 36
    if cost is not None:
        surface.blit(icon("metal", 20), (rect.x + 10, y - 1))
        theme.draw_text(surface, str(cost), (rect.x + 34, y), 16, theme.TEXT if cost_ok else theme.ALARM, kind="title")
        y += 24
    for text, color in lines:
        theme.draw_text(surface, text, (rect.x + 12, y), 15, color)
        y += 20
