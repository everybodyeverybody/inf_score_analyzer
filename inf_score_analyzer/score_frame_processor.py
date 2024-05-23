#!/usr/bin/env python3
import copy
import logging
from typing import Any
from decimal import Decimal

# type: ignore
from numpy.typing import NDArray

from . import sqlite_client
from .local_dataclasses import (
    Point,
    Score,
    ClearType,
    SongReference,
    VideoProcessingState,
)
from .frame_utilities import (
    get_rectanglular_subsection_from_frame,
    is_white,
    is_bright,
    get_numbers_from_area,
)
from . import constants as CONSTANTS

log = logging.getLogger(__name__)


def fast_slow_digit_reader(block: NDArray) -> int:
    top_left = Point(x=1, y=1)
    top_left_gap = Point(x=1, y=3)
    bottom_right_gap = Point(x=12, y=10)
    top_right_gap = Point(x=12, y=4)
    bottom_left_gap = Point(x=1, y=10)
    middle_top = Point(x=8, y=5)
    middle_third_row_center = Point(x=8, y=7)
    if is_white(block, top_left):
        log.debug("MIGHT BE 2345")
        if is_white(block, top_left_gap):
            log.debug("MIGHT BE 45")
            if is_white(block, top_right_gap):
                log.debug("DEFINITELY 4")
                return 4
            else:
                log.debug("DEFINITELY 5")
                return 5
        else:
            log.debug("MIGHT BE 23")
            if is_white(block, bottom_right_gap):
                log.debug("DEFINITELY 3")
                return 3
            else:
                log.debug("DEFINITELY 2")
                return 2
    else:
        log.debug("MIGHT BE 678901_")
        if is_white(block, top_right_gap):
            log.debug("MIGHT BE 9780")
            if is_white(block, middle_third_row_center):
                log.debug("MIGHT BE 89")
                if is_white(block, bottom_left_gap):
                    log.debug("DEFINITELY 8")
                    return 8
                else:
                    log.debug("DEFINITELY 9")
                    return 9
            else:
                log.debug("MIGHT BE 70")
                if is_white(block, bottom_left_gap):
                    log.debug("DEFINITELY 0")
                    return 0
                else:
                    log.debug("DEFINITELY 7")
                    return 7
        else:
            log.debug("MIGHT BE 61_")
            if is_white(block, middle_top):
                log.debug("MIGHT BE 61")
                if is_white(block, top_left_gap):
                    log.debug("DEFINITELY 6")
                    return 6
                else:
                    log.debug("DEFINITELY 1")
                    return 1
            else:
                log.debug("DEFINITELY ' '")
                return 0


def score_digit_reader(block: NDArray) -> int:
    top_left_gap = Point(3, 5)
    exact_middle = Point(12, 8)
    top_right_gap = Point(22, 5)
    bottom_left_gap = Point(3, 11)
    bottom_right_gap = Point(22, 11)
    bottom_middle = Point(12, 14)
    top_middle = Point(12, 2)
    log.debug("READING")
    if is_white(block, top_left_gap):
        log.debug("MIGHT BE 0456789")
        if is_white(block, bottom_left_gap):
            log.debug("MIGHT BE 068")
            if is_white(block, exact_middle):
                log.debug("MIGHT BE 68")
                if is_white(block, top_right_gap):
                    log.debug("DEFINITELY 8")
                    return 8
                else:
                    log.debug("DEFINITELY 6")
                    return 6
            else:
                log.debug("DEFINITELY 0")
                return 0
        else:
            log.debug("MIGHT BE 4579")
            if is_white(block, bottom_middle):
                log.debug("MIGHT BE 59")
                if is_white(block, top_right_gap):
                    log.debug("DEFINITELY 9")
                    return 9
                else:
                    log.debug("DEFINITELY 5")
                    return 5
            else:
                log.debug("MIGHT BE 47")
                if is_white(block, top_middle):
                    log.debug("DEFINITELY 7")
                    return 7
                else:
                    log.debug("DEFINITELY 4")
                    return 4
    else:
        log.debug("MIGHT BE _123")
        if is_white(block, top_right_gap):
            log.debug("MIGHT BE 23")
            if is_white(block, bottom_right_gap):
                log.debug("DEFINITELY 3")
                return 3
            else:
                log.debug("DEFINITELY 2")
                return 2
        else:
            log.debug("MIGHT BE _1")
            if is_white(block, exact_middle):
                log.debug("DEFINITELY 1")
                return 1
            else:
                log.debug("DEFINITELY ' '")
                return 0


