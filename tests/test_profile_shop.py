"""Этап 3: профиль SQLite, демо-покупка «Полной экспедиции», замки миссий и «Следующая миссия» (ФТ-32–ФТ-34)."""

from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from collections.abc import Iterator  # noqa: E402
from pathlib import Path  # noqa: E402

import pygame  # noqa: E402
import pytest  # noqa: E402

from reddome.app import App  # noqa: E402
from reddome.profile import FULL_EXPEDITION, Profile  # noqa: E402
from reddome.scenes.game import GameScene  # noqa: E402
from reddome.scenes.missions import MissionsScene  # noqa: E402
from reddome.scenes.result import ResultScene  # noqa: E402
from reddome.scenes.shop import ShopScene  # noqa: E402
from reddome.sim.types import Outcome  # noqa: E402

FRAME_MS = 1000 / 60


def test_profile_purchase_unlocks_and_persists(tmp_path: Path) -> None:
    path = tmp_path / "p" / "profile.sqlite3"
    profile = Profile(path)
    assert profile.mission_unlocked(1) and not profile.mission_unlocked(2)
    assert profile.purchase_demo(FULL_EXPEDITION)
    assert not profile.purchase_demo(FULL_EXPEDITION)
    profile.close()
    again = Profile(path)
    assert again.owns(FULL_EXPEDITION) and again.mission_unlocked(3)
    assert again.funnel_counts()["purchase_done"] == 1


def test_profile_keeps_best_score_and_wins() -> None:
    profile = Profile()
    assert profile.best_score(1) is None
    profile.record_result(1, True, 1200)
    profile.record_result(1, False, 300)
    profile.record_result(1, True, 900)
    assert profile.best_score(1) == 1200
    assert profile.wins(1) == 2


def test_unknown_product_and_event_are_rejected() -> None:
    profile = Profile()
    with pytest.raises(ValueError):
        profile.purchase_demo("gold")
    with pytest.raises(ValueError):
        profile.log("clicked_somewhere")


@pytest.fixture
def app() -> Iterator[App]:
    application = App(window_flags=0, profile=Profile())
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


def test_demo_purchase_in_shop_unlocks_missions(app: App) -> None:
    shop = open_scene(app, "shop", back="missions")
    assert isinstance(shop, ShopScene)
    click(app, shop.buy.rect.center)
    assert shop.confirming
    click(app, shop.pay.rect.center)
    assert app.profile.owns(FULL_EXPEDITION) and shop.message
    counts = app.profile.funnel_counts()
    assert counts["shop_open"] == 1 and counts["purchase_click"] == 1 and counts["purchase_done"] == 1
    missions = open_scene(app, "missions")
    assert isinstance(missions, MissionsScene)
    assert set(missions.play_buttons) == {1, 2, 3} and not missions.lock_buttons
    click(app, missions.play_buttons[3].rect.center)
    game = app.top
    assert isinstance(game, GameScene) and game.sim.state.mission == 3
    assert type(game.bot).__name__ == "BotAdaptive"


def test_cancel_keeps_missions_locked(app: App) -> None:
    shop = open_scene(app, "shop")
    click(app, shop.buy.rect.center)
    click(app, shop.cancel.rect.center)
    assert not shop.confirming and not app.profile.owns(FULL_EXPEDITION)


def test_next_mission_leads_to_shop_when_locked(app: App) -> None:
    result = open_scene(app, "result", outcome=Outcome("player", "dome_destroyed"), mission=1)
    assert isinstance(result, ResultScene)
    assert [b.label for b in result.buttons] == ["Ещё раз", "Следующая миссия", "В меню"]
    assert app.profile.wins(1) == 1
    click(app, result.buttons[1].rect.center)
    assert isinstance(app.top, ShopScene)


def test_next_mission_starts_when_unlocked(app: App) -> None:
    app.profile.purchase_demo(FULL_EXPEDITION)
    result = open_scene(app, "result", outcome=Outcome("player", "ice_held"), mission=2)
    assert result.reason == "Ледяные поля удержаны"
    click(app, result.buttons[1].rect.center)
    assert isinstance(app.top, GameScene) and app.top.sim.state.mission == 3


def test_loss_has_no_next_mission(app: App) -> None:
    result = open_scene(app, "result", outcome=Outcome("vector", "great_dome"), mission=3)
    assert [b.label for b in result.buttons] == ["Ещё раз", "В меню"]
    assert result.reason == "ВЕКТОР первым построил Большой купол"
