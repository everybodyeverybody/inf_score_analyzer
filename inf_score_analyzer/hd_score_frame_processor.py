#!/usr/bin/env python3
import io
import uuid
import logging
import sqlite3
from typing import Set
from decimal import Decimal
from datetime import datetime, timezone

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
    get_numbers_from_area,
)
from . import constants as CONSTANTS

log = logging.getLogger(__name__)


# TODO: this needs a refactor with Friction!Function breaking
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
            referenced_textage_id = next(iter(metadata_title))
            log.info("Using metadata title: {referenced_textage_id}")
        else:
            log.warning(f"Found too much metadata, {metadata_title}, tiebreaking")
            referenced_textage_id = metadata_lookup_tiebreaker(metadata_title, title)
            log.warning(f"Tiebreaker found: {referenced_textage_id}")
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
    """
    Calculates the levenshtein distance on songs that match
    play metadata (note count, difficulty, bpm) versus
    what is provided by our OCR library to determine
    the song title.

    In cases of ties, this raises an exception, indicating
    we have missed some special case or overlap, or that
    OCR is underperforming or outputting garbage.

    https://en.wikipedia.org/wiki/Levenshtein_distance
    """
    lowest_score = -1
    lowest_textage_id = None
    lowest_has_tie = False
    app_db_connection = sqlite3.connect(CONSTANTS.APP_DB)
    db_cursor = app_db_connection.cursor()
    ids_as_string = ",".join([f"'{id}'" for id in metadata_titles])
    query = (
        "select textage_id, artist, title "
        "from songs "
        f"where textage_id in ({ids_as_string})"
    )
    results = db_cursor.execute(query).fetchall()
    scores = {}
    for textage_id, artist, title in results:
        score = polyleven.levenshtein(ocr_titles.en_artist, artist)
        score += polyleven.levenshtein(ocr_titles.en_title, title)
        score += polyleven.levenshtein(ocr_titles.jp_artist, artist)
        score += polyleven.levenshtein(ocr_titles.jp_title, title)
        scores[textage_id] = score
    # We only care about ties for the lowest score
    # so we sort to get the elements in ascending score order
    sorted_scores = {t: scores[t] for t in sorted(scores, key=scores.get)}  # type: ignore
    for textage_id, score in sorted_scores.items():
        if lowest_score != -1 and score == lowest_score:
            lowest_has_tie = True
        if lowest_score == -1 or score < lowest_score:
            lowest_textage_id = textage_id
            lowest_score = score
    if lowest_has_tie or lowest_textage_id is None:
        raise RuntimeError(
            "Couldn't figure out song title from OCR data and metadata. "
            f"song metadata: {metadata_titles} "
            f"ocr data: {ocr_titles} "
            f"similarity scores: {sorted_scores} "
        )
    return lowest_textage_id


def hd_fast_slow_digit_reader(block: NDArray) -> int:
    top_left = Point(x=1, y=1)
    top_left_gap = Point(x=1, y=3)
    bottom_right_gap = Point(x=12, y=10)
    top_right_gap = Point(x=12, y=4)
    bottom_left_gap = Point(x=1, y=10)
    middle_top = Point(x=8, y=5)
    middle_third_row_center = Point(x=8, y=7)
    if is_white(block, top_left):
        log.debug("MIGHT BE 2345")
        if is_white(block, top_left_gap):
            log.debug("MIGHT BE 45")
            if is_white(block, top_right_gap):
                log.debug("DEFINITELY 4")
                return 4
            else:
                log.debug("DEFINITELY 5")
                return 5
        else:
            log.debug("MIGHT BE 23")
            if is_white(block, bottom_right_gap):
                log.debug("DEFINITELY 3")
                return 3
            else:
                log.debug("DEFINITELY 2")
                return 2
    else:
        log.debug("MIGHT BE 678901_")
        if is_white(block, top_right_gap):
            log.debug("MIGHT BE 9780")
            if is_white(block, middle_third_row_center):
                log.debug("MIGHT BE 89")
                if is_white(block, bottom_left_gap):
                    log.debug("DEFINITELY 8")
                    return 8
                else:
                    log.debug("DEFINITELY 9")
                    return 9
            else:
                log.debug("MIGHT BE 70")
                if is_white(block, bottom_left_gap):
                    log.debug("DEFINITELY 0")
                    return 0
                else:
                    log.debug("DEFINITELY 7")
                    return 7
        else:
            log.debug("MIGHT BE 61_")
            if is_white(block, middle_top):
                log.debug("MIGHT BE 61")
                if is_white(block, top_left_gap):
                    log.debug("DEFINITELY 6")
                    return 6
                else:
                    log.debug("DEFINITELY 1")
                    return 1
            else:
                log.debug("DEFINITELY ' '")
                return 0


