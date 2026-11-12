"""Запуск игры: python -m reddome [--debug] [--seed N] [--low] [--no-particles] [--no-shadows] [--no-daynight]
[--camera N] [--no-gestures] [--gesture-keys] [--swap-hands] [--profile ФАЙЛ]."""

from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path

from reddome.app import App
from reddome.config.camera import CameraSettings
from reddome.config.graphics import GraphicsSettings
from reddome.profile import Profile, default_profile_path


def graphics_from_args(args: argparse.Namespace) -> GraphicsSettings:
    graphics = GraphicsSettings.low() if args.low else GraphicsSettings()
    if args.no_particles:
        graphics = replace(graphics, particles=False)
    if args.no_shadows:
        graphics = replace(graphics, shadows=False)
    if args.no_daynight:
        graphics = replace(graphics, day_night=False)
    return replace(graphics, show_fps=args.debug)


def camera_from_args(args: argparse.Namespace) -> CameraSettings:
    return CameraSettings(
        enabled=not args.no_gestures,
        index=args.camera,
        swap_hands=args.swap_hands,
        keys=args.gesture_keys or args.debug,
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m reddome", description="Красный купол")
    parser.add_argument("--debug", action="store_true", help="FPS в углу и отладочные клавиши: K — победа, L — поражение")
    parser.add_argument("--seed", type=int, default=1, help="seed карты (по умолчанию 1)")
    parser.add_argument("--low", action="store_true", help="слабый ноутбук: без частиц, теней и смены дня и ночи")
    parser.add_argument("--no-particles", action="store_true", help="без частиц и эффектов")
    parser.add_argument("--no-shadows", action="store_true", help="без теней")
    parser.add_argument("--no-daynight", action="store_true", help="без смены дня и ночи")
    parser.add_argument("--camera", type=int, default=0, metavar="N", help="номер камеры для жестов (по умолчанию 0)")
    parser.add_argument("--no-gestures", action="store_true", help="не включать камеру и жесты")
    parser.add_argument("--gesture-keys", action="store_true", help="эмуляция жестов клавишами F1–F8 (включена и в --debug)")
    parser.add_argument("--swap-hands", action="store_true", help="поменять левую и правую руку, если камера их путает")
    parser.add_argument("--profile", type=Path, default=None, metavar="ФАЙЛ",
                        help="файл профиля SQLite: покупки и результаты (по умолчанию — в папке пользователя)")
    args = parser.parse_args(argv)
    profile = Profile(args.profile or default_profile_path())
    App(debug=args.debug, seed=args.seed, graphics=graphics_from_args(args), camera=camera_from_args(args),
        profile=profile).run()


if __name__ == "__main__":
    main()
