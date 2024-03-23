#!/usr/bin/env python3
import json
import logging
from typing import List

# library imports
from numpy.typing import NDArray

# local imports
from . import constants as CONSTANTS
from .local_dataclasses import GameStatePixel, GameState
from .color_presets import BGR_WHITE, BGR_BLACK
from .frame_utilities import check_pixel_color_in_frame

log = logging.getLogger(__name__)


def hd_get_game_state_from_frame(
    frame: NDArray, pixels: List[GameStatePixel]
) -> GameState:
    active_states: dict[GameState, set] = {}
    white_screen_state_pixels: set[bool] = set()
    black_screen_state_pixels: set[bool] = set()
    for state_pixel in pixels:
        does_color_match: bool = check_pixel_color_in_frame(frame, state_pixel)
        black_screen_state_pixels.add(
            check_pixel_color_in_frame(frame, state_pixel, specific_color=BGR_BLACK)
        )
        white_screen_state_pixels.add(
            check_pixel_color_in_frame(frame, state_pixel, specific_color=BGR_WHITE)
        )
        if state_pixel.state not in active_states:
            active_states[state_pixel.state] = set()
        # log.debug(f"does color match? {state_pixel} {does_color_match}")
        active_states[state_pixel.state].add(does_color_match)
    screen_is_white = white_screen_state_pixels == CONSTANTS.ALL_TRUE
    # screen_is_black = black_screen_state_pixels == CONSTANTS.ALL_TRUE
    current_game_states: set[GameState] = set()
    for state_name, all_pixels_match in active_states.items():
        if all_pixels_match == CONSTANTS.ALL_TRUE:
            current_game_states.add(GameState(state_name))
    if not current_game_states:
        if screen_is_white:
            current_game_states.add(GameState.SONG_SELECTED)
        else:
            current_game_states.add(GameState.LOADING)
    if len(current_game_states) > 1:
        raise RuntimeError(f"Could not resolve game state: {current_game_states}")
    return GameState(current_game_states.pop())
