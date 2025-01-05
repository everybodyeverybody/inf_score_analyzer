#!/usr/bin/env python3
import os
import logging
from typing import Any
from pathlib import Path

import cv2 as cv  # type: ignore

from inf_score_analyzer import song_select_frame_processor
from inf_score_analyzer.sqlite_client import read_song_data_from_db

SONG_SELECT_FILES_DIR = "./tests/hd_song_select_images/"
SONG_SELECT_FILES = [
    Path(file).absolute() for file in os.scandir(SONG_SELECT_FILES_DIR)
]
SONG_SELECT_FILES_METADATA: dict[str, dict[str, Any]] = {}
for file in SONG_SELECT_FILES:
    name_diff, bpms = file.name.split("-bpm-")
    stripped_bpms = bpms.strip().replace(".png", "")
    single_or_multiple_bpms = stripped_bpms.split("-")
    if len(single_or_multiple_bpms) == 2:
        min_bpm = int(single_or_multiple_bpms[0])
        max_bpm = int(single_or_multiple_bpms[1])
    elif len(single_or_multiple_bpms) == 1:
        min_bpm = int(single_or_multiple_bpms[0])
        max_bpm = int(min_bpm)
    else:
        print(name_diff)
        print(stripped_bpms)
        print(file)
        raise RuntimeError("could not parse bpms from filenames")
    name_diff_list = name_diff.split("-")
    miss_count = int(name_diff_list.pop())
    score = int(name_diff_list.pop())
    clear_type = str.upper(name_diff_list.pop())
    level = int(name_diff_list.pop())
    difficulty = str.upper(name_diff_list.pop())
    textage_id = name_diff_list.pop()
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
        "textage_id": textage_id,
        "clear_type": clear_type,
    }
    SONG_SELECT_FILES_METADATA[str(file)] = metadata


def test_bpm_reader() -> None:
    for file, metadata in SONG_SELECT_FILES_METADATA.items():
        frame = cv.imread(file)
        min_bpm, max_bpm = song_select_frame_processor.read_bpm(frame)
        assert metadata["min_bpm"] == min_bpm
        assert metadata["max_bpm"] == max_bpm


def test_difficulty_reader() -> None:
    for file, metadata in SONG_SELECT_FILES_METADATA.items():
        frame = cv.imread(file)
        difficulty, level = song_select_frame_processor.read_difficulty(frame)
        try:
            assert metadata["difficulty"] == difficulty.name
        except:
            print(f"{file} {metadata['difficulty']} {difficulty}")
            raise


def test_level_reader() -> None:
    for file, metadata in SONG_SELECT_FILES_METADATA.items():
        logging.debug(file)
        logging.debug(metadata)
        frame = cv.imread(file)
        difficulty, level = song_select_frame_processor.read_difficulty(frame)
        try:
            assert metadata["level"] == level
        except:
            print(f"{file} {metadata['level']} {level}")
            raise


def test_textage_id_reader() -> None:
    song_reference = read_song_data_from_db()
    for file, metadata in SONG_SELECT_FILES_METADATA.items():
        logging.debug(file)
        logging.debug(metadata)
        frame = cv.imread(file)
        difficulty, level = song_select_frame_processor.read_difficulty(frame)
        bpm = song_select_frame_processor.read_bpm(frame)
        try:
            textage_id, _ = song_select_frame_processor.read_textage_id(
                frame, song_reference, bpm, difficulty, level
            )
        except Exception:
            print("Could not find textage ID")
            textage_id = None

        try:
            assert metadata["textage_id"] == textage_id
        except Exception:
            print(f"{file} {metadata['textage_id']} {textage_id}")
            raise
