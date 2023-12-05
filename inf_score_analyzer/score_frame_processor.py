#!/usr/bin/env python3
import io
import re
import uuid
import logging
import sqlite3
from decimal import Decimal
from datetime import datetime, timezone
from typing import Callable, Set, Optional

import numpy  # type: ignore
import polyleven  # type: ignore
from numpy.typing import NDArray

from .local_dataclasses import (
    Point,
    Score,
    OCRSongTitles,
    Difficulty,
    SongReference,
    ClearType,
)
from .frame_utilities import (
    get_rectanglular_subsection_from_frame,
    is_white,
    is_black,
    is_bright,
    read_pixel,
)
from . import constants as CONSTANTS

log = logging.getLogger(__name__)


def write_score_sqlite(
    session_uuid: str,
    title: OCRSongTitles,
    score: Score,
    difficulty: str,
    score_frame: NDArray,
    song_reference: SongReference,
    level: int,
    metadata_title: Set[str],
) -> None:
    referenced_textage_id = None
    resolved_song_info = song_reference.resolve_ocr(title, difficulty, level)
    if resolved_song_info is not None:
        referenced_textage_id = resolved_song_info
    else:
        if len(metadata_title) == 1:
            log.info("Using metadata title")
            referenced_textage_id = metadata_title.pop()
        else:
            log.warning(f"Found too much metadata, {metadata_title}")
            referenced_textage_id = metadata_lookup_tiebreaker(metadata_title, title)

    difficulty_id = Difficulty[difficulty].value
    log.info(f"Difficulty: {Difficulty[difficulty]}")
    log.info("TRYING SQLITE WRITE")
    score_uuid = str(uuid.uuid4())
    end_time_utc = datetime.now(timezone.utc)

    score_frame_bytes = io.BytesIO()
    numpy.savez(score_frame_bytes, frame_slice=score_frame)
    score_frame_bytes.seek(0)

    score_query = (
        "insert into score values ("
        ":score_uuid,"
        ":session_uuid,"
        ":textage_id,"
        ":difficulty_id,"
        ":perfect_great,"
        ":great,"
        ":good,"
        ":bad,"
        ":poor,"
        ":fast,"
        ":slow,"
        ":combo_break,"
        ":grade,"
        ":clear_type,"
        ":failure_measure,"
        ":failure_note,"
        ":end_time_utc"
        ")"
    )
    user_db_connection = sqlite3.connect(CONSTANTS.USER_DB)
    db_cursor = user_db_connection.cursor()
    db_cursor.execute(
        score_query,
        {
            "score_uuid": score_uuid,
            "session_uuid": session_uuid,
            "textage_id": referenced_textage_id,
            "difficulty_id": difficulty_id,
            "perfect_great": score.fgreat,
            "great": score.great,
            "good": score.good,
            "bad": score.bad,
            "poor": score.poor,
            "fast": score.fast,
            "slow": score.slow,
            "combo_break": None,
            "grade": score.grade,
            "clear_type": score.clear_type,
            "failure_measure": None,
            "failure_note": None,
            "end_time_utc": end_time_utc,
        },
    )
    ocr_query = (
        "insert into score_ocr "
        "values (:score_uuid, :result_screengrab, :title_scaled,"
        ":en_title_ocr, :en_artist_ocr, :jp_title_ocr, :jp_artist_ocr)"
    )
    db_cursor.execute(
        ocr_query,
        {
            "score_uuid": score_uuid,
            "result_screengrab": score_frame_bytes.getvalue(),
            "title_scaled": None,
            "en_title_ocr": title.en_title,
            "en_artist_ocr": title.en_artist,
            "jp_title_ocr": title.jp_title,
            "jp_artist_ocr": title.jp_artist,
        },
    )
    user_db_connection.commit()
    return None


def metadata_lookup_tiebreaker(
    metadata_titles: Set[str], ocr_titles: OCRSongTitles
) -> str:
    app_db_connection = sqlite3.connect(CONSTANTS.APP_DB)
    db_cursor = app_db_connection.cursor()
    ids_as_string = ",".join([f"'{id}'" for id in metadata_titles])
    query = f"select textage_id, artist, title from songs where textage_id in ({ids_as_string})"
    results = db_cursor.execute(query).fetchall()
    lowest_score_title = (-1, "")
    for song in results:
        score = polyleven.levenshtein(ocr_titles.en_artist, song[1])
        score += polyleven.levenshtein(ocr_titles.en_title, song[2])
        score += polyleven.levenshtein(ocr_titles.jp_artist, song[1])
        score += polyleven.levenshtein(ocr_titles.jp_title, song[2])
        if lowest_score_title[0] == -1 or score <= lowest_score_title[0]:
            if score == lowest_score_title[0]:
                raise RuntimeError(
                    f"Couldn't figure out the song, my bad {metadata_titles} ocr {ocr_titles}"
                )
            lowest_score_title = (score, song[0])
    return lowest_score_title[1]


