#!/usr/bin/env python3
import json
import logging
from typing import List

# library imports
from numpy.typing import NDArray

# local imports
from . import constants as CONSTANTS
from .local_dataclasses import StatePixel
from .color_presets import BGR_WHITE, BGR_BLACK
from .frame_utilities import check_pixel_color_in_frame

log = logging.getLogger(__name__)


def get_game_state_from_frame(frame: NDArray, magic_pixels: List[StatePixel]) -> str:
    active_states: dict[str, set] = {}
    white_screen_state_pixels: set[bool] = set()
    black_screen_state_pixels: set[bool] = set()
    for state_pixel in magic_pixels:
        does_color_match: bool = check_pixel_color_in_frame(frame, state_pixel)
        black_screen_state_pixels.add(
            check_pixel_color_in_frame(frame, state_pixel, specific_color=BGR_BLACK)
        )
        white_screen_state_pixels.add(
            check_pixel_color_in_frame(frame, state_pixel, specific_color=BGR_WHITE)
        )
        if state_pixel.state not in active_states:
            active_states[state_pixel.state] = set()
        log.debug(f"{state_pixel} {does_color_match}")
        # print(f"{state_pixel} {does_color_match}")
        active_states[state_pixel.state].add(does_color_match)
    screen_is_white = white_screen_state_pixels == CONSTANTS.ALL_TRUE
    screen_is_black = black_screen_state_pixels == CONSTANTS.ALL_TRUE
    current_game_states: set[str] = set()
    for state_name, all_pixels_match in active_states.items():
        if all_pixels_match == CONSTANTS.ALL_TRUE:
            current_game_states.add(state_name)
    if not current_game_states:
        if screen_is_black:
            current_game_states.add("LOADING")
        elif screen_is_white:
            current_game_states.add("SONG_SELECTED")
        else:
            current_game_states.add("TRANSITION")
    return "_".join(current_game_states)


def read_state_pixels() -> List[StatePixel]:
    log.info(f"Reading pixel config from {CONSTANTS.STATE_PIXEL_CONFIG_FILE}")
    with open(CONSTANTS.STATE_PIXEL_CONFIG_FILE, "rt") as state_pixel_reader:
        pixel_config_json = json.load(state_pixel_reader)
        return [StatePixel(**entry) for entry in pixel_config_json]
