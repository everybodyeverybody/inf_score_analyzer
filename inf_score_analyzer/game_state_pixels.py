#!/usr/bin/env python3
from .local_dataclasses import GameState, GameStatePixel

P1_SCORE_MIDDLE = GameStatePixel(
    state=GameState.P1_SCORE, name="good_middle_g", y=852, x=300, b=-1, g=182, r=240
)

P1_SCORE_TIMING_T = GameStatePixel(
    state=GameState.P1_SCORE,
    name="timing_t_cross_top",
    y=963,
    x=113,
    b=252,
    g=194,
    r=102,
)


P2_SCORE_MIDDLE = GameStatePixel(
    state=GameState.P2_SCORE, name="good_middle_g", y=852, x=1649, b=-1, g=182, r=240
)

P2_SCORE_TIMING_T = GameStatePixel(
    state=GameState.P2_SCORE,
    name="timing_t_cross_top",
    y=963,
    x=1457,
    b=252,
    g=194,
    r=102,
)


P1_SP_NORMAL_PLAY_EXTRA_STAGE = GameStatePixel(
    state=GameState.P1_SP_PLAY,
    name="extra stage grey border right",
    y=44,
    x=1500,
    b=109,
    g=109,
    r=109,
)

P1_SP_PLAY_AREA_BORDER = GameStatePixel(
    state=GameState.P1_SP_PLAY,
    name="1p blue play area border",
    y=10,
    x=25,
    b=255,
    g=153,
    r=0,
)

P2_SP_NORMAL_PLAY_EXTRA_STAGE = GameStatePixel(
    state=GameState.P2_SP_PLAY,
    name="extra stage grey border left",
    y=44,
    x=420,
    b=109,
    g=109,
    r=109,
)

P2_SP_PLAY_AREA_BORDER = GameStatePixel(
    state=GameState.P2_SP_PLAY,
    name="2p blue play area border",
    y=10,
    x=1895,
    b=255,
    g=153,
    r=0,
)


SONG_SELECT_MUSIC_UNDERLINE = GameStatePixel(
    state=GameState.SONG_SELECT,
    name="music select underline",
    y=108,
    x=70,
    b=255,
    g=255,
    r=255,
)

SONG_SELECT_TOP_RIGHT_BORDER = GameStatePixel(
    state=GameState.SONG_SELECT,
    name="top right blue border",
    y=45,
    x=1870,
    b=252,
    g=232,
    r=20,
)

SONG_SELECT_SCORE_DATA = GameStatePixel(
    state=GameState.SONG_SELECT,
    name="score data MISS COUNT M",
    y=866,
    x=67,
    b=253,
    g=253,
    r=253,
)


SCORE_STATES: set[GameState] = {GameState.P1_SCORE, GameState.P2_SCORE}
PLAY_STATES: set[GameState] = {
    GameState.P1_SP_PLAY,
    GameState.P2_SP_PLAY,
    GameState.P1_DP_PLAY,
    GameState.P2_DP_PLAY,
}
SONG_SELECT_STATES: set[GameState] = {GameState.SONG_SELECT}

ALL_STATE_PIXELS: list[GameStatePixel] = [
    P1_SCORE_MIDDLE,
    P1_SCORE_TIMING_T,
    P2_SCORE_MIDDLE,
    P2_SCORE_TIMING_T,
    P1_SP_NORMAL_PLAY_EXTRA_STAGE,
    P1_SP_PLAY_AREA_BORDER,
    P2_SP_NORMAL_PLAY_EXTRA_STAGE,
    P2_SP_PLAY_AREA_BORDER,
    SONG_SELECT_MUSIC_UNDERLINE,
    SONG_SELECT_SCORE_DATA,
    SONG_SELECT_MUSIC_UNDERLINE,
]
