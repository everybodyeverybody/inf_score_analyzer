#!/usr/bin/env python3
import os
from pathlib import Path
from .local_dataclasses import NumberArea

BASE_DIR = Path(os.getenv("PWD", default="./"))
DATA_DIR = BASE_DIR / Path("data")
STATE_PIXEL_CONFIG_FILE = DATA_DIR / Path("hd_pixel_locations.json")
ALL_TRUE = set([True])

SCORE_P1_AREA = NumberArea(
    start_x=391,
    start_y=787,
    x_offset=28,
    y_offset=28,
    rows=5,
    digits_per_row=4,
    name="SCORE_P1",
)

SCORE_P2_AREA = NumberArea(
    start_x=1740,
    start_y=787,
    x_offset=28,
    y_offset=28,
    rows=5,
    digits_per_row=4,
    name="SCORE_P2",
)


NOTES_AREA = NumberArea(
    start_x=1002,
    start_y=1038,
    x_offset=21,
    y_offset=17,
    rows=1,
    digits_per_row=4,
    name="NOTES",
)

FAST_SLOW_P1_AREA = NumberArea(
    start_x=105,
    start_y=978,
    x_offset=17,
    y_offset=16,
    rows=2,
    digits_per_row=4,
    name="FAST_SLOW_P1",
)

FAST_SLOW_P2_AREA = NumberArea(
    start_x=1449,
    start_y=978,
    x_offset=17,
    y_offset=16,
    rows=2,
    digits_per_row=4,
    name="FAST_SLOW_P2",
)


BPM_X_OFFSET = 35
BPM_Y_OFFSET = 20
MIN_MAX_BPM_X_OFFSET = 26
MIN_MAX_BPM_Y_OFFSET = 14
BPM_P1_AREA = NumberArea(
    start_x=973,
    start_y=966,
    x_offset=BPM_X_OFFSET,
    y_offset=BPM_Y_OFFSET,
    rows=1,
    digits_per_row=3,
    name="BPM_P1",
    kerning_offset=[0, 0, 1],
)
MIN_BPM_P1_AREA = NumberArea(
    start_x=882,
    start_y=974,
    x_offset=MIN_MAX_BPM_X_OFFSET,
    y_offset=MIN_MAX_BPM_Y_OFFSET,
    rows=1,
    digits_per_row=3,
    name="MIN_BPM_P1",
)
MAX_BPM_P1_AREA = NumberArea(
    start_x=1091,
    start_y=974,
    x_offset=MIN_MAX_BPM_X_OFFSET,
    y_offset=MIN_MAX_BPM_Y_OFFSET,
    rows=1,
    digits_per_row=3,
    name="MAX_BPM_P1",
)
LEVEL_SP_P1 = NumberArea(
    start_x=650,
    start_y=100,
    x_offset=34,
    y_offset=17,
    rows=1,
    digits_per_row=1,
    name="LEVEL_SP_P1",
)

# TODO: implement
# probably 125px
BPM_P2_AREA = NumberArea(
    start_x=848,
    start_y=966,
    x_offset=BPM_X_OFFSET,
    y_offset=BPM_Y_OFFSET,
    rows=1,
    digits_per_row=3,
    name="BPM_P2",
    kerning_offset=[0, 0, 1],
)
MIN_BPM_P2_AREA = NumberArea(
    start_x=757,
    start_y=974,
    x_offset=MIN_MAX_BPM_X_OFFSET,
    y_offset=MIN_MAX_BPM_Y_OFFSET,
    rows=1,
    digits_per_row=3,
    name="MIN_BPM_P2",
)
MAX_BPM_P2_AREA = NumberArea(
    start_x=966,
    start_y=974,
    x_offset=MIN_MAX_BPM_X_OFFSET,
    y_offset=MIN_MAX_BPM_Y_OFFSET,
    rows=1,
    digits_per_row=3,
    name="MAX_BPM_P2",
)
LEVEL_SP_P2 = NumberArea(
    start_x=1280,
    start_y=100,
    x_offset=34,
    y_offset=17,
    rows=1,
    digits_per_row=1,
    name="LEVEL_SP_P2",
)


SCORE_DIGIT_X_OFFSET = 28
SCORE_DIGIT_Y_OFFSET = 28
PERCENTAGE_DIGIT_X_OFFSET = 26
PERCENTAGE_DIGIT_Y_OFFSET = 18
BPM_DIGIT_X_OFFSET = 27
BPM_DIGIT_Y_OFFSET = 17

BPM_SP_P1_AREA_X_ORIGIN = 636
BPM_SP_P1_AREA_Y_ORIGIN = 644

BPM_SP_P2_AREA_X_ORIGIN = 566
BPM_SP_P2_AREA_Y_ORIGIN = 644

BPM_DP_AREA_X_ORIGIN = 601
BPM_DP_AREA_Y_ORIGIN = 643

MAX_BPM_SP_P1_AREA_X_ORIGIN = 726
MAX_BPM_SP_P1_AREA_Y_ORIGIN = 647
MAX_BPM_SP_P2_AREA_X_ORIGIN = 656
MAX_BPM_SP_P2_AREA_Y_ORIGIN = 647
MAX_BPM_DP_AREA_X_ORIGIN = 691
MAX_BPM_DP_AREA_Y_ORIGIN = 646

MIN_BPM_SP_P1_AREA_X_ORIGIN = 882
MIN_BPM_SP_P1_AREA_Y_ORIGIN = 974
MIN_MAX_BPM_DIGIT_X_OFFSET = 26
MIN_MAX_BPM_DIGIT_Y_OFFSET = 14

QUANTIZED_WHITE_MAX = 235
QUANTIZED_BLACK_MIN = 20
BRIGHTNESS_HALFWAY_POINT = 128

FAST_SLOW_X_OFFSET = 17
FAST_SLOW_Y_OFFSET = 16

NOTES_X_OFFSET = 21
NOTES_Y_OFFSET = 17

LOG_FORMAT = "%(asctime)s:%(levelname)s:%(module)s:%(message)s"
DEV_MODE: bool = "DEV_MODE" in os.environ

# sqlite
APP_DB_NAME = "app.sqlite3.db"
USER_DB_NAME = "user.sqlite3.db"
APP_DB = DATA_DIR / Path(APP_DB_NAME)
USER_DB = DATA_DIR / Path(USER_DB_NAME)
MIN_APP_AGE_UPDATE_SECONDS = 43200
TACHI_API_TOKEN = os.getenv("TACHI_API_TOKEN")
KAMAITACHI_API_URL = "https://kamai.tachi.ac/ir/direct-manual/import"
KAMAITACHI_SONG_LIST_URL = "https://raw.githubusercontent.com/zkrising/Tachi/refs/heads/main/seeds/collections/songs-iidx.json"
COMMUNITY_RANK_TABLE_URL = "https://iidx-sp12.github.io/songs.json"
COMMUNITY_RANK_TABLE_ID = "SP12"

# grayscale tweak constants for human vision
GRAYSCALE_BLUE = 0.0721
GRAYSCALE_GREEN = 0.7154
GRAYSCALE_RED = 0.2125
PYTESSERACT_LINE_OF_TEXT = "--psm 7"
PYTESSERACT_SINGLE_LETTER = "--psm 10"