def calculate_grade(perfect_greats: int, greats: int, note_count: int) -> str:
    max_score = note_count * 2
    score = perfect_greats * 2 + greats
    percentage = (Decimal(score) / Decimal(max_score)) * Decimal(100)
    grade = "F"
    if percentage >= Decimal("88.89"):
        grade = "AAA"
    elif percentage >= Decimal("77.78"):
        grade = "AA"
    elif percentage >= Decimal("66.67"):
        grade = "A"
    elif percentage >= Decimal("55.56"):
        grade = "B"
    elif percentage >= Decimal("44.44"):
        grade = "C"
    elif percentage >= Decimal("33.33"):
        grade = "D"
    elif percentage >= Decimal("22.22"):
        grade = "E"
    return grade


def get_clear_type_from_results_screen(frame: NDArray, left_side: bool) -> ClearType:
    start_y = 417
    end_y = 437
    if left_side:
        start_x = 366
        end_x = 512
    else:
        raise RuntimeError("2p score type not implemented")
    subs = get_rectanglular_subsection_from_frame(frame, start_y, start_x, end_y, end_x)
    top_left = Point(y=5, x=23)
    first_letter_black = Point(y=10, x=25)
    easy_clear_r = Point(y=6, x=113)
    combo_or_clear = Point(y=2, x=86)
    clear_or_hard = Point(y=5, x=86)
    if is_bright(subs, top_left):
        log.debug("PROBABLY ASSIST EASY EXH")
        if is_bright(subs, first_letter_black):
            log.debug("PROBABLY EASY EXH")
            if is_bright(subs, easy_clear_r):
                log.debug("DEFINITELY EASY")
                return ClearType.EASY
            else:
                log.debug("DEFINITELY EXHARD")
                return ClearType.EXHARD
        else:
            log.debug("DEFINITELY ASSIST")
            return ClearType.ASSIST
    else:
        log.debug("PROBABLY FAILED NORMAL HARD FULLCOMBO")
        if not is_bright(subs, easy_clear_r):
            log.debug("DEFINITELY FAILED")
            return ClearType.FAILED
        elif not is_bright(subs, combo_or_clear):
            log.debug("DEFINITELY FULL_COMBO")
            return ClearType.FULL_COMBO
        elif is_bright(subs, clear_or_hard):
            log.debug("DEFINITELY NORMAL")
            return ClearType.NORMAL
        else:
            log.debug("DEFINITELY HARD")
            return ClearType.HARD
    return ClearType.UNKNOWN


def get_note_count(frame: NDArray) -> int:
    return get_numbers_from_area(frame, CONSTANTS.NOTES_AREA, note_count_reader)[0]


def get_score_from_result_screen(
    frame: NDArray, left_side: bool, is_double: bool
) -> Score:
    log.info("reading score...")
    if left_side:
        score_area = CONSTANTS.SCORE_P1_AREA
        fast_slow_area = CONSTANTS.FAST_SLOW_P1_AREA
    else:
        raise RuntimeError("2p is not yet supported")
    scores = get_numbers_from_area(frame, score_area, score_digit_reader)
    fast_slow = get_numbers_from_area(frame, fast_slow_area, fast_slow_digit_reader)
    note_count = get_note_count(frame)
    log.debug(f"SCORES: {scores}")
    log.debug(f"FAST_SLOW {fast_slow}")
    log.debug(f"NOTE COUNT {note_count}")
    if note_count is None:
        grade = "X"
    else:
        grade = calculate_grade(scores[0], scores[1], note_count)
    clear_type = get_clear_type_from_results_screen(frame, left_side)
    score_data: list[Any] = []
    score_data.extend(scores)
    score_data.extend(fast_slow)
    score_data.append(grade)
    score_data.append(clear_type.name)
    log.debug(score_data)
    return Score(*score_data)


