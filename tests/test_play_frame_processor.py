#!/usr/bin/env python3
from typing import Dict, Union
import cv2 as cv  # type: ignore
from inf_score_analyzer.local_dataclasses import VideoProcessingState
from inf_score_analyzer.play_frame_processor import read_play_metadata


BPM_PLAY_FRAMES = {
    "tests/bpm_frames/126-176-251bpm.png": {
        "min_bpm": 126,
        "max_bpm": 251,
        "level": 10,
        "difficulty": "SP_HYPER",
        "lifebar_type": "NORMAL",
        "left_side": True,
        "is_double": False,
    },
    "tests/bpm_frames/37-222-444bpm.png": {
        "min_bpm": 37,
        "max_bpm": 444,
        "level": 11,
        "difficulty": "SP_ANOTHER",
        "lifebar_type": "NORMAL",
        "left_side": True,
        "is_double": False,
    },
    "tests/bpm_frames/90-180-180bpm.png": {
        "min_bpm": 90,
        "max_bpm": 180,
        "level": 9,
        "difficulty": "SP_ANOTHER",
        "lifebar_type": "NORMAL",
        "left_side": True,
        "is_double": False,
    },
    "tests/bpm_frames/90-195-300bpm.png": {
        "min_bpm": 90,
        "max_bpm": 300,
        "level": 10,
        "difficulty": "SP_HYPER",
        "lifebar_type": "NORMAL",
        "left_side": True,
        "is_double": False,
    },
    "tests/dp_frames/dp_right_side.png": {
        "min_bpm": 101,
        "max_bpm": 101,
        "level": 1,
        "difficulty": "DP_NORMAL",
        "lifebar_type": "NORMAL",
        "left_side": False,
        "is_double": True,
    },
    "tests/dp_frames/dp_left_side.png": {
        "min_bpm": 101,
        "max_bpm": 101,
        "level": 1,
        "difficulty": "DP_NORMAL",
        "lifebar_type": "NORMAL",
        "left_side": True,
        "is_double": True,
    },
}

LEVEL_PLAY_FRAMES = {
    "tests/level_frames/lv2.png": {
        "min_bpm": 102,
        "max_bpm": 102,
        "level": 2,
        "difficulty": "SP_HYPER",
        "lifebar_type": "NORMAL",
        "left_side": True,
        "is_double": False,
    },
    "tests/level_frames/lv3.png": {
        "min_bpm": 130,
        "max_bpm": 130,
        "level": 3,
        "difficulty": "SP_NORMAL",
        "lifebar_type": "NORMAL",
        "left_side": True,
        "is_double": False,
    },
    "tests/level_frames/lv4.png": {
        "min_bpm": 149,
        "max_bpm": 149,
        "level": 4,
        "difficulty": "SP_NORMAL",
        "lifebar_type": "NORMAL",
        "left_side": True,
        "is_double": False,
    },
    "tests/level_frames/lv5.png": {
        "min_bpm": 165,
        "max_bpm": 165,
        "level": 5,
        "difficulty": "SP_NORMAL",
        "lifebar_type": "NORMAL",
        "left_side": True,
        "is_double": False,
    },
    "tests/level_frames/lv6.png": {
        "min_bpm": 198,
        "max_bpm": 198,
        "level": 6,
        "difficulty": "SP_NORMAL",
        "lifebar_type": "NORMAL",
        "left_side": True,
        "is_double": False,
    },
    "tests/level_frames/lv7.png": {
        "min_bpm": 185,
        "max_bpm": 185,
        "level": 7,
        "difficulty": "SP_NORMAL",
        "lifebar_type": "NORMAL",
        "left_side": True,
        "is_double": False,
    },
    "tests/level_frames/lv8.png": {
        "min_bpm": 180,
        "max_bpm": 180,
        "level": 8,
        "difficulty": "SP_HYPER",
        "lifebar_type": "NORMAL",
        "left_side": True,
        "is_double": False,
    },
    "tests/level_frames/lv9.png": {
        "min_bpm": 160,
        "max_bpm": 160,
        "level": 9,
        "difficulty": "SP_HYPER",
        "lifebar_type": "NORMAL",
        "left_side": True,
        "is_double": False,
    },
    "tests/level_frames/lv10.png": {
        "min_bpm": 144,
        "max_bpm": 144,
        "level": 10,
        "difficulty": "SP_ANOTHER",
        "lifebar_type": "NORMAL",
        "left_side": True,
        "is_double": False,
    },
    "tests/level_frames/lv11.png": {
        "min_bpm": 105,
        "max_bpm": 210,
        "level": 11,
        "difficulty": "SP_ANOTHER",
        "lifebar_type": "NORMAL",
        "left_side": True,
        "is_double": False,
    },
    "tests/level_frames/lv12.png": {
        "min_bpm": 153,
        "max_bpm": 153,
        "level": 12,
        "difficulty": "SP_ANOTHER",
        "lifebar_type": "NORMAL",
        "left_side": True,
        "is_double": False,
    },
    "tests/level_frames/legg.png": {
        "min_bpm": 128,
        "max_bpm": 128,
        "level": 10,
        "difficulty": "SP_LEGGENDARIA",
        "lifebar_type": "HARD",
        "left_side": True,
        "is_double": False,
    },
    "tests/level_frames/exhard.png": {
        "min_bpm": 180,
        "max_bpm": 180,
        "level": 5,
        "difficulty": "SP_NORMAL",
        "lifebar_type": "EXHARD",
        "left_side": True,
        "is_double": False,
    },
}

