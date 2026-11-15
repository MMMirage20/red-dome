"""Этап 3: жесты кулаком в игре и управление меню жестами (SDL dummy, без камеры)."""

from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from collections.abc import Iterator  # noqa: E402

import pygame  # noqa: E402
import pytest  # noqa: E402

from reddome.app import App  # noqa: E402
from reddome.input.keyboard import KEY_GESTURES  # noqa: E402
from reddome.profile import FULL_EXPEDITION, Profile  # noqa: E402
from reddome.scenes.game import GameScene  # noqa: E402
from reddome.scenes.menu import MenuScene  # noqa: E402
from reddome.scenes.missions import MissionsScene  # noqa: E402
from reddome.scenes.pause import PauseScene  # noqa: E402
from reddome.scenes.shop import ShopScene  # noqa: E402
from reddome.sim.state import add_building  # noqa: E402
from tests.helpers import open_spot  # noqa: E402
from tests.test_gesture_commands import FRAME_MS, FakeSource, show  # noqa: E402


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch) -> Iterator[App]:
    monkeypatch.setattr(pygame.mouse, "get_focused", lambda: False)
    monkeypatch.setattr(pygame.mouse, "get_pos", lambda: (5, 5))
    application = App(window_flags=0, profile=Profile())
    yield application
    pygame.quit()


@pytest.fixture
def source(app: App) -> FakeSource:
    fake = FakeSource()
    app.gestures.use_source(fake)
    app.gestures.mapper.reset()
    return fake


def open_scene(app: App, name: str, **data: object) -> object:
    app.start(name, **data)
    app.step(FRAME_MS, [])
    return app.top


def short(app: App) -> int:
    return app.balance.gestures.hold_ms


def long(app: App) -> int:
    return app.balance.gestures.attack_hold_ms


def test_fist_keys_emulate_gestures() -> None:
    assert KEY_GESTURES[pygame.K_F10] == ("Closed_Fist", "left")
    assert KEY_GESTURES[pygame.K_F11] == ("Closed_Fist", "right")


def test_left_fist_sends_idle_drones_to_construction(app: App, source: FakeSource) -> None:
    game = open_scene(app, "game")
    assert isinstance(game, GameScene)
    state = game.sim.state
    spot = open_spot(state, state.map.bases["player"])
    site = add_building(state, game.sim.balance, "player", "solar", spot, complete=False)
    for drone in game.player_units("drone"):
        drone.task = "idle"
    show(app, source, "Closed_Fist", "left", long(app))
    builders = [u for u in state.units if u.target_id == site.id and u.task in ("to_site", "building")]
    assert len(builders) == len(game.player_units("drone"))
    assert "стройку" in game.hint


def test_left_fist_without_sites_explains(app: App, source: FakeSource) -> None:
    game = open_scene(app, "game")
    show(app, source, "Closed_Fist", "left", long(app))
    assert "Стройплощадок нет" in game.hint


def test_right_fist_trains_rocket_rover_in_mission_two(app: App, source: FakeSource) -> None:
    app.profile.purchase_demo(FULL_EXPEDITION)
    game = open_scene(app, "game", mission=2)
    state, balance = game.sim.state, game.sim.balance
    state.colonies["player"].resources["metal"] = 1000
    base = state.map.bases["player"]
    for type_ in ("oxy_gen", "hangar"):
        add_building(state, balance, "player", type_, open_spot(state, base))
    show(app, source, "Closed_Fist", "right", long(app))
    assert "реактор" in game.hint  # без реактора — объяснение
    add_building(state, balance, "player", "reactor", open_spot(state, base))
    show(app, source, "Closed_Fist", "right", long(app))
    hangar = next(b for b in state.buildings if b.type == "hangar" and b.side == "player")
    assert [item.type for item in hangar.queue] == ["rocket_rover"]


def test_menu_is_playable_with_gestures(app: App, source: FakeSource) -> None:
    menu = open_scene(app, "menu")
    assert isinstance(menu, MenuScene)
    show(app, source, "Open_Palm", "right", short(app))  # фокус на первой кнопке — «Играть»
    assert menu.buttons[0].focused
    show(app, source, "Thumb_Up", "right", short(app))
    missions = app.top
    assert isinstance(missions, MissionsScene)
    show(app, source, "Open_Palm", "right", short(app))
    assert missions.play_button.focused
    show(app, source, "Thumb_Up", "right", short(app))
    assert isinstance(app.top, GameScene) and app.top.sim.state.mission == 1


def test_palm_left_wraps_and_thumb_down_goes_back(app: App, source: FakeSource) -> None:
    missions = open_scene(app, "missions")
    show(app, source, "Open_Palm", "right", short(app))
    show(app, source, "Open_Palm", "left", short(app))
    enabled = [b for b in missions.buttons if b.enabled]
    assert enabled[-1].focused and sum(b.focused for b in missions.buttons) == 1
    show(app, source, "Thumb_Down", "right", short(app))
    assert isinstance(app.top, MenuScene)


def test_demo_purchase_with_gestures(app: App, source: FakeSource) -> None:
    shop = open_scene(app, "shop", back="missions")
    assert isinstance(shop, ShopScene)
    show(app, source, "Thumb_Up", "right", short(app))  # первый жест только выбирает «Купить (демо)»
    assert shop.buy.focused and not shop.confirming
    show(app, source, "Thumb_Up", "right", short(app))
    assert shop.confirming
    show(app, source, "Thumb_Up", "right", short(app))  # выбор «Оплатить (демо)»
    show(app, source, "Thumb_Up", "right", short(app))
    assert app.profile.owns(FULL_EXPEDITION)


def test_pause_menu_with_gestures(app: App, source: FakeSource) -> None:
    open_scene(app, "game")
    app.push("pause", background=None)
    app.step(FRAME_MS, [])
    assert isinstance(app.top, PauseScene)
    show(app, source, "Thumb_Down", "right", short(app))
    assert isinstance(app.top, GameScene)
