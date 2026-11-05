"""Скачивание моделей для жестов и голоса. Сами модели в git не хранятся.

Запуск из корня репозитория:

    python tools/download_models.py              # обе модели
    python tools/download_models.py --gestures   # только жесты (MediaPipe Gesture Recognizer)
    python tools/download_models.py --voice      # только голос (малая русская модель Vosk)
    python tools/download_models.py --force      # скачать заново, даже если всё на месте

Что делает: качает файл во временный *.part, сверяет SHA-256 с константой ниже и только потом
кладёт на место. Архив Vosk распаковывает в models/vosk/ и запоминает хэш проверенного архива,
чтобы при следующем запуске ничего не качать. Уже скачанное и проверенное пропускает.

Только стандартная библиотека (urllib, hashlib, zipfile): скрипт работает сразу после
pip install -r requirements.txt.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
import urllib.error
import urllib.request
import zipfile
from collections.abc import Callable, Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELS_DIR = ROOT / "models"

# Модель жестов: MediaPipe Gesture Recognizer, HandGestureClassifier float16.
# Официальная страница (раздел Models): https://developers.google.com/edge/mediapipe/solutions/vision/gesture_recognizer
# Страница даёт только адрес «latest». Если Google обновит модель, хэш перестанет совпадать —
# скрипт об этом скажет, а проверенный хэш нужно будет обновить здесь.
GESTURE_URL = (
    "https://storage.googleapis.com/mediapipe-models/gesture_recognizer/gesture_recognizer/float16/latest/gesture_recognizer.task"
)
# Посчитан по файлу 8 373 440 байт, с которым проверена игра (неделя 3).
GESTURE_SHA256 = "97952348cf6a6a4915c2ea1496b4b37ebabc50cbbf80571435643c455f2b0482"
GESTURE_FILE = MODELS_DIR / "gesture_recognizer.task"

# Малая русская модель Vosk, Apache 2.0. Список моделей: https://alphacephei.com/vosk/models
VOSK_URL = "https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip"
# TODO: вписать SHA-256 архива. Сайт контрольных сумм не публикует, а из среды, где писался скрипт,
# alphacephei.com был недоступен. Пока строка пустая, скрипт качает без сверки и печатает хэш —
# его нужно вписать сюда и закоммитить, после этого каждое скачивание проверяется.
VOSK_SHA256 = ""
VOSK_MODEL_NAME = "vosk-model-small-ru-0.22"
VOSK_DIR = MODELS_DIR / "vosk"

# Файл рядом с распакованной моделью: SHA-256 архива, из которого она распакована.
MARKER_NAME = ".download-sha256"
USER_AGENT = "red-dome-download-models"
TIMEOUT_SEC = 60
CHUNK_BYTES = 1 << 20

Log = Callable[[str], None]


class DownloadError(Exception):
    """Понятная ошибка для человека: что не так и что сделать."""


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download(url: str, dest: Path, log: Log) -> None:
    """Скачивает url в dest целиком. При любой ошибке dest удаляется."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    log(f"  качаю {url}")
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SEC) as response, dest.open("wb") as out:
            total = int(response.headers.get("Content-Length") or 0)
            done = 0
            for chunk in iter(lambda: response.read(CHUNK_BYTES), b""):
                out.write(chunk)
                done += len(chunk)
                if total and sys.stdout.isatty():
                    print(f"\r  {done * 100 // total:3d} %  {done // CHUNK_BYTES} из {total // CHUNK_BYTES} МБ", end="", flush=True)
            if total and sys.stdout.isatty():
                print()
        if total and done != total:
            raise DownloadError(f"Скачано {done} байт из {total}: соединение оборвалось. Запустите скрипт ещё раз.")
    except urllib.error.HTTPError as e:
        dest.unlink(missing_ok=True)
        raise DownloadError(f"Сервер ответил {e.code} {e.reason} на {url}. Проверьте адрес на официальной странице модели.") from e
    except urllib.error.URLError as e:
        dest.unlink(missing_ok=True)
        raise DownloadError(f"Не удалось скачать {url}: {e.reason}. Проверьте интернет, прокси или VPN.") from e
    except TimeoutError as e:
        dest.unlink(missing_ok=True)
        raise DownloadError(f"Сервер не ответил за {TIMEOUT_SEC} с: {url}. Попробуйте позже.") from e
    except DownloadError:
        dest.unlink(missing_ok=True)
        raise
    except OSError as e:
        dest.unlink(missing_ok=True)
        raise DownloadError(f"Не удалось записать {dest}: {e}. Хватает ли места на диске?") from e


def _check_hash(path: Path, expected: str, url: str) -> str:
    """Возвращает SHA-256 файла; при несовпадении с ожидаемым удаляет файл и бросает DownloadError."""
    actual = sha256_of(path)
    if expected and actual != expected.lower():
        path.unlink(missing_ok=True)
        raise DownloadError(
            f"SHA-256 не совпадает для {url}\n"
            f"    ожидали: {expected}\n"
            f"    получили: {actual}\n"
            "  Файл удалён. Если источник обновил модель, проверьте новую версию и обновите хэш в tools/download_models.py."
        )
    return actual


