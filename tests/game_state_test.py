#!/usr/bin/env python3
import cv2 as cv

from inf_score_analyzer.local_dataclasses import GameState, GameStatePixel
from inf_score_analyzer.game_state_pixels import ALL_STATE_PIXELS
from inf_score_analyzer.hd_game_state_frame_processor import (
    hd_get_game_state_from_frame,
)


def test_play_state():
    frame = cv.imread("tests/hd_play_images/P1_SP_jelly_kiss_another_8_bpm_135.png")
    play_state_check = hd_get_game_state_from_frame(frame, ALL_STATE_PIXELS)
    assert GameState.P1_SP_PLAY == play_state_check


def test_score_state():
    frame = cv.imread(
        "tests/hd_score_images/P1_FAILED_1090_notes_506_209_84_14_31_121_172.png"
    )
    assert GameState.P1_SCORE == hd_get_game_state_from_frame(frame, ALL_STATE_PIXELS)


def test_song_select_state():
    frame = cv.imread("tests/hd_state_images/HD_SONG_SELECT.png")
    assert GameState.SONG_SELECT == hd_get_game_state_from_frame(
        frame, ALL_STATE_PIXELS
    )
