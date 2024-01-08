#!/usr/bin/env python3
import logging
import cv2 as cv  # type: ignore
from inf_score_analyzer.local_dataclasses import Score
from inf_score_analyzer.score_frame_processor import (
    get_score_from_result_screen,
    get_note_count,
    get_clear_type_from_results_screen,
)

from inf_score_analyzer.local_dataclasses import ClearType

SCORE_FRAMES = {
    "tests/note_count_frames/1073_screamsquad.png": Score(
        fgreat=516,
        great=300,
        good=192,
        bad=49,
        poor=58,
        fast=235,
        slow=257,
        grade="B",
        clear_type="FAILED",
    ),
    "tests/clear_type_frames/assist_clear.png": Score(
        fgreat=58,
        great=22,
        good=11,
        bad=0,
        poor=2,
        fast=21,
        slow=12,
        grade="A",
        clear_type="ASSIST",
    ),
}

NOTE_COUNT_FRAMES = {
    "tests/note_count_frames/786_era.png": 786,
    "tests/note_count_frames/1073_screamsquad.png": 1073,
    "tests/note_count_frames/1088_naught.png": 1088,
    "tests/note_count_frames/2094_mare.png": 2094,
    "tests/note_count_frames/656_jelly.png": 656,
    "tests/clear_type_frames/2p_full_combo.png": 133,
}

RIGHT_SIDE_SCORE_FRAMES = {
    "tests/2p_frames/2p_meikyou_score.png": Score(
        fgreat=49,
        great=51,
        good=138,
        bad=64,
        poor=291,
        fast=86,
        slow=103,
        grade="F",
        clear_type="FAILED",
    ),
    "tests/2p_frames/2p_sleepless_days_score.png": Score(
        fgreat=11,
        great=7,
        good=10,
        bad=1,
        poor=16,
        fast=12,
        slow=5,
        grade="F",
        clear_type="FAILED",
    ),
}

LEFT_CLEAR_TYPE_FRAMES = {
    "tests/clear_type_frames/assist_clear.png": ClearType.ASSIST,
    "tests/clear_type_frames/clear.png": ClearType.NORMAL,
    "tests/clear_type_frames/easy_clear.png": ClearType.EASY,
    "tests/clear_type_frames/exh-clear.png": ClearType.EXHARD,
    "tests/clear_type_frames/failed.png": ClearType.FAILED,
    "tests/clear_type_frames/full_combo.png": ClearType.FULL_COMBO,
    "tests/clear_type_frames/hard_clear.png": ClearType.HARD,
}

RIGHT_CLEAR_TYPE_FRAMES = {
    "tests/clear_type_frames/2p_exhard.png": ClearType.EXHARD,
    "tests/clear_type_frames/2p_assist.png": ClearType.ASSIST,
    "tests/clear_type_frames/2p_easy.png": ClearType.EASY,
    "tests/clear_type_frames/2p_normal.png": ClearType.NORMAL,
    "tests/clear_type_frames/2p_full_combo.png": ClearType.FULL_COMBO,
    "tests/clear_type_frames/2p_hard.png": ClearType.HARD,
}


def test_get_score_from_result_screen():
    results = {}
    for file in SCORE_FRAMES:
        left_side = True
        is_double = False
        data = cv.imread(file)
        note_count = get_note_count(data)
        results[file] = get_score_from_result_screen(
            data, left_side, is_double, note_count
        )

    for file in results:
        logging.info(file)
        assert results[file] == SCORE_FRAMES[file]


def test_get_notecounts_from_result_screen():
    results = {}
    for file in NOTE_COUNT_FRAMES:
        data = cv.imread(file)
        logging.debug(file)
        results[file] = get_note_count(data)

    for file in results:
        assert results[file] == NOTE_COUNT_FRAMES[file]


def test_right_side_score_processor():
    results = {}
    for file in RIGHT_SIDE_SCORE_FRAMES:
        left_side = False
        is_double = False
        data = cv.imread(file)
        note_count = get_note_count(data)
        results[file] = get_score_from_result_screen(
            data, left_side, is_double, note_count
        )

    for file in results:
        assert results[file] == RIGHT_SIDE_SCORE_FRAMES[file]


def test_clear_type_processor():
    left_results = {}
    right_results = {}
    for file in LEFT_CLEAR_TYPE_FRAMES:
        data = cv.imread(file)
        print(file)
        clear_type = get_clear_type_from_results_screen(data, True)
        left_results[file] = clear_type

    for file in RIGHT_CLEAR_TYPE_FRAMES:
        data = cv.imread(file)
        print(file)
        clear_type = get_clear_type_from_results_screen(data, False)
        right_results[file] = clear_type

    for file in left_results:
        assert left_results[file] == LEFT_CLEAR_TYPE_FRAMES[file]
    for file in right_results:
        assert right_results[file] == RIGHT_CLEAR_TYPE_FRAMES[file]