def hd_score_digit_reader(block: NDArray) -> int:
    top_left_gap = Point(3, 5)
    exact_middle = Point(12, 8)
    top_right_gap = Point(22, 5)
    bottom_left_gap = Point(3, 11)
    bottom_right_gap = Point(22, 11)
    bottom_middle = Point(12, 14)
    top_middle = Point(12, 2)
    log.debug("READING")
    if is_white(block, top_left_gap):
        log.debug("MIGHT BE 0456789")
        if is_white(block, bottom_left_gap):
            log.debug("MIGHT BE 068")
            if is_white(block, exact_middle):
                log.debug("MIGHT BE 68")
                if is_white(block, top_right_gap):
                    log.debug("DEFINITELY 8")
                    return 8
                else:
                    log.debug("DEFINITELY 6")
                    return 6
            else:
                log.debug("DEFINITELY 0")
                return 0
        else:
            log.debug("MIGHT BE 4579")
            if is_white(block, bottom_middle):
                log.debug("MIGHT BE 59")
                if is_white(block, top_right_gap):
                    log.debug("DEFINITELY 9")
                    return 9
                else:
                    log.debug("DEFINITELY 5")
                    return 5
            else:
                log.debug("MIGHT BE 47")
                if is_white(block, top_middle):
                    log.debug("DEFINITELY 7")
                    return 7
                else:
                    log.debug("DEFINITELY 4")
                    return 4
    else:
        log.debug("MIGHT BE _123")
        if is_white(block, top_right_gap):
            log.debug("MIGHT BE 23")
            if is_white(block, bottom_right_gap):
                log.debug("DEFINITELY 3")
                return 3
            else:
                log.debug("DEFINITELY 2")
                return 2
        else:
            log.debug("MIGHT BE _1")
            if is_white(block, exact_middle):
                log.debug("DEFINITELY 1")
                return 1
            else:
                log.debug("DEFINITELY ' '")
                return 0


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


def hd_get_clear_type_from_results_screen(frame: NDArray, left_side: bool) -> ClearType:
    start_y = 417
    end_y = 437
    if left_side:
        start_x = 366
        end_x = 512
    else:
        raise RuntimeError("2p score type not implemented")
    subs = get_rectanglular_subsection_from_frame(frame, start_y, start_x, end_y, end_x)
    top_left = Point(y=5, x=23)
    first_letter_black = Point(y=10, x=25)
    easy_clear_r = Point(y=6, x=113)
    combo_or_clear = Point(y=2, x=86)
    clear_or_hard = Point(y=5, x=86)
    if is_bright(subs, top_left):
        log.debug("PROBABLY ASSIST EASY EXH")
        if is_bright(subs, first_letter_black):
            log.debug("PROBABLY EASY EXH")
            if is_bright(subs, easy_clear_r):
                log.debug("DEFINITELY EASY")
                return ClearType.EASY
            else:
                log.debug("DEFINITELY EXHARD")
                return ClearType.EXHARD
        else:
            log.debug("DEFINITELY ASSIST")
            return ClearType.ASSIST
    else:
        log.debug("PROBABLY FAILED NORMAL HARD FULLCOMBO")
        if not is_bright(subs, easy_clear_r):
            log.debug("DEFINITELY FAILED")
            return ClearType.FAILED
        elif not is_bright(subs, combo_or_clear):
            log.debug("DEFINITELY FULL_COMBO")
            return ClearType.FULL_COMBO
        elif is_bright(subs, clear_or_hard):
            log.debug("DEFINITELY NORMAL")
            return ClearType.NORMAL
        else:
            log.debug("DEFINITELY HARD")
            return ClearType.HARD
    return ClearType.UNKNOWN


