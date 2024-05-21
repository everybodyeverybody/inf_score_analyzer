#!/usr/bin/env python3
import os
from typing import Any
from pathlib import Path
import cv2 as cv  # type: ignore

from inf_score_analyzer.local_dataclasses import Score
import inf_score_analyzer.score_frame_processor as score_frame_processor

SCORE_FILES_DIR = "./tests/hd_score_images/"
SCORE_FILES = [Path(file).absolute() for file in os.scandir(SCORE_FILES_DIR)]
SCORE_FILES_METADATA: dict[str, dict[str, Any]] = {}

for file in SCORE_FILES:
    name_diff, score_counts = file.name.split("_notes_")
    scores = [int(score) for score in score_counts.replace(".png", "").split("_")]
    play_side, clear_type, notes = name_diff.split("_")
    left_side = True
    if play_side == "P2":
        left_side = False
    file_score = Score(*scores)  # type: ignore
    file_score.clear_type = clear_type
    file_score.grade = score_frame_processor.calculate_grade(
        file_score.fgreat, file_score.great, int(notes)
    )
    SCORE_FILES_METADATA[str(file)] = {
        "score": file_score,
        "notes": int(notes),
        "left_side": left_side,
    }


def test_score_reader():
    for file, entry in SCORE_FILES_METADATA.items():
        frame = cv.imread(file)
        frame_score = score_frame_processor.get_score_from_result_screen(
            frame, entry["left_side"], False
        )
        assert frame_score == entry["score"]


def test_notes_reader():
    for file, entry in SCORE_FILES_METADATA.items():
        frame = cv.imread(file)
        frame_note_count = score_frame_processor.get_note_count(frame)
        assert frame_note_count == entry["notes"]
