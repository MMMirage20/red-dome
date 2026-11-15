"""Выбор миссии (W3-01, ФТ-02, ФТ-15): миссия 1 открыта, замки на 2–3 ведут в магазин. SDL dummy."""

from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from collections.abc import Iterator  # noqa: E402

import pygame  # noqa: E402
import pytest  # noqa: E402

from reddome.app import App  # noqa: E402
from reddome.scenes.game import GameScene  # noqa: E402
from reddome.scenes.menu import MenuScene  # noqa: E402
from reddome.scenes.missions import MISSIONS, MissionsScene  # noqa: E402
from reddome.scenes.shop import ShopScene  # noqa: E402

FRAME_MS = 1000 / 60


@pytest.fixture(scope="module")
def app() -> Iterator[App]:
    application = App(window_flags=0)
    yield application
    pygame.quit()


def open_scene(app: App, name: str, **data: object) -> object:
    app.start(name, **data)
    app.step(FRAME_MS, [])
    return app.top


def click(app: App, pos: tuple[int, int]) -> None:
    app.step(FRAME_MS, [
        pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos),
        pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=pos),
    ])
    app.step(FRAME_MS, [])


def test_only_first_mission_is_unlocked() -> None:
    assert [m.number for m in MISSIONS] == [1, 2, 3]
    assert [m.free for m in MISSIONS] == [True, False, False]


def test_menu_play_opens_mission_select(app: App) -> None:
    menu = open_scene(app, "menu")
    assert isinstance(menu, MenuScene)
    assert [b.label for b in menu.buttons][0] == "Играть"
    click(app, menu.buttons[0].rect.center)
    assert isinstance(app.top, MissionsScene)


def test_start_mission_one(app: App) -> None:
    scene = open_scene(app, "missions")
    assert isinstance(scene, MissionsScene)
    click(app, scene.play_button.rect.center)
    assert isinstance(app.top, GameScene)


@pytest.mark.parametrize("number", [2, 3])
def test_locked_mission_leads_to_shop_and_back(app: App, number: int) -> None:
    scene = open_scene(app, "missions")
    assert isinstance(scene, MissionsScene)
    click(app, scene.lock_buttons[number].rect.center)
    shop = app.top
    assert isinstance(shop, ShopScene)
    assert shop.back.label == "Назад к миссиям"
    click(app, shop.back.rect.center)
    assert isinstance(app.top, MissionsScene)


def test_click_on_locked_card_body_opens_shop(app: App) -> None:
    scene = open_scene(app, "missions")
    assert isinstance(scene, MissionsScene)
    mission, rect = scene.cards[1]
    assert not mission.free
    click(app, (rect.centerx, rect.y + 90))
    assert isinstance(app.top, ShopScene)


def test_escape_returns_to_menu(app: App) -> None:
    open_scene(app, "missions")
    app.step(FRAME_MS, [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, mod=0, unicode="")])
    app.step(FRAME_MS, [])
    assert isinstance(app.top, MenuScene)


def test_result_shows_score(app: App) -> None:
    from reddome.scenes.result import ResultScene
    from reddome.sim.score import Score, ScoreLine
    from reddome.sim.types import Outcome

    score = Score((ScoreLine("win", "Победа", 1, 1000), ScoreLine("killed_unit", "Враги", 3, 20),
                   ScoreLine("lost_colonist", "Погибшие колонисты", 0, -200)))
    result = open_scene(app, "result", outcome=Outcome(winner="player", reason="dome_destroyed"), score=score)
    assert isinstance(result, ResultScene)
    assert result.score_text == "Очки: 1 060"
    assert result.score_parts == ["Победа +1000", "Враги 3×20"]