def get_note_count(frame: NDArray) -> int:
    return get_numbers_from_area(frame, CONSTANTS.NOTES_AREA, hd_note_count_reader)[0]


def get_score_from_result_screen(
    frame: NDArray, left_side: bool, is_double: bool
) -> Score:
    if left_side:
        score_area = CONSTANTS.SCORE_P1_AREA
        fast_slow_area = CONSTANTS.FAST_SLOW_P1_AREA
    else:
        raise RuntimeError("2p is not yet supported")
    scores = get_numbers_from_area(frame, score_area, hd_score_digit_reader)
    fast_slow = get_numbers_from_area(frame, fast_slow_area, hd_fast_slow_digit_reader)
    note_count = get_note_count(frame)
    log.debug(f"SCORES: {scores}")
    log.debug(f"FAST_SLOW {fast_slow}")
    log.debug(f"NOTE COUNT {note_count}")
    if note_count is None:
        grade = "X"
    else:
        grade = calculate_grade(scores[0], scores[1], note_count)
    clear_type = hd_get_clear_type_from_results_screen(frame, left_side)
    score_data: list[int | str] = []
    score_data.extend(scores)
    score_data.extend(fast_slow)
    score_data.append(grade)
    score_data.append(clear_type.name)
    log.debug(score_data)
    return Score(*score_data)


def hd_note_count_reader(block: NDArray) -> int:
    top_left = Point(x=1, y=1)
    top_left_gap = Point(x=1, y=3)
    bottom_right_gap = Point(x=14, y=12)
    top_right_gap = Point(x=14, y=3)
    bottom_left_gap = Point(x=1, y=10)
    middle_top = Point(x=8, y=5)
    middle_third_row_center = Point(x=10, y=9)
    middle_middle = Point(x=10, y=8)
    if is_white(block, top_left):
        log.debug("MIGHT BE 2345")
        if is_white(block, top_left_gap):
            log.debug("MIGHT BE 45")
            if is_white(block, top_right_gap):
                log.debug("DEFINITELY 4")
                return 4
            else:
                log.debug("DEFINITELY 5")
                return 5
        else:
            log.debug("MIGHT BE 23")
            if is_white(block, bottom_right_gap):
                log.debug("DEFINITELY 3")
                return 3
            else:
                log.debug("DEFINITELY 2")
                return 2
    else:
        log.debug("MIGHT BE 678901_")
        if is_white(block, top_right_gap):
            log.debug("MIGHT BE 9780")
            if is_white(block, bottom_left_gap):
                log.debug("MIGHT BE 80")
                if is_white(block, middle_middle):
                    log.debug("DEFINITELY 8")
                    return 8
                else:
                    log.debug("DEFINITELY 0")
                    return 0
            else:
                log.debug("MIGHT BE 79")
                if is_white(block, middle_third_row_center):
                    log.debug("DEFINITELY 9")
                    return 9
                else:
                    log.debug("DEFINITELY 7")
                    return 7
        else:
            log.debug("MIGHT BE 61_")
            if is_white(block, middle_top):
                log.debug("MIGHT BE 61")
                if is_white(block, top_left_gap):
                    log.debug("DEFINITELY 6")
                    return 6
                else:
                    log.debug("DEFINITELY 1")
                    return 1
            else:
                log.debug("DEFINITELY ' '")
                return 0
