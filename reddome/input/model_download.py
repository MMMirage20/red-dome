"""Модель жестов: где её искать и как скачать при первом запуске (сборка для itch.io).

Модель Google MediaPipe Gesture Recognizer в архив игры не входит: отдельной лицензии на неё нет
(README, «Сторонние ресурсы и лицензии»). Если модели нет ни в папке models/ рядом с игрой, ни в папке
пользователя, поток камеры качает её с официального адреса Google в папку пользователя
(%APPDATA%\\RedDome\\models или ~/.reddome/models) и сверяет SHA-256 — так же, как tools/download_models.py.
Только стандартная библиотека.
"""

from __future__ import annotations

import hashlib
import urllib.error
import urllib.request
from pathlib import Path

from reddome.profile import default_profile_path

#: Тот же адрес и хэш, что в tools/download_models.py (модель, с которой проверена игра, 8 373 440 байт).
GESTURE_URL = (
    "https://storage.googleapis.com/mediapipe-models/gesture_recognizer/gesture_recognizer/float16/latest/gesture_recognizer.task"
)
GESTURE_SHA256 = "97952348cf6a6a4915c2ea1496b4b37ebabc50cbbf80571435643c455f2b0482"
GESTURE_FILE_NAME = "gesture_recognizer.task"
TIMEOUT_SEC = 60
CHUNK_BYTES = 1 << 20
USER_AGENT = "red-dome-game"


class ModelDownloadError(Exception):
    """Понятная причина, почему модель не скачалась; показывается в оверлее жестов (F9)."""


def user_models_dir() -> Path:
    """Папка моделей пользователя — рядом с профилем игрока."""
    return default_profile_path().parent / "models"


def find_gesture_model(preferred: Path) -> Path | None:
    """Модель из настроек (models/ рядом с игрой) или уже скачанная в папку пользователя."""
    for path in (preferred, user_models_dir() / GESTURE_FILE_NAME):
        if path.is_file():
            return path
    return None


def download_gesture_model(dest: Path | None = None, url: str = GESTURE_URL, sha256: str = GESTURE_SHA256) -> Path:
    """Качает модель во временный файл, сверяет SHA-256 и только потом кладёт на место."""
    dest = dest or user_models_dir() / GESTURE_FILE_NAME
    part = dest.with_name(dest.name + ".part")
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        digest = hashlib.sha256()
        with urllib.request.urlopen(request, timeout=TIMEOUT_SEC) as response, part.open("wb") as out:
            for chunk in iter(lambda: response.read(CHUNK_BYTES), b""):
                out.write(chunk)
                digest.update(chunk)
    except (urllib.error.URLError, TimeoutError) as error:
        part.unlink(missing_ok=True)
        reason = getattr(error, "reason", error)
        raise ModelDownloadError(f"не скачалась модель жестов: {reason}. Нужен интернет при первом запуске") from error
    except OSError as error:
        part.unlink(missing_ok=True)
        raise ModelDownloadError(f"не записалась модель жестов в {dest.parent}: {error}") from error
    if digest.hexdigest() != sha256:
        part.unlink(missing_ok=True)
        raise ModelDownloadError("модель жестов на сервере изменилась (SHA-256 не совпал) — нужна новая версия игры")
    part.replace(dest)
    return dest