def fast_slow_digit_reader(block: NDArray) -> str:
    top_mid = Point(x=5, y=1)
    mid_top = Point(x=5, y=4)
    top_right = Point(x=9, y=1)
    mid_bottom = Point(x=5, y=5)
    mid_left_top = Point(x=1, y=4)
    mid_left_bottom = Point(x=1, y=5)
    mid_right_bottom = Point(x=9, y=5)
    if is_white(read_pixel(block, mid_left_bottom)):
        log.debug("MIGHT BE 02689")
        if is_white(read_pixel(block, mid_top)):
            log.debug("PROBABLY 268")
            if is_white(read_pixel(block, top_right)):
                log.debug("PROBABLY 28")
                if is_white(read_pixel(block, mid_right_bottom)):
                    log.debug("DEFINITELY 8")
                    return "8"
                else:
                    log.debug("DEFINITELY 2")
                    return "2"
            else:
                log.debug("DEFINITELY 6")
                return "6"
        else:
            log.debug("PROBABLY 09")
            if is_white(read_pixel(block, mid_bottom)):
                log.debug("DEFINITELY 9")
                return "9"
            else:
                log.debug("DEFINITELY 0")
                return "0"
    else:
        log.debug("MIGHT BE 13457_")
        if is_white(read_pixel(block, mid_left_top)):
            log.debug("PROBABLY 45")
            if is_white(read_pixel(block, top_mid)):
                log.debug("DEFINITELY 5")
                return "5"
            else:
                log.debug("DEFINITELY 4")
                return "4"
        else:
            log.debug("PROBABLY 137_")
            if is_white(read_pixel(block, mid_bottom)):
                log.debug("DEFINITELY 1")
                return "1"
            elif is_white(read_pixel(block, mid_top)):
                log.debug("DEFINITELY 3")
                return "3"
            elif is_white(read_pixel(block, top_right)):
                log.debug("DEFINITELY 7")
                return "7"
            else:
                log.debug("DEFINITELY BLANK")
                return " "
    return "X"


def score_digit_reader(block: NDArray) -> str:
    top_mid = Point(10, 3)
    mid_top = Point(10, 6)
    mid1 = Point(10, 7)
    mid2 = Point(10, 8)
    top_left = Point(3, 4)
    bottom_left = Point(3, 11)
    bottom_right = Point(15, 11)

    if is_white(read_pixel(block, mid1)) and is_white(read_pixel(block, mid2)):
        log.debug("MIGHT BE 12358")
        if is_white(read_pixel(block, bottom_left)):
            log.debug("PROBABLY 28")
            if is_white(read_pixel(block, top_left)):
                log.debug("DEFINITELY 8")
                return "8"
            else:
                log.debug("DEFINITELY 2")
                return "2"
        elif is_white(read_pixel(block, bottom_right)):
            log.debug("PROBABLY 35")
            if is_white(read_pixel(block, top_left)):
                log.debug("DEFINITELY 5")
                return "5"
            else:
                log.debug("DEFINITELY 3")
                return "3"
        else:
            log.debug("DEFINITELY 1")
            return "1"
    elif not is_white(read_pixel(block, mid1)) and not is_white(
        read_pixel(block, mid2)
    ):
        log.debug("MIGHT BE 07")
        if is_white(read_pixel(block, bottom_left)):
            log.debug("DEFINITELY 0")
            return "0"
        elif is_white(read_pixel(block, top_left)):
            log.debug("DEFINITELY 7")
            return "7"
        else:
            log.debug("DEFINITELY BLANK")
            return " "
    else:
        log.debug("MIGHT BE 469")
        if is_white(read_pixel(block, mid_top)):
            log.debug("DEFINITELY 6")
            return "6"
        elif is_white(read_pixel(block, top_mid)):
            log.debug("DEFINITELY 9")
            return "9"
        else:
            log.debug("DEFINITELY 4")
            return "4"
    return "X"