def note_count_reader(block: NDArray) -> int:
    top_left = Point(x=1, y=1)
    top_left_gap = Point(x=1, y=3)
    bottom_right_gap = Point(x=14, y=12)
    top_right_gap = Point(x=14, y=3)
    bottom_left_gap = Point(x=1, y=10)
    middle_top = Point(x=8, y=5)
    middle_third_row_center = Point(x=10, y=9)
    middle_middle = Point(x=10, y=8)
    if is_white(block, top_left):
        log.debug("MIGHT BE 2345")
        if is_white(block, top_left_gap):
            log.debug("MIGHT BE 45")
            if is_white(block, top_right_gap):
                log.debug("DEFINITELY 4")
                return 4
            else:
                log.debug("DEFINITELY 5")
                return 5
        else:
            log.debug("MIGHT BE 23")
            if is_white(block, bottom_right_gap):
                log.debug("DEFINITELY 3")
                return 3
            else:
                log.debug("DEFINITELY 2")
                return 2
    else:
        log.debug("MIGHT BE 678901_")
        if is_white(block, top_right_gap):
            log.debug("MIGHT BE 9780")
            if is_white(block, bottom_left_gap):
                log.debug("MIGHT BE 80")
                if is_white(block, middle_middle):
                    log.debug("DEFINITELY 8")
                    return 8
                else:
                    log.debug("DEFINITELY 0")
                    return 0
            else:
                log.debug("MIGHT BE 79")
                if is_white(block, middle_third_row_center):
                    log.debug("DEFINITELY 9")
                    return 9
                else:
                    log.debug("DEFINITELY 7")
                    return 7
        else:
            log.debug("MIGHT BE 61_")
            if is_white(block, middle_top):
                log.debug("MIGHT BE 61")
                if is_white(block, top_left_gap):
                    log.debug("DEFINITELY 6")
                    return 6
                else:
                    log.debug("DEFINITELY 1")
                    return 1
            else:
                log.debug("DEFINITELY ' '")
                return 0


def update_video_processing_state(
    frame: NDArray,
    frame_count: int,
    v: VideoProcessingState,
    song_reference: SongReference,
) -> None:
    # total note count only exists on the score frame
    if v.note_count is None:
        v.note_count = get_note_count(frame)
    if v.left_side is not None and v.is_double is not None:
        if v.score is None:
            v.score = get_score_from_result_screen(frame, v.left_side, v.is_double)
        # only if no lookup for titles by song metadata have been determined
        if (
            v.difficulty
            and v.level
            and v.min_bpm
            and v.max_bpm
            and v.note_count
            and (v.metadata_title is None or len(v.metadata_title) > 1)
        ):
            v.metadata_title = song_reference.resolve_by_play_metadata(
                (v.difficulty, v.level),
                (v.min_bpm, v.max_bpm),
                v.note_count,
            )
        # if all score data is found but the frame is not saved
        if (
            v.ocr_song_title is not None
            and v.score is not None
            and v.score_frame is None
        ):
            v.score_frame = copy.deepcopy(frame)
            # if CONSTANTS.DEV_MODE:
            #    frame_utilities.dump_to_png(frame, state.name, frame_count)
    return


def handle_score_transition(
    frame_count: int,
    v: VideoProcessingState,
    song_reference: SongReference,
    session_uuid: str,
) -> None:
    if (
        v.ocr_song_title is None
        and v.ocr_song_future is not None
        and v.ocr_song_future.done()
    ):
        v.ocr_song_title = v.ocr_song_future.result()
        log.info("found ocr song title {v.ocr_song_title}")

    if (
        v.score is not None
        and v.score_frame is not None
        and v.ocr_song_title is not None
        and v.difficulty is not None
        and v.level is not None
        and v.metadata_title is not None
    ):
        log.info(f"frame#{frame_count}:writing score")
        sqlite_client.write_score(
            session_uuid,
            v.ocr_song_title,
            v.score,
            v.difficulty,
            v.score_frame,
            song_reference,
            v.level,
            v.metadata_title,
        )
    return
