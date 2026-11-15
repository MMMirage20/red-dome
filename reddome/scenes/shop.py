"""Магазин (ФТ-15; этап 3 — ФТ-33): «Полная экспедиция» покупается демо-оплатой и снимает замки с миссий 2–3.

Демо-оплата — окно подтверждения с честной пометкой, что деньги не списываются; покупка пишется в профиль
(reddome/profile.py) и восстанавливается при следующем запуске. Косметика — пока «Скоро». Каждый шаг
воронки (открыл магазин, увидел предложение, нажал «Купить», купил) пишется в профиль для ЛР14.
Сюда ведут замки миссий 2–3: тогда «Назад» возвращает к выбору миссии.
"""

from __future__ import annotations

from typing import Any

import pygame

from reddome.profile import FULL_EXPEDITION, PRODUCTS, Profile
from reddome.render.backdrop import starfield
from reddome.scenes.base import Scene
from reddome.ui import theme
from reddome.ui.icons import icon
from reddome.ui.widgets import Button, card

OFFERS = (
    (FULL_EXPEDITION, "Полная экспедиция", "Миссии 2–3 и режим «Схватка»", "1 490 ₸", "dome"),
    ("", "Скины купола и роверов", "Косметика без игрового преимущества", "290–590 ₸", "guard_rover"),
)
DEMO_NOTE = "Демо-оплата: деньги не списываются, покупка только открывает миссии в этой копии игры"


class ShopScene(Scene):
    def enter(self, back: str = "menu", **data: Any) -> None:
        self.sky = starfield(theme.SCREEN_SIZE, seed=11)
        self.back_to = "missions" if back == "missions" else "menu"
        title = "Назад к миссиям" if self.back_to == "missions" else "Назад в меню"
        w, _ = theme.SCREEN_SIZE
        self.back = Button((w // 2, 640), title, lambda: self.app.start(self.back_to))
        self.profile: Profile | None = getattr(self.app, "profile", None)
        self.confirming = False
        self.message = ""
        cx = w // 2
        self.offer_rects = []
        for i in range(len(OFFERS)):
            rect = pygame.Rect(0, 0, 400, 380)
            rect.center = (cx - 220 + 440 * i, 360)
            self.offer_rects.append(rect)
        first = self.offer_rects[0]
        self.buy = Button((first.centerx, first.bottom - 40), "Купить (демо)", self.ask_purchase, width=260, height=46)
        dialog = self.dialog_rect()
        self.pay = Button((dialog.centerx - 120, dialog.bottom - 46), "Оплатить (демо)", self.confirm, width=220, height=46)
        self.cancel = Button((dialog.centerx + 120, dialog.bottom - 46), "Отмена", self.close_dialog, width=200, height=46)
        if self.profile is not None:
            self.profile.log("shop_open")
            self.profile.log("offer_view", FULL_EXPEDITION)

    @staticmethod
    def dialog_rect() -> pygame.Rect:
        rect = pygame.Rect(0, 0, 640, 260)
        rect.center = (theme.SCREEN_SIZE[0] // 2, theme.SCREEN_SIZE[1] // 2)
        return rect

    @property
    def owned(self) -> bool:
        return self.profile is not None and self.profile.owns(FULL_EXPEDITION)

    def menu_buttons(self) -> list[Button]:
        if self.confirming:
            return [self.pay, self.cancel]
        return [self.back] if self.owned or self.profile is None else [self.buy, self.back]

    def menu_back(self) -> None:
        if self.confirming:
            self.close_dialog()
        else:
            self.app.start(self.back_to)

    def ask_purchase(self) -> None:
        if self.owned or self.profile is None:
            return
        self.profile.log("purchase_click", FULL_EXPEDITION)
        self.confirming = True

    def confirm(self) -> None:
        if self.profile is not None and self.profile.purchase_demo(FULL_EXPEDITION):
            self.message = "Готово: миссии 2–3 открыты"
        self.confirming = False

    def close_dialog(self) -> None:
        self.confirming = False

    def handle_event(self, event: pygame.event.Event) -> None:
        if self.confirming:
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self.close_dialog()
                return
            self.pay.handle_event(event)
            self.cancel.handle_event(event)
            return
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.app.start(self.back_to)
            return
        if not self.owned:
            self.buy.handle_event(event)
        self.back.handle_event(event)

    def draw(self, surface: pygame.Surface) -> None:
        surface.blit(self.sky, (0, 0))
        cx = theme.SCREEN_SIZE[0] // 2
        theme.draw_text(surface, "Магазин", (cx, 90), 52, theme.SAND, anchor="center", kind="title", shadow=True)
        for (product, title, description, price, picture), rect in zip(OFFERS, self.offer_rects, strict=True):
            surface.blit(card(rect.size), rect)
            surface.blit(icon(picture, 96), (rect.centerx - 48, rect.y + 26))
            theme.draw_text(surface, title, (rect.centerx, rect.y + 156), 26, theme.TEXT, anchor="center", kind="title")
            theme.draw_text(surface, description, (rect.centerx, rect.y + 194), 17, theme.TEXT_QUIET, anchor="center")
            theme.draw_text(surface, price, (rect.centerx, rect.y + 244), 32, theme.SAND, anchor="center", kind="title")
            if product == FULL_EXPEDITION and self.owned:
                self._badge(surface, (rect.centerx, rect.bottom - 40), "Куплено", theme.SUCCESS)
            elif product == FULL_EXPEDITION and self.profile is not None:
                self.buy.draw(surface)
            else:
                self._badge(surface, (rect.centerx, rect.bottom - 40), "Скоро", theme.ACCENT)
        if self.message:
            theme.draw_text(surface, self.message, (cx, 586), 20, theme.SUCCESS, anchor="center", kind="title")
        self.back.draw(surface)
        if self.confirming:
            self._draw_dialog(surface)

    @staticmethod
    def _badge(surface: pygame.Surface, center: tuple[int, int], text: str, color: theme.Color) -> None:
        badge = pygame.Rect(0, 0, 130, 32)
        badge.center = center
        pygame.draw.rect(surface, theme.PANEL_LIGHT, badge, border_radius=16)
        pygame.draw.rect(surface, color, badge, 1, border_radius=16)
        theme.draw_text(surface, text, badge.center, 16, color, anchor="center", kind="title")

    def _draw_dialog(self, surface: pygame.Surface) -> None:
        shade = pygame.Surface(theme.SCREEN_SIZE, pygame.SRCALPHA)
        shade.fill((0, 0, 0, 150))
        surface.blit(shade, (0, 0))
        rect = self.dialog_rect()
        surface.blit(card(rect.size), rect)
        product = PRODUCTS[FULL_EXPEDITION]
        price = f"{product.price_kzt:,}".replace(",", " ")
        theme.draw_text(surface, f"Купить «{product.title}» за {price} ₸?", (rect.centerx, rect.y + 52), 26,
                        theme.TEXT, anchor="center", kind="title")
        theme.draw_text(surface, product.description, (rect.centerx, rect.y + 96), 17, theme.TEXT_QUIET, anchor="center")
        theme.draw_text(surface, DEMO_NOTE, (rect.centerx, rect.y + 136), 15, theme.WARNING, anchor="center")
        self.pay.draw(surface)
        self.cancel.draw(surface)
