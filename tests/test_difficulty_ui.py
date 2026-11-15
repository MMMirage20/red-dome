"""Сложность в интерфейсе (этап 2, S2-01): переключатель на выборе миссии (W3-01), строка на паузе и на итогах. SDL dummy."""

from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from collections.abc import Iterator  # noqa: E402

import pygame  # noqa: E402
import pytest  # noqa: E402

from reddome.app import App  # noqa: E402
from reddome.scenes.game import GameScene  # noqa: E402
from reddome.scenes.missions import MissionsScene  # noqa: E402
from reddome.scenes.pause import PauseScene  # noqa: E402
from reddome.scenes.result import ResultScene  # noqa: E402
from reddome.sim.types import Outcome  # noqa: E402

FRAME_MS = 1000 / 60


@pytest.fixture(scope="module")
def app() -> Iterator[App]:
    application = App(window_flags=0)
    yield application
    pygame.quit()


@pytest.fixture(autouse=True)
def normal_difficulty(app: App) -> Iterator[None]:
    app.difficulty = "normal"
    yield
    app.difficulty = "normal"


def open_scene(app: App, name: str, **data: object) -> object:
    app.start(name, **data)
    app.step(FRAME_MS, [])
    return app.top


def click(app: App, pos: tuple[int, int]) -> None:
    app.step(FRAME_MS, [
        pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos),
        pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=pos),
    ])


def test_menu_switch_cycles_difficulty(app: App) -> None:
    menu = open_scene(app, "missions")
    assert isinstance(menu, MissionsScene)
    assert "Обычный" in menu.difficulty_button.label
    click(app, menu.difficulty_button.rect.center)
    assert app.difficulty == "hard" and "Сложный" in menu.difficulty_button.label
    click(app, menu.difficulty_button.rect.center)
    assert app.difficulty == "easy" and "Лёгкий" in menu.difficulty_button.label
    app.step(FRAME_MS, [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_LEFT, mod=0, unicode="")])
    assert app.difficulty == "hard"
    app.step(FRAME_MS, [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RIGHT, mod=0, unicode="")])
    assert app.difficulty == "easy"


def test_game_starts_on_chosen_difficulty_and_pause_shows_it(app: App) -> None:
    app.difficulty = "easy"
    game = open_scene(app, "game")
    assert isinstance(game, GameScene)
    assert game.sim.state.difficulty == "easy"
    assert game.sim.balance.difficulty == "easy"
    app.step(FRAME_MS, [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, mod=0, unicode="")])
    app.step(FRAME_MS, [])
    pause = app.top
    assert isinstance(pause, PauseScene)
    assert pause.difficulty_text == "Сложность: Лёгкий"


def test_result_shows_difficulty(app: App) -> None:
    result = open_scene(app, "result", outcome=Outcome(winner="player", reason="dome_destroyed"), difficulty="hard")
    assert isinstance(result, ResultScene)
    assert result.difficulty_text == "Сложность: Сложный"
