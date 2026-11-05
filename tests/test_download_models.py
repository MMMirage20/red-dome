"""tools/download_models.py без сети: источник — локальный файл по адресу file://."""

from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

import pytest

from tools import download_models as dm


def _source(tmp_path: Path, name: str, data: bytes) -> tuple[str, str]:
    """Кладёт файл-«сервер» и возвращает его file:// адрес и SHA-256."""
    src = tmp_path / "server" / name
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_bytes(data)
    return src.as_uri(), hashlib.sha256(data).hexdigest()


def _zip_source(tmp_path: Path, members: dict[str, bytes]) -> tuple[str, str]:
    archive = tmp_path / "server" / "model.zip"
    archive.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return archive.as_uri(), dm.sha256_of(archive)


def _quiet(_: str) -> None:
    pass


def test_constants_pin_gesture_model() -> None:
    assert dm.GESTURE_URL.startswith("https://") and dm.GESTURE_URL.endswith(".task")
    assert len(dm.GESTURE_SHA256) == 64 and int(dm.GESTURE_SHA256, 16) >= 0
    assert dm.VOSK_URL.startswith("https://") and dm.VOSK_URL.endswith(f"{dm.VOSK_MODEL_NAME}.zip")
    assert dm.GESTURE_FILE == dm.MODELS_DIR / "gesture_recognizer.task"
    assert dm.VOSK_DIR == dm.MODELS_DIR / "vosk"


def test_fetch_file_downloads_and_verifies(tmp_path: Path) -> None:
    url, sha = _source(tmp_path, "m.task", b"model-bytes")
    dest = tmp_path / "models" / "m.task"
    assert dm.fetch_file(url, dest, sha, log=_quiet) == "downloaded"
    assert dest.read_bytes() == b"model-bytes"
    assert not dest.with_name("m.task.part").exists()


def test_fetch_file_skips_verified_file_without_network(tmp_path: Path) -> None:
    url, sha = _source(tmp_path, "m.task", b"model-bytes")
    dest = tmp_path / "models" / "m.task"
    dm.fetch_file(url, dest, sha, log=_quiet)
    (tmp_path / "server" / "m.task").unlink()  # «сервер» пропал: повторный запуск не должен качать
    assert dm.fetch_file(url, dest, sha, log=_quiet) == "skipped"


def test_fetch_file_wrong_hash_leaves_nothing(tmp_path: Path) -> None:
    url, _ = _source(tmp_path, "m.task", b"model-bytes")
    dest = tmp_path / "models" / "m.task"
    with pytest.raises(dm.DownloadError, match="SHA-256 не совпадает"):
        dm.fetch_file(url, dest, "0" * 64, log=_quiet)
    assert not dest.exists()
    assert not dest.with_name("m.task.part").exists()


def test_fetch_file_replaces_corrupted_file(tmp_path: Path) -> None:
    url, sha = _source(tmp_path, "m.task", b"model-bytes")
    dest = tmp_path / "models" / "m.task"
    dest.parent.mkdir(parents=True)
    dest.write_bytes(b"broken")
    assert dm.fetch_file(url, dest, sha, log=_quiet) == "downloaded"
    assert dest.read_bytes() == b"model-bytes"


def test_fetch_file_without_pinned_hash_reports_it(tmp_path: Path) -> None:
    url, sha = _source(tmp_path, "m.task", b"model-bytes")
    lines: list[str] = []
    dm.fetch_file(url, tmp_path / "m.task", "", log=lines.append)
    assert any(sha in line for line in lines)


def test_missing_source_is_a_clear_error(tmp_path: Path) -> None:
    url = (tmp_path / "нет-такого.task").as_uri()
    dest = tmp_path / "models" / "m.task"
    with pytest.raises(dm.DownloadError, match="Не удалось скачать"):
        dm.fetch_file(url, dest, "0" * 64, log=_quiet)
    assert not dest.exists()


def test_fetch_zip_extracts_marks_and_skips(tmp_path: Path) -> None:
    url, sha = _zip_source(tmp_path, {"vosk-small/am/final.mdl": b"am", "vosk-small/conf/model.conf": b"conf"})
    target = tmp_path / "models" / "vosk"
    assert dm.fetch_zip(url, target, "vosk-small", sha, log=_quiet) == "downloaded"
    model = target / "vosk-small"
    assert (model / "am" / "final.mdl").read_bytes() == b"am"
    assert (model / dm.MARKER_NAME).read_text(encoding="utf-8").strip() == sha
    assert sorted(p.name for p in target.iterdir()) == ["vosk-small"]  # ни .part, ни временной папки
    assert dm.fetch_zip(url, target, "vosk-small", sha, log=_quiet) == "skipped"


def test_fetch_zip_redownloads_when_pinned_hash_changes(tmp_path: Path) -> None:
    url, sha = _zip_source(tmp_path, {"vosk-small/a.txt": b"a"})
    target = tmp_path / "vosk"
    dm.fetch_zip(url, target, "vosk-small", "", log=_quiet)
    # Хэш вписали после первого скачивания: маркер совпадает, качать не нужно.
    assert dm.fetch_zip(url, target, "vosk-small", sha, log=_quiet) == "skipped"
    assert dm.fetch_zip(url, target, "vosk-small", sha, force=True, log=_quiet) == "downloaded"


def test_fetch_zip_rejects_path_traversal(tmp_path: Path) -> None:
    url, sha = _zip_source(tmp_path, {"../evil.txt": b"x"})
    target = tmp_path / "models" / "vosk"
    with pytest.raises(dm.DownloadError, match="подозрительный путь"):
        dm.fetch_zip(url, target, "vosk-small", sha, log=_quiet)
    assert not (tmp_path / "models" / "evil.txt").exists()
    assert not (target / "vosk-small").exists()


def test_fetch_zip_wrong_hash_keeps_old_model(tmp_path: Path) -> None:
    url, sha = _zip_source(tmp_path, {"vosk-small/a.txt": b"a"})
    target = tmp_path / "vosk"
    dm.fetch_zip(url, target, "vosk-small", sha, log=_quiet)
    with pytest.raises(dm.DownloadError):
        dm.fetch_zip(url, target, "vosk-small", "f" * 64, force=True, log=_quiet)
    assert (target / "vosk-small" / "a.txt").read_bytes() == b"a"


@pytest.mark.parametrize(
    ("argv", "expected"),
    [([], ["gestures", "voice"]), (["--gestures"], ["gestures"]), (["--voice"], ["voice"]), (["--gestures", "--voice"], ["gestures", "voice"])],
)
def test_main_flags_choose_models(monkeypatch: pytest.MonkeyPatch, argv: list[str], expected: list[str]) -> None:
    calls: list[str] = []
    monkeypatch.setattr(dm, "fetch_gestures", lambda force=False: calls.append("gestures") or "skipped")
    monkeypatch.setattr(dm, "fetch_voice", lambda force=False: calls.append("voice") or "skipped")
    assert dm.main(argv) == 0
    assert calls == expected


def test_main_returns_error_code_and_continues(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    def broken(force: bool = False) -> str:
        raise dm.DownloadError("нет сети")

    calls: list[str] = []
    monkeypatch.setattr(dm, "fetch_gestures", broken)
    monkeypatch.setattr(dm, "fetch_voice", lambda force=False: calls.append("voice") or "skipped")
    assert dm.main([]) == 1
    assert calls == ["voice"]
    assert "нет сети" in capsys.readouterr().err
