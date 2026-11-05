"""Жесты (ФТ-13): порог уверенности, удержание по рукам, cooldown, выбор руки, swap_hands."""

from __future__ import annotations

from reddome.config.balance import Balance
from reddome.input.gestures import GestureCommand, GestureFrame, GestureMapper, Hand

STEP_MS = 50


def hold(
    mapper: GestureMapper, gesture: str, hand: Hand, from_ms: int, to_ms: int, score: float = 0.9
) -> list[GestureCommand]:
    """Держать один жест одной рукой с from_ms по to_ms включительно, кадр каждые STEP_MS."""
    commands = []
    for t in range(from_ms, to_ms + 1, STEP_MS):
        fired = mapper.feed([GestureFrame(gesture, score, t, hand)], t)
        if fired is not None:
            commands.append(fired.command)
    return commands


def test_low_confidence_is_ignored(balance: Balance) -> None:
    mapper = GestureMapper(balance.gestures)
    assert hold(mapper, "Open_Palm", "left", 0, 3000, score=balance.gestures.min_score - 0.1) == []


def test_open_palm_left_selects_drone_and_right_selects_rovers(balance: Balance) -> None:
    hold_ms = balance.gestures.hold_ms
    assert hold(GestureMapper(balance.gestures), "Open_Palm", "left", 0, hold_ms) == ["select_drone"]
    assert hold(GestureMapper(balance.gestures), "Open_Palm", "right", 0, hold_ms) == ["select_rovers"]


def test_victory_trains_drone_left_and_rover_right(balance: Balance) -> None:
    hold_ms = balance.gestures.hold_ms
    assert hold(GestureMapper(balance.gestures), "Victory", "left", 0, hold_ms) == ["train_drone"]
    assert hold(GestureMapper(balance.gestures), "Victory", "right", 0, hold_ms) == ["train_rover"]


def test_pointing_up_attacks_with_either_hand_only_after_attack_hold(balance: Balance) -> None:
    attack_ms = balance.gestures.attack_hold_ms
    assert attack_ms > balance.gestures.hold_ms
    for hand in ("left", "right"):
        mapper = GestureMapper(balance.gestures)
        assert hold(mapper, "Pointing_Up", hand, 0, attack_ms - STEP_MS) == []
        assert hold(mapper, "Pointing_Up", hand, attack_ms, attack_ms + 1000) == ["attack_base"]


def test_ily_pauses_after_pause_hold(balance: Balance) -> None:
    pause_ms = balance.gestures.pause_hold_ms
    mapper = GestureMapper(balance.gestures)
    assert hold(mapper, "ILoveYou", "right", 0, pause_ms - STEP_MS) == []
    assert hold(mapper, "ILoveYou", "right", pause_ms, pause_ms) == ["pause"]


def test_thumbs_give_gather_and_retreat_with_any_hand(balance: Balance) -> None:
    hold_ms = balance.gestures.hold_ms
    assert hold(GestureMapper(balance.gestures), "Thumb_Up", "left", 0, hold_ms) == ["gather"]
    assert hold(GestureMapper(balance.gestures), "Thumb_Down", "right", 0, hold_ms) == ["retreat"]


def test_one_hold_one_command_repeat_after_gesture_change(balance: Balance) -> None:
    mapper = GestureMapper(balance.gestures)
    assert hold(mapper, "Thumb_Up", "left", 0, 3000) == ["gather"]
    assert hold(mapper, "None", "left", 3050, 3200) == []
    assert hold(mapper, "Thumb_Up", "left", 3250, 5000) == ["gather"]


def test_cooldown_blocks_second_command(balance: Balance) -> None:
    spec = balance.gestures
    mapper = GestureMapper(spec)
    assert hold(mapper, "Open_Palm", "left", 0, spec.hold_ms) == ["select_drone"]
    fired_at = spec.hold_ms
    # Сразу другой жест той же рукой: порог удержания наступает раньше конца cooldown — команда сгорает.
    start = fired_at + STEP_MS
    assert start + spec.hold_ms < fired_at + spec.cooldown_ms
    assert hold(mapper, "Thumb_Up", "left", start, fired_at + spec.cooldown_ms + 1000) == []
    # После cooldown новое удержание снова работает.
    later = fired_at + spec.cooldown_ms + 2000
    assert hold(mapper, "None", "left", later, later) == []
    assert hold(mapper, "Thumb_Up", "left", later + STEP_MS, later + STEP_MS + spec.hold_ms) == ["gather"]


def test_two_hands_in_one_frame_give_one_command_by_confidence(balance: Balance) -> None:
    mapper = GestureMapper(balance.gestures)
    commands = []
    for t in range(0, balance.gestures.hold_ms + 1000, STEP_MS):
        fired = mapper.feed([
            GestureFrame("Open_Palm", 0.80, t, "left"),
            GestureFrame("Open_Palm", 0.95, t, "right"),
        ], t)
        if fired is not None:
            commands.append((fired.command, fired.hand))
    assert commands == [("select_rovers", "right")]


def test_hand_leaving_frame_resets_hold(balance: Balance) -> None:
    hold_ms = balance.gestures.hold_ms
    mapper = GestureMapper(balance.gestures)
    assert hold(mapper, "Thumb_Down", "right", 0, hold_ms - 100) == []
    assert mapper.feed([], hold_ms - 50) is None  # рука пропала
    assert hold(mapper, "Thumb_Down", "right", hold_ms, 2 * hold_ms - 50) == []
    assert hold(mapper, "Thumb_Down", "right", 2 * hold_ms, 2 * hold_ms) == ["retreat"]


def test_swap_hands_exchanges_left_and_right(balance: Balance) -> None:
    hold_ms = balance.gestures.hold_ms
    mapper = GestureMapper(balance.gestures, swap_hands=True)
    assert hold(mapper, "Open_Palm", "left", 0, hold_ms) == ["select_rovers"]
    mapper = GestureMapper(balance.gestures, swap_hands=True)
    assert hold(mapper, "Victory", "right", 0, hold_ms) == ["train_drone"]


def test_closed_fist_does_nothing(balance: Balance) -> None:
    for hand in ("left", "right"):
        assert hold(GestureMapper(balance.gestures), "Closed_Fist", hand, 0, 5000) == []


def test_holds_report_progress_for_indicator(balance: Balance) -> None:
    mapper = GestureMapper(balance.gestures)
    hold(mapper, "Pointing_Up", "right", 0, 400)
    (state,) = mapper.holds(400)
    assert state.hand == "right" and state.command == "attack_base"
    assert abs(state.progress - 400 / balance.gestures.attack_hold_ms) < 1e-9
