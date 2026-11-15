"""Точка входа сборки PyInstaller (tools/build_windows.py): та же игра, что python -m reddome.

В сборке без консоли упавшая игра закрылась бы молча, поэтому ошибка пишется в crash.log рядом
с профилем игрока и показывается окном Windows.
"""

from __future__ import annotations

import sys
import traceback


def selftest(report_path: str) -> None:
    """RedDome.exe --selftest ФАЙЛ: проверка сборки без окна — импорты, модель жестов, распознаватель."""
    lines = []
    try:
        import cv2
        import mediapipe as mp
        import numpy as np
        from mediapipe.tasks.python import vision
        from mediapipe.tasks.python.core.base_options import BaseOptions

        lines.append(f"imports ok: cv2 {cv2.__version__}, mediapipe {mp.__version__}")
        from reddome.config.camera import CameraSettings
        from reddome.input.model_download import download_gesture_model, find_gesture_model

        model = find_gesture_model(CameraSettings().model_path) or download_gesture_model()
        lines.append(f"model ok: {model} ({model.stat().st_size} bytes)")
        options = vision.GestureRecognizerOptions(base_options=BaseOptions(model_asset_path=str(model)),
                                                  running_mode=vision.RunningMode.IMAGE, num_hands=2)
        with vision.GestureRecognizer.create_from_options(options) as recognizer:
            frame = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.zeros((240, 320, 3), dtype=np.uint8))
            result = recognizer.recognize(frame)
        lines.append(f"recognizer ok: hands on blank frame = {len(result.gestures)}")
        from reddome.config.balance import load_balance

        balance = load_balance()
        lines.append(f"balance ok: missions {sorted(balance.missions)}")
    except BaseException:  # noqa: BLE001 — отчёт для разработчика
        lines.append("FAILED:\n" + traceback.format_exc())
    with open(report_path, "w", encoding="utf-8") as file:
        file.write("\n".join(lines) + "\n")


def run() -> None:
    if len(sys.argv) == 3 and sys.argv[1] == "--selftest":
        selftest(sys.argv[2])
        return
    try:
        from reddome.__main__ import main

        main()
    except SystemExit:
        raise
    except BaseException:  # noqa: BLE001 — любая ошибка должна попасть в crash.log
        text = traceback.format_exc()
        try:
            from reddome.profile import default_profile_path

            log = default_profile_path().parent / "crash.log"
            log.parent.mkdir(parents=True, exist_ok=True)
            log.write_text(text, encoding="utf-8")
            where = str(log)
        except OSError:
            where = "(не удалось записать crash.log)"
        if sys.platform == "win32":
            import ctypes

            ctypes.windll.user32.MessageBoxW(None, f"Игра завершилась с ошибкой.\nПодробности: {where}\n\n{text[-600:]}",
                                             "Красный купол", 0x10)
        raise


if __name__ == "__main__":
    run()
