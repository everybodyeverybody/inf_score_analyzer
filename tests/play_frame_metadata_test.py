#!/usr/bin/env python3
import os
import logging
from typing import Any
from pathlib import Path

import cv2 as cv  # type: ignore

from inf_score_analyzer import play_frame_processor

PLAY_FILES_DIR = "./tests/hd_play_images/"
PLAY_FILES = [Path(file).absolute() for file in os.scandir(PLAY_FILES_DIR)]
PLAY_FILES_METADATA: dict[str, dict[str, Any]] = {}

for file in PLAY_FILES:
    name_diff, bpms = file.name.split("_bpm_")
    stripped_bpms = bpms.strip().replace(".png", "")
    single_or_multiple_bpms = stripped_bpms.split("_")
    if len(single_or_multiple_bpms) == 3:
        min_bpm = int(single_or_multiple_bpms[0])
        max_bpm = int(single_or_multiple_bpms[2])
    elif len(single_or_multiple_bpms) == 1:
        min_bpm = int(single_or_multiple_bpms[0])
        max_bpm = int(min_bpm)
    else:
        raise RuntimeError("could not parse bpms from filenames")
    name_diff_list = name_diff.split("_")
    level = int(name_diff_list.pop())
    difficulty = str.upper(name_diff_list.pop())
    side = name_diff_list[0]
    if side == "P1":
        left_side = True
    else:
        left_side = False
    sp_dp = name_diff_list[1]
    if sp_dp == "SP":
        is_doubles = False
    else:
        is_doubles = True
    metadata: dict[str, Any] = {
        "min_bpm": min_bpm,
        "max_bpm": max_bpm,
        "level": level,
        "difficulty": f"{sp_dp}_{difficulty}",
        "left_side": left_side,
        "is_doubles": is_doubles,
    }
    PLAY_FILES_METADATA[str(file)] = metadata


def test_bpm_reader() -> None:
    for file, metadata in PLAY_FILES_METADATA.items():
        frame = cv.imread(file)
        min_bpm, max_bpm = play_frame_processor.read_bpm(
            frame, metadata["left_side"], metadata["is_doubles"]
        )
        assert metadata["min_bpm"] == min_bpm
        assert metadata["max_bpm"] == max_bpm


def test_difficulty_reader() -> None:
    for file, metadata in PLAY_FILES_METADATA.items():
        frame = cv.imread(file)
        difficulty = play_frame_processor.read_play_difficulty(
            frame, metadata["left_side"], metadata["is_doubles"]
        )
        assert metadata["difficulty"] == difficulty


def test_level_reader() -> None:
    for file, metadata in PLAY_FILES_METADATA.items():
        logging.debug(file)
        logging.debug(metadata)
        frame = cv.imread(file)
        level = play_frame_processor.read_play_level(
            frame, metadata["left_side"], metadata["is_doubles"]
        )
        assert metadata["level"] == level
