#!/usr/bin/env python3
import logging

# library imports
from numpy.typing import NDArray  # type: ignore

# local imports
from . import constants as CONSTANTS
from .local_dataclasses import GameStatePixel, GameState
from .frame_utilities import check_pixel_color_in_frame


log = logging.getLogger(__name__)


def get_game_state_from_frame(
    frame: NDArray, pixels: list[GameStatePixel]
) -> GameState:
    active_states: dict[GameState, set] = {}
    for state_pixel in pixels:
        does_color_match: bool = check_pixel_color_in_frame(frame, state_pixel)
        # log.debug(f"checking {state_pixel}: {does_color_match}")
        if state_pixel.state not in active_states:
            active_states[state_pixel.state] = set()
        active_states[state_pixel.state].add(does_color_match)
    for state_name, all_pixels_match in active_states.items():
        if all_pixels_match == CONSTANTS.ALL_TRUE:
            return GameState(state_name)
    return GameState.LOADING
