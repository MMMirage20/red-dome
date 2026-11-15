"""Сборка игры для Windows (itch.io): папка с RedDome.exe и zip-архив для загрузки.

    pip install -r requirements.txt -r requirements-ai.txt pyinstaller
    python -m tools.build_windows

Результат: dist/RedDome/RedDome.exe и dist/RedDome-windows.zip. Внутрь кладутся игра, balance.json,
модель стиля игрока (style_model.json), шрифты и mediapipe с OpenCV для жестов. Модели жестов в архиве
нет: игра скачает её с сервера Google при первом запуске (reddome/input/model_download.py).
scikit-learn, pandas, Vosk и тесты в сборку не попадают — игре они не нужны (matplotlib нужен: его импортирует mediapipe).
"""

from __future__ import annotations

import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
BUILD = ROOT / "build"
NAME = "RedDome"
ZIP_PATH = DIST / f"{NAME}-windows.zip"
LAUNCHER = Path(__file__).with_name("reddome_launcher.py")
EXCLUDES = ("sklearn", "scipy", "pandas", "pytest", "tkinter", "vosk", "sounddevice",
            "IPython", "jupyter", "joblib", "tools.sim_cli", "tools.train_style")

PLAYER_README = """Красный купол (Red Dome) — RTS о колонии на Марсе против ИИ «ВЕКТОР»

Запуск: распакуйте архив целиком и откройте RedDome.exe.
Windows может предупредить о неизвестном издателе: «Подробнее» → «Выполнить в любом случае».

Управление
  ЛКМ — выделить (рамкой — несколько), ПКМ — приказ: по руде — добывать, по врагу — атаковать, по земле — идти.
  B — строить (затем P, I, O, E, H, T, R, G — здание), Q — собрать дрона или ровера, Z — ракетный ровер,
  F — атака, G — добывать, X — стоп, «.» — свободный дрон, Ctrl+цифра — группа, стрелки или край экрана — камера,
  Esc — пауза (там же памятка по клавишам и жестам).

Жесты с веб-камеры (MediaPipe)
  При первом запуске игра скачивает модель жестов Google (8 МБ) — нужен интернет.
  Ладонь левой — выбрать дрона, ладонь правой — все роверы, указательный вверх — атака на купол ВЕКТОРа,
  большой палец вверх — дроны за работу, вниз — отступить, «победа» левой / правой — дрон / ровер,
  кулак левой — дроны на стройку, кулак правой — ракетный ровер, «I love you» — пауза.
  Без камеры жесты эмулируются клавишами F1–F8, F10, F11: запустите RedDome.exe --gesture-keys.

Профиль и покупки: %APPDATA%\\RedDome. Если игра закрылась с ошибкой — там же crash.log.
Исходный код: https://github.com/MMMirage20/red-dome
"""


def build() -> Path:
    import PyInstaller.__main__

    sep = ";" if sys.platform == "win32" else ":"
    datas = [
        (ROOT / "reddome" / "config" / "balance.json", "reddome/config"),
        (ROOT / "reddome" / "bot" / "style_model.json", "reddome/bot"),
        (ROOT / "assets", "assets"),
    ]
    args = [
        str(LAUNCHER),
        "--name", NAME,
        "--noconfirm",
        "--clean",
        "--windowed",
        "--distpath", str(DIST),
        "--workpath", str(BUILD),
        "--specpath", str(BUILD),
        "--paths", str(ROOT),
        "--collect-submodules", "reddome",
        "--collect-all", "mediapipe",
    ]
    for source, target in datas:
        args += ["--add-data", f"{source}{sep}{target}"]
    for module in EXCLUDES:
        args += ["--exclude-module", module]
    PyInstaller.__main__.run(args)
    folder = DIST / NAME
    (folder / "README_RU.txt").write_text(PLAYER_README, encoding="utf-8-sig")
    shutil.copy(ROOT / "LICENSE", folder / "LICENSE.txt")
    return folder


def make_zip(folder: Path) -> Path:
    ZIP_PATH.unlink(missing_ok=True)
    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                archive.write(path, Path(NAME) / path.relative_to(folder))
    return ZIP_PATH


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    folder = build()
    archive = make_zip(folder)
    print(f"Готово: {folder / (NAME + '.exe')}")
    print(f"Архив для itch.io: {archive} ({archive.stat().st_size / 2**20:.0f} МБ)")


if __name__ == "__main__":
    main()