def fetch_file(url: str, dest: Path, sha256: str, *, force: bool = False, log: Log = print) -> str:
    """Качает один файл в dest с проверкой хэша. Возвращает "skipped" или "downloaded"."""
    if dest.exists() and not force:
        if not sha256:
            log(f"  {dest.name} уже есть (хэш не закреплён, проверить нечем) — пропускаю")
            return "skipped"
        if sha256_of(dest) == sha256.lower():
            log(f"  {dest.name} уже скачан и проверен — пропускаю")
            return "skipped"
        log(f"  {dest.name} есть, но хэш не совпадает — качаю заново")
    part = dest.with_name(dest.name + ".part")
    _download(url, part, log)
    actual = _check_hash(part, sha256, url)
    part.replace(dest)
    if not sha256:
        log(f"  SHA-256: {actual} — впишите его в tools/download_models.py, чтобы проверять следующие скачивания")
    log(f"  готово: {dest}")
    return "downloaded"


def _safe_extract(archive: zipfile.ZipFile, dest: Path) -> None:
    """Распаковка без выхода за пределы dest (защита от путей вида ../ и абсолютных)."""
    root = dest.resolve()
    for member in archive.infolist():
        target = (dest / member.filename).resolve()
        if target != root and root not in target.parents:
            raise DownloadError(f"В архиве подозрительный путь {member.filename!r} — распаковка остановлена.")
    archive.extractall(dest)


def _marker_ok(model_dir: Path, sha256: str) -> bool:
    marker = model_dir / MARKER_NAME
    if not model_dir.is_dir() or not marker.is_file():
        return False
    stored = marker.read_text(encoding="utf-8").strip()
    return not sha256 or stored == sha256.lower()


def fetch_zip(url: str, target_dir: Path, model_name: str, sha256: str, *, force: bool = False, log: Log = print) -> str:
    """Качает zip, проверяет хэш и распаковывает в target_dir/model_name. Возвращает "skipped" или "downloaded"."""
    model_dir = target_dir / model_name
    if not force and _marker_ok(model_dir, sha256):
        log(f"  {model_name} уже скачана и проверена — пропускаю")
        return "skipped"
    target_dir.mkdir(parents=True, exist_ok=True)
    part = target_dir / f"{model_name}.zip.part"
    unpack = target_dir / f"{model_name}.unpack"
    _download(url, part, log)
    try:
        actual = _check_hash(part, sha256, url)
        shutil.rmtree(unpack, ignore_errors=True)
        log("  распаковываю")
        try:
            with zipfile.ZipFile(part) as archive:
                _safe_extract(archive, unpack)
        except zipfile.BadZipFile as e:
            raise DownloadError(f"Скачанный файл не похож на zip: {url}. Запустите скрипт ещё раз.") from e
        extracted = unpack / model_name
        if not extracted.is_dir():
            # Архив без папки верхнего уровня: модель лежит прямо в корне архива.
            extracted = unpack
        shutil.rmtree(model_dir, ignore_errors=True)
        extracted.replace(model_dir)
        (model_dir / MARKER_NAME).write_text(actual + "\n", encoding="utf-8")
    finally:
        part.unlink(missing_ok=True)
        shutil.rmtree(unpack, ignore_errors=True)
    if not sha256:
        log(f"  SHA-256 архива: {actual} — впишите его в VOSK_SHA256 в tools/download_models.py")
    log(f"  готово: {model_dir}")
    return "downloaded"


def fetch_gestures(force: bool = False) -> str:
    print("Модель жестов (MediaPipe Gesture Recognizer):")
    return fetch_file(GESTURE_URL, GESTURE_FILE, GESTURE_SHA256, force=force)


def fetch_voice(force: bool = False) -> str:
    print("Модель голоса (Vosk, малая русская):")
    return fetch_zip(VOSK_URL, VOSK_DIR, VOSK_MODEL_NAME, VOSK_SHA256, force=force)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Скачать модели жестов и голоса в папку models/.")
    parser.add_argument("--gestures", action="store_true", help="только модель жестов MediaPipe")
    parser.add_argument("--voice", action="store_true", help="только малую русскую модель Vosk")
    parser.add_argument("--force", action="store_true", help="скачать заново, даже если всё уже на месте")
    args = parser.parse_args(argv)
    both = not args.gestures and not args.voice
    jobs: list[Callable[[bool], str]] = []
    if args.gestures or both:
        jobs.append(fetch_gestures)
    if args.voice or both:
        jobs.append(fetch_voice)

    failed = 0
    for job in jobs:
        try:
            job(args.force)
        except DownloadError as e:
            failed += 1
            print(f"  Ошибка: {e}", file=sys.stderr)
    if failed:
        print(f"Не скачано моделей: {failed}. Игра всё равно запускается — без моделей работают мышь и клавиатура.", file=sys.stderr)
        return 1
    print("Модели на месте.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