def get_score_from_score_level_row(
    result_screen: NDArray,
    row_start_x: int,
    row_start_y: int,
    x_offset: int,
    y_offset: int,
    block_reader: Callable,
    score_digit_column_count: int = 4,
    ascii_print: bool = False,
) -> int:
    score_string = ""
    for column_index in range(score_digit_column_count):
        end_y = row_start_y + y_offset
        block_start_x = row_start_x + x_offset * column_index
        block_end_x = block_start_x + x_offset
        score_digit_block = get_rectanglular_subsection_from_frame(
            result_screen, row_start_y, block_start_x, end_y, block_end_x
        )
        # score_string += score_digit_reader(score_digit_block)
        score_string += block_reader(score_digit_block)

        # if logging.DEBUG > log.level:
        #    log.debug("ASCII\n" + get_array_as_ascii_art(score_digit_block))

    if re.match(score_string.strip(), r"^[^\d]+$"):
        return 0
    else:
        log.debug(f"score string {score_string}")
        log.debug(f"stripped {score_string.strip()}")
        return int(score_string.strip())


def get_score_from_score_area(
    result_screen: NDArray,
    start_x: int,
    start_y: int,
    x_offset: int,
    y_offset: int,
    block_reader: Callable,
    score_level_row_count: int = 5,
) -> list:
    scores: list[int] = []
    for row in range(score_level_row_count):
        row_start_y = start_y + row * y_offset
        score = get_score_from_score_level_row(
            result_screen, start_x, row_start_y, x_offset, y_offset, block_reader
        )
        scores.append(score)
    return scores


def get_speed_area_origin(left_side: bool, is_double: bool) -> tuple[int, int]:
    if left_side:
        start_x = 65
        start_y = 635
    else:
        start_x = 945
        start_y = 635
    return start_x, start_y


def get_score_area_origin(left_side: bool) -> tuple[int, int]:
    if left_side:
        start_x = 270
        start_y = 509
    else:
        start_x = 1151
        start_y = 509
    return start_x, start_y


def calculate_grade(perfect_greats: int, greats: int, note_count: int) -> str:
    max_score = note_count * 2
    score = perfect_greats * 2 + greats
    percentage = (Decimal(score) / Decimal(max_score)) * Decimal(100)
    grade = "F"
    if percentage >= Decimal("88.89"):
        grade = "AAA"
    elif percentage >= Decimal("77.78"):
        grade = "AA"
    elif percentage >= Decimal("66.67"):
        grade = "A"
    elif percentage >= Decimal("55.56"):
        grade = "B"
    elif percentage >= Decimal("44.44"):
        grade = "C"
    elif percentage >= Decimal("33.33"):
        grade = "D"
    elif percentage >= Decimal("22.22"):
        grade = "E"
    return grade


def get_clear_type_from_results_screen(frame: NDArray, left_side: bool) -> ClearType:
    start_y = 267
    end_y = 280
    if left_side:
        start_x = 254
        end_x = 333
    else:
        start_x = 1134
        end_x = 1213
    subs = get_rectanglular_subsection_from_frame(frame, start_y, start_x, end_y, end_x)
    far_left_middle = Point(x=2, y=6)
    top_mid = Point(x=32, y=0)
    top_mid_clear_area = Point(x=38, y=0)
    below_failed_a = Point(x=25, y=12)
    hard_dash = Point(x=17, y=4)
    easy_e_corner = Point(x=13, y=0)
    if is_bright(read_pixel(subs, far_left_middle)):
        log.debug("PROBABLY EXHARD or FULL_COMBO")
        if is_black(read_pixel(subs, top_mid)):
            log.debug("DEFINITELY FULL_COMBO")
            return ClearType.FULL_COMBO
        else:
            log.debug("DEFINITELY ClearType.EXHARD")
            return ClearType.EXHARD
    elif is_black(read_pixel(subs, top_mid_clear_area)):
        log.debug("PROBABLY FAILED OR NORMAL")
        if is_black(read_pixel(subs, below_failed_a)):
            log.debug("DEFINITELY NORMAL")
            return ClearType.NORMAL
        else:
            log.debug("DEFINITELY FAILED")
            return ClearType.FAILED
        return ClearType.FAILED
    else:
        log.debug("PROBABLY ASSIST, HARD, OR EASY")
        if not is_black(read_pixel(subs, hard_dash)):
            log.debug("PROBABLY EASY OR ASSIST")
            if is_black(read_pixel(subs, easy_e_corner)):
                log.debug("DEFINITELY EASY")
                return ClearType.EASY
            else:
                log.debug("DEFINITELY ASSIST")
                return ClearType.ASSIST
        else:
            log.debug("DEFINITELY HARD")
            return ClearType.HARD
    log.error("Could not determine ClearType")
    return ClearType.UNKNOWN