SP_RIGHT_SIDE_FRAMES = {
    "tests/2p_frames/2p_lv10_another.png": {
        "min_bpm": 140,
        "max_bpm": 140,
        "level": 10,
        "difficulty": "SP_ANOTHER",
        "lifebar_type": "EXHARD",
        "left_side": False,
        "is_double": False,
    },
    "tests/2p_frames/2p_lv11_another.png": {
        "min_bpm": 180,
        "max_bpm": 212,
        "level": 11,
        "difficulty": "SP_ANOTHER",
        "lifebar_type": "NORMAL",
        "left_side": False,
        "is_double": False,
    },
    "tests/2p_frames/2p_lv12_another.png": {
        "min_bpm": 93,
        "max_bpm": 191,
        "level": 12,
        "difficulty": "SP_ANOTHER",
        "lifebar_type": "NORMAL",
        "left_side": False,
        "is_double": False,
    },
    "tests/2p_frames/2p_lv1_normal.png": {
        "min_bpm": 145,
        "max_bpm": 145,
        "level": 1,
        "difficulty": "SP_NORMAL",
        "lifebar_type": "NORMAL",
        "left_side": False,
        "is_double": False,
    },
    "tests/2p_frames/2p_lv2_normal.png": {
        "min_bpm": 132,
        "max_bpm": 132,
        "level": 2,
        "difficulty": "SP_NORMAL",
        "lifebar_type": "EXHARD",
        "left_side": False,
        "is_double": False,
    },
    "tests/2p_frames/2p_lv3_normal.png": {
        "min_bpm": 90,
        "max_bpm": 90,
        "level": 3,
        "difficulty": "SP_NORMAL",
        "lifebar_type": "EXHARD",
        "left_side": False,
        "is_double": False,
    },
    "tests/2p_frames/2p_lv4_hyper.png": {
        "min_bpm": 144,
        "max_bpm": 144,
        "level": 4,
        "difficulty": "SP_HYPER",
        "lifebar_type": "HARD",
        "left_side": False,
        "is_double": False,
    },
    "tests/2p_frames/2p_lv5_normal.png": {
        "min_bpm": 200,
        "max_bpm": 200,
        "level": 5,
        "difficulty": "SP_NORMAL",
        "lifebar_type": "HARD",
        "left_side": False,
        "is_double": False,
    },
    "tests/2p_frames/2p_lv6_hyper.png": {
        "min_bpm": 188,
        "max_bpm": 188,
        "level": 6,
        "difficulty": "SP_HYPER",
        "lifebar_type": "HARD",
        "left_side": False,
        "is_double": False,
    },
    "tests/2p_frames/2p_lv7_another.png": {
        "min_bpm": 170,
        "max_bpm": 170,
        "level": 7,
        "difficulty": "SP_ANOTHER",
        "lifebar_type": "HARD",
        "left_side": False,
        "is_double": False,
    },
    "tests/2p_frames/2p_lv8_hyper.png": {
        "min_bpm": 180,
        "max_bpm": 180,
        "level": 8,
        "difficulty": "SP_HYPER",
        "lifebar_type": "HARD",
        "left_side": False,
        "is_double": False,
    },
    "tests/2p_frames/2p_lv9_hyper.png": {
        "min_bpm": 145,
        "max_bpm": 145,
        "level": 9,
        "difficulty": "SP_HYPER",
        "lifebar_type": "EXHARD",
        "left_side": False,
        "is_double": False,
    },
}

