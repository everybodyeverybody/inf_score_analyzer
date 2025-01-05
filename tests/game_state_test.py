#!/usr/bin/env python3
import cv2 as cv  # type: ignore

from inf_score_analyzer import game_state_frame_processor
from inf_score_analyzer.local_dataclasses import GameState
from inf_score_analyzer.game_state_pixels import ALL_STATE_PIXELS


def test_play_state():
    frame = cv.imread("tests/hd_play_images/P1_SP_jelly_kiss_another_8_bpm_135.png")
    play_state_check = game_state_frame_processor.get_game_state_from_frame(
        frame, ALL_STATE_PIXELS
    )
    assert GameState.P1_SP_PLAY == play_state_check


def test_score_state():
    frame = cv.imread(
        "tests/hd_score_images/rbwafter-SP-A-10-P1-FAILED-1090-notes-506-209-84-14-31-121-172-1221-45.png"
    )
    assert GameState.P1_SCORE == game_state_frame_processor.get_game_state_from_frame(
        frame, ALL_STATE_PIXELS
    )


def test_song_select_state():
    frame = cv.imread("tests/hd_state_images/HD_SONG_SELECT.png")
    assert (
        GameState.SONG_SELECT
        == game_state_frame_processor.get_game_state_from_frame(frame, ALL_STATE_PIXELS)
    )
