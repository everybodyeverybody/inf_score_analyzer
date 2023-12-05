#!/usr/bin/env python3
import cv2 as cv  # type: ignore
from inf_score_analyzer.play_frame_processor import get_lifebar_percentage


# TODO: future work
# TODO: add 2p and DP values
FRAMES_AND_VALUES = {
    "tests/percentage_raw_frames/percentage_006540.png": 18,
    "tests/percentage_raw_frames/percentage_012240.png": 100,
    "tests/percentage_raw_frames/percentage_006840.png": 30,
    "tests/percentage_raw_frames/percentage_007320.png": 56,
    "tests/percentage_raw_frames/percentage_007620.png": 72,
    "tests/percentage_raw_frames/percentage_011940.png": 94,
    "tests/percentage_raw_frames/percentage_005880.png": 0,
}


def test_get_percentage_from_play_screen():
    results = {}

    for file in FRAMES_AND_VALUES.keys():
        data = cv.imread(file)
        score = get_lifebar_percentage(data, True, False)
        results[file] = score

    for entry in results.keys():
        assert results[entry] == FRAMES_AND_VALUES[entry]