def get_score_from_result_screen(
    frame: NDArray, left_side: bool, is_double: bool, note_count: Optional[int] = None
) -> Score:
    score_area_x, score_area_y = get_score_area_origin(left_side)
    scores = get_score_from_score_area(
        frame,
        score_area_x,
        score_area_y,
        CONSTANTS.SCORE_DIGIT_X_OFFSET,
        CONSTANTS.SCORE_DIGIT_Y_OFFSET,
        score_digit_reader,
    )
    speed_area_x, speed_area_y = get_speed_area_origin(left_side, is_double)
    fast_slow = get_score_from_score_area(
        frame,
        speed_area_x,
        speed_area_y,
        CONSTANTS.FAST_SLOW_X_OFFSET,
        CONSTANTS.FAST_SLOW_Y_OFFSET,
        fast_slow_digit_reader,
        2,
    )
    if note_count is None:
        grade = "X"
    else:
        grade = calculate_grade(scores[0], scores[1], note_count)
    clear_type = get_clear_type_from_results_screen(frame, left_side)
    scores.extend(fast_slow)
    scores.append(grade)
    scores.append(clear_type.name)
    return Score(*scores)


def get_note_count(frame: NDArray) -> int:
    notes_top_left_x = 678
    notes_top_left_y = 686
    notes_bottom_right_y = 700
    block_width = 14
    digits_sum = 0

    left_curve_indent = Point(x=4, y=8)
    bottom_middle = Point(x=6, y=12)
    top_right_curve = Point(x=8, y=4)
    top_mid_left = Point(x=3, y=4)
    top_center = Point(x=6, y=4)
    bottom_right_curve = Point(x=8, y=9)
    top_left_of_seven = Point(x=4, y=1)
    top_point_of_four = Point(x=9, y=1)

    for digit in range(4):
        magnitude = 10 ** (3 - digit)
        block_top_left_x = notes_top_left_x + (digit * block_width)
        block_top_left_y = notes_top_left_y
        block_bottom_right_x = notes_top_left_x + ((digit + 1) * block_width)
        block_bottom_right_y = notes_bottom_right_y
        digit_area = get_rectanglular_subsection_from_frame(
            frame=frame,
            top_left_x=block_top_left_x,
            top_left_y=block_top_left_y,
            bottom_right_x=block_bottom_right_x,
            bottom_right_y=block_bottom_right_y,
        )
        if is_black(read_pixel(digit_area, left_curve_indent)):
            log.debug("PROBABLY 359")
            if not is_black(read_pixel(digit_area, top_right_curve)):
                log.debug("PROBABLY 39")
                if is_black(read_pixel(digit_area, top_mid_left)):
                    log.debug("DEFINITELY 3")
                    digits_sum += magnitude * 3
                else:
                    log.debug("DEFINITELY 9")
                    digits_sum += magnitude * 9
            else:
                log.debug("DEFINITELY 5")
                digits_sum += magnitude * 5
        elif is_black(read_pixel(digit_area, bottom_middle)):
            log.debug("PROBABLY 128")
            if is_black(read_pixel(digit_area, top_center)):
                log.debug("PROBABLY 28")
                if is_black(read_pixel(digit_area, bottom_right_curve)):
                    log.debug("DEFINITELY 2")
                    digits_sum += magnitude * 2
                else:
                    log.debug("DEFINITELY 8")
                    digits_sum += magnitude * 8
            else:
                log.debug("DEFINITELY 1")
                digits_sum += magnitude * 1
        else:
            log.debug("PROBABLY 0467")
            if not is_black(read_pixel(digit_area, top_right_curve)):
                log.debug("PROBABLY 047")
                if is_black(read_pixel(digit_area, top_point_of_four)):
                    log.debug("PROBABLY 47")
                    if is_black(read_pixel(digit_area, top_left_of_seven)):
                        log.debug("DEFINITELY 7")
                        digits_sum += magnitude * 7
                    else:
                        log.debug("DEFINITELY 4")
                        digits_sum += magnitude * 4
                else:
                    log.debug("DEFINITELY 0")
                    digits_sum += magnitude * 0
                pass
            else:
                log.debug("DEFINITELY 6")
                digits_sum += magnitude * 6

    return digits_sum
