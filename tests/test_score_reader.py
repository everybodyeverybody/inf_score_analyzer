#!/usr/bin/env python3
import os
from typing import Any
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor

import cv2 as cv  # type: ignore

from inf_score_analyzer.sqlite_client import read_song_data_from_db
from inf_score_analyzer.local_dataclasses import Score, Difficulty
import inf_score_analyzer.score_frame_processor as score_frame_processor
from inf_score_analyzer import sqlite_client

SCORE_FILES_DIR = "./tests/hd_score_images/"
SCORE_FILES = [Path(file).absolute() for file in os.scandir(SCORE_FILES_DIR)]
SCORE_FILES_METADATA: dict[str, dict[str, Any]] = {}
SONG_REFERENCE = read_song_data_from_db()

for file in SCORE_FILES:
    name_diff, score_counts = file.name.split("-notes-")
    scores = [int(score) for score in score_counts.replace(".png", "").split("-")]
    textage_id, sp_or_dp, difficulty, level, play_side, clear_type, notes = (
        name_diff.split("-")
    )
    left_side = True
    if play_side == "P2":
        left_side = False
    is_double = False
    if sp_or_dp == "DP":
        is_double = True
    file_score: Score = Score(*scores)  # type: ignore
    file_score.clear_type = clear_type
    file_score.grade = score_frame_processor.calculate_grade(
        file_score.fgreat, file_score.great, int(notes)
    )
    file_score.total_score = scores[7]
    file_score.miss_count = scores[8]

    difficulty_enum_index = 1
    if is_double:
        difficulty_enum_index = 6

    if difficulty == "N":
        difficulty_enum_index += 1
    elif difficulty == "H":
        difficulty_enum_index += 2
    elif difficulty == "A":
        difficulty_enum_index += 3
    elif difficulty == "L":
        difficulty_enum_index += 4
    else:
        difficulty_enum_index = 99

    SCORE_FILES_METADATA[str(file)] = {
        "score": file_score,
        "notes": int(notes),
        "difficulty": Difficulty(difficulty_enum_index),
        "level": int(level),
        "left_side": left_side,
        "is_double": is_double,
        "textage_id": textage_id,
    }


def test_score_reader():
    for file, entry in SCORE_FILES_METADATA.items():
        frame = cv.imread(file)
        frame_score = score_frame_processor.get_score_from_result_screen(
            frame, entry["left_side"], False
        )
        try:
            assert frame_score == entry["score"]
        except:
            print(f"{file} {entry} {frame_score}")
            raise


def test_notes_reader():
    for file, entry in SCORE_FILES_METADATA.items():
        frame = cv.imread(file)
        frame_note_count = score_frame_processor.get_note_count(frame)
        try:
            assert frame_note_count == entry["notes"]
        except:
            print(f"{file} {entry}")
            raise


def test_difficulty_reader():
    for file, entry in SCORE_FILES_METADATA.items():
        frame = cv.imread(file)
        difficulty, _ = score_frame_processor.get_difficulty_and_level(
            frame, entry["is_double"]
        )
        try:
            assert difficulty == entry["difficulty"]
        except:
            print(f"{file} {entry}")
            raise


def test_level_reader():
    for file, entry in SCORE_FILES_METADATA.items():
        frame = cv.imread(file)
        _, level = score_frame_processor.get_difficulty_and_level(
            frame, entry["is_double"]
        )
        try:
            assert level == entry["level"]
        except:
            print(f"{file} {entry}")
            raise


def test_play_type_reader():
    for file, entry in SCORE_FILES_METADATA.items():
        frame = cv.imread(file)
        play_type = score_frame_processor.get_play_type(frame)
        assert play_type == entry["is_double"]
        try:
            assert play_type == entry["is_double"]
        except:
            print(f"{file} {entry}")
            raise


def test_all():
    with ProcessPoolExecutor(max_workers=1) as ocr:
        for file, entry in SCORE_FILES_METADATA.items():
            frame = cv.imread(file)
            score, notes, ocr_titles, difficulty, level = (
                score_frame_processor.read_score_from_png(
                    frame, entry["left_side"], entry["is_double"], ocr
                )
            )
            metadata_titles = SONG_REFERENCE.resolve_by_score_metadata(
                difficulty.name, level, notes
            )
            tiebreak_data = sqlite_client.read_tiebreak_data(metadata_titles)
            textage_id = SONG_REFERENCE.resolve_ocr_and_metadata(
                ocr_titles, metadata_titles, tiebreak_data, difficulty, level
            )
            try:
                assert textage_id == entry["textage_id"]
            except:
                print(f"{file} {entry}")
                raise