DP_SIDE_FRAMES = {
    "tests/dp_frames/12_dp_right.png": {
        "min_bpm": 256,
        "max_bpm": 256,
        "level": 12,
        "difficulty": "DP_ANOTHER",
        "lifebar_type": "NORMAL",
        "left_side": False,
        "is_double": True,
    },
    "tests/dp_frames/12_dp_left.png": {
        "min_bpm": 256,
        "max_bpm": 256,
        "level": 12,
        "difficulty": "DP_ANOTHER",
        "lifebar_type": "NORMAL",
        "left_side": True,
        "is_double": True,
    },
    "tests/dp_frames/dp_hard_right_side.png": {
        "min_bpm": 102,
        "max_bpm": 102,
        "level": 2,
        "difficulty": "DP_NORMAL",
        "lifebar_type": "HARD",
        "left_side": False,
        "is_double": True,
    },
    "tests/dp_frames/dp_exhard_right_side.png": {
        "min_bpm": 180,
        "max_bpm": 180,
        "level": 11,
        "difficulty": "DP_ANOTHER",
        "lifebar_type": "EXHARD",
        "left_side": False,
        "is_double": True,
    },
    "tests/dp_frames/dp_hard_left_side.png": {
        "min_bpm": 256,
        "max_bpm": 256,
        "level": 12,
        "difficulty": "DP_ANOTHER",
        "lifebar_type": "HARD",
        "left_side": True,
        "is_double": True,
    },
    "tests/dp_frames/dp_exhard_left_side.png": {
        "min_bpm": 145,
        "max_bpm": 145,
        "level": 1,
        "difficulty": "DP_NORMAL",
        "lifebar_type": "EXHARD",
        "left_side": True,
        "is_double": True,
    },
}


def test_get_bpm_from_play_screen():
    evaluation_loop(BPM_PLAY_FRAMES)


def test_get_level_from_play_screen():
    evaluation_loop(LEVEL_PLAY_FRAMES)


def test_sp_right_side_metadata():
    evaluation_loop(SP_RIGHT_SIDE_FRAMES)


def test_dp_right_side_metadata():
    evaluation_loop(DP_SIDE_FRAMES)


def evaluation_loop(frames: Dict[str, Dict[str, Union[int, str]]]):
    results = {}
    for file in frames.keys():
        v = VideoProcessingState()
        data = cv.imread(file)
        (
            difficulty,
            level,
            lifebar_type,
            min_bpm,
            max_bpm,
            left_side,
            is_double,
        ) = read_play_metadata(0, data, v)
        play_metadata = {
            "difficulty": difficulty,
            "level": level,
            "lifebar_type": lifebar_type,
            "min_bpm": min_bpm,
            "max_bpm": max_bpm,
            "left_side": left_side,
            "is_double": is_double,
        }
        results[file] = play_metadata

    for entry in results.keys():
        print(entry)
        print(results[entry])
        assert results[entry] == frames[entry]
