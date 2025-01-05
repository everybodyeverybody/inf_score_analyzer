#!/usr/bin/env python3
import logging

import cv2 as cv  # type: ignore
import pytesseract  # type: ignore
from numpy.typing import NDArray  # type: ignore

from .local_dataclasses import (
    Point,
    Score,
    ClearType,
    Difficulty,
    DifficultyType,
    SingleOrDouble,
    GameStatePixel,
    OCRSongTitles,
    OCRGenres,
    NumberArea,
    TitleType,
)

from .song_reference import SongReference
from .frame_utilities import (
    get_rectanglular_subsection_from_frame,
    is_white,
    is_black,
    check_point_color,
    is_bright,
    get_numbers_from_area,
    polarize_area,
    grayscale_area,
    flatten_difficulty_gradients,
    check_pixel_color_in_frame,
)
from . import sqlite_client
from . import constants as CONSTANTS
from . import text_gradients
from .score_frame_processor import calculate_grade_from_total_score

from typing import Optional

log = logging.getLogger(__name__)


def __read_difficulty_type(block: NDArray) -> DifficultyType:
    bottom_row_start = Point(y=25, x=5)
    bottom_row_end = 44
    another_red = (83, 89, 252)
    hyper_orange = (9, 215, 255)
    normal_blue = (255, 227, 8)
    legg_purple = (247, 140, 249)
    color_count = {another_red: 0, hyper_orange: 0, normal_blue: 0, legg_purple: 0}
    while bottom_row_start.x <= bottom_row_end:
        for color in color_count:
            if check_point_color(block, bottom_row_start, color):
                color_count[color] += 1
        bottom_row_start.x += 1
    highest_color = None
    highest_count = -1
    for color in color_count:
        if color_count[color] > highest_count:
            highest_color = color
            highest_count = color_count[color]
    difficulty_type = DifficultyType.UNKNOWN
    if highest_color == another_red:
        difficulty_type = DifficultyType.ANOTHER
    elif highest_color == hyper_orange:
        difficulty_type = DifficultyType.HYPER
    elif highest_color == normal_blue:
        difficulty_type = DifficultyType.NORMAL
    elif highest_color == legg_purple:
        difficulty_type = DifficultyType.LEGGENDARIA
    return difficulty_type


def __read_difficulty(
    block: NDArray, is_double: bool
) -> tuple[Difficulty, DifficultyType]:
    difficulty_type = __read_difficulty_type(block)
    if is_double:
        difficulty = Difficulty(difficulty_type.value + SingleOrDouble.DP.value)
    else:
        difficulty = Difficulty(difficulty_type.value + SingleOrDouble.SP.value)
    return difficulty, difficulty_type


def __read_difficulty_level(block: NDArray, difficulty_type: DifficultyType):
    center = Point(y=15, x=22)
    lower_middle = Point(y=25, x=22)
    top_middle = Point(y=2, x=22)
    bottom_left = Point(y=23, x=9)
    top_right_gap = Point(y=9, x=35)
    # bottom_right_gap = Point(y=18, x=35)
    bottom_right_gap = Point(y=19, x=35)
    bottom_left_gap = Point(y=18, x=10)
    middle_left = Point(y=14, x=11)

    if is_white(block, center):
        log.debug("PROBABLY 1 2 3 4 5 6 8 9 12")
        if not is_white(block, bottom_left):
            log.debug("PROBABLY 1 4 9")
            if not is_white(block, top_middle):
                log.debug("DEFINITELY 4")
                return 4
            elif is_white(block, top_right_gap):
                log.debug("DEFINITELY 9")
                return 9
            else:
                log.debug("DEFINITELY 1")
                return 1
        elif is_white(block, bottom_right_gap):
            log.debug("PROBABLY 3 5 6 8")
            if not is_white(block, middle_left):
                log.debug("DEFINITELY 3")
                return 3
            elif is_white(block, top_right_gap):
                log.debug("DEFINITELY 8")
                return 8
            elif is_white(block, bottom_left_gap):
                log.debug("DEFINITELY 6")
                return 6
            else:
                log.debug("DEFINITELY 5")
                return 5
        else:
            log.debug("PROBABLY 2 12")
            if is_white(block, top_right_gap):
                log.debug("DEFINITELY 2")
                return 2
            else:
                log.debug("DEFINITELY 12")
                return 12
    else:
        log.debug("PROBABLY 7 10 11")
        if is_white(block, lower_middle):
            log.debug("DEFINITELY 10")
            return 10
        elif not is_white(block, bottom_left):
            log.debug("DEFINITELY 7")
            return 7
        else:
            log.debug("DEFINITELY 11")
            return 11


def read_sp_dp():
    return False


def read_difficulty(frame: NDArray) -> tuple[Difficulty, int]:
    top_left_y = 526
    top_left_x = 1249
    bottom_right_y = 553
    bottom_right_x = 1294
    is_double = read_sp_dp()
    difficulty_slice = get_rectanglular_subsection_from_frame(
        frame, top_left_y, top_left_x, bottom_right_y, bottom_right_x
    )
    difficulty, difficulty_type = __read_difficulty(difficulty_slice, is_double)
    # TODO: make this a match expr
    if difficulty_type == DifficultyType.NORMAL:
        gradient = text_gradients.DIFFICULTY_NORMAL
    elif difficulty_type == DifficultyType.HYPER:
        gradient = text_gradients.DIFFICULTY_HYPER
    elif difficulty_type == DifficultyType.ANOTHER:
        gradient = text_gradients.DIFFICULTY_ANOTHER
    elif difficulty_type == DifficultyType.LEGGENDARIA:
        gradient = text_gradients.DIFFICULTY_LEGGENDARIA
    else:
        raise RuntimeError(
            "Could not determine difficulty type from song select screenshot."
        )
    flatten_difficulty_gradients(
        frame,
        top_left_y,
        top_left_x,
        bottom_right_y,
        bottom_right_x,
        gradient,
    )
    level = __read_difficulty_level(difficulty_slice, difficulty_type)
    return difficulty, level


def read_clear_type(frame: NDArray) -> ClearType:
    top_left_y = 888
    top_left_x = 64
    bottom_right_y = 906
    bottom_right_x = 266
    clear_type_slice = get_rectanglular_subsection_from_frame(
        frame, top_left_y, top_left_x, bottom_right_y, bottom_right_x
    )
    fc_clear_a = Point(y=6, x=178)
    fc_clear_r = Point(y=6, x=190)
    first_letter = Point(y=9, x=10)
    exhard_pixel = GameStatePixel(
        y=first_letter.y, x=first_letter.x, b=117, g=227, r=255
    )
    hard_pixel = GameStatePixel(y=first_letter.y, x=first_letter.x, b=97, g=97, r=255)
    easy_pixel = GameStatePixel(y=first_letter.y, x=first_letter.x, b=124, g=255, r=189)
    clear_pixel = GameStatePixel(y=9, x=3, b=255, g=234, r=94)
    if is_bright(clear_type_slice, fc_clear_a) and is_bright(
        clear_type_slice, fc_clear_r
    ):
        log.debug("DEFINITELY FC")
        return ClearType.FULL_COMBO
    elif check_pixel_color_in_frame(clear_type_slice, exhard_pixel):
        log.debug("DEFINITELY EXHARD")
        return ClearType.EXHARD
    elif check_pixel_color_in_frame(clear_type_slice, hard_pixel):
        log.debug("DEFINITELY HARD")
        return ClearType.HARD
    elif check_pixel_color_in_frame(clear_type_slice, easy_pixel):
        log.debug("DEFINITELY EASY")
        return ClearType.EASY
    elif check_pixel_color_in_frame(clear_type_slice, clear_pixel):
        log.debug("DEFINITYELY NORMAL")
        return ClearType.NORMAL
    # TODO: get assist clear and failed
    return ClearType.NO_PLAY


def process_song_select_bpm_digits(block: NDArray) -> int:
    """
    This is worse than any others as the area is noisy with
    white and black colors, so we can only check for specific points for
    each number where there are black segments that do not overlap with
    other segments.
    """
    # TODO: redo this
    digit_check = {
        0: [
            Point(y=7, x=7),
            Point(y=8, x=7),
            Point(y=9, x=7),
            Point(y=10, x=7),
            Point(y=11, x=7),
            Point(y=12, x=7),
            Point(y=13, x=7),
            Point(y=7, x=12),
            Point(y=7, x=13),
            Point(y=7, x=14),
            Point(y=7, x=15),
            Point(y=7, x=16),
            Point(y=7, x=17),
        ],
        1: [
            Point(y=5, x=18),
            Point(y=6, x=18),
            Point(y=7, x=18),
            Point(y=8, x=18),
            Point(y=9, x=18),
        ],
        2: [
            Point(y=13, x=26),
            Point(y=14, x=26),
            Point(y=15, x=26),
            Point(y=16, x=26),
            Point(y=7, x=2),
            Point(y=7, x=3),
            Point(y=7, x=4),
            Point(y=7, x=5),
        ],
        3: [Point(y=10, x=3), Point(y=11, x=3), Point(y=12, x=3), Point(y=13, x=3)],
        4: [
            Point(y=11, x=19),
            Point(y=11, x=20),
            Point(y=11, x=21),
            Point(y=11, x=22),
            Point(y=10, x=1),
            Point(y=11, x=1),
            Point(y=12, x=1),
            Point(y=13, x=1),
        ],
        5: [
            Point(y=14, x=2),
            Point(y=14, x=3),
            Point(y=14, x=4),
            Point(y=14, x=5),
            Point(y=7, x=23),
            Point(y=7, x=24),
            Point(y=7, x=25),
            Point(y=7, x=26),
            Point(y=7, x=27),
        ],
        6: [Point(y=3, x=12), Point(y=4, x=12), Point(y=5, x=12), Point(y=6, x=12)],
        9: [Point(y=17, x=15), Point(y=18, x=15), Point(y=19, x=15), Point(y=20, x=15)],
        8: [
            Point(y=14, x=7),
            Point(y=14, x=8),
            Point(y=14, x=9),
            Point(y=14, x=10),
            Point(y=14, x=11),
            Point(y=14, x=12),
            Point(y=14, x=13),
            Point(y=14, x=14),
            Point(y=14, x=15),
            Point(y=14, x=16),
            Point(y=14, x=17),
            Point(y=14, x=18),
            Point(y=14, x=19),
            Point(y=14, x=18),
        ],
        7: [
            Point(y=3, x=1),
            Point(y=4, x=1),
            Point(y=5, x=1),
            Point(y=6, x=1),
        ],
    }
    true_set = frozenset([True])
    for number, points in digit_check.items():
        match_set = set([])
        for point in points:
            match_set.add(is_black(block, point))
        if match_set == true_set:
            log.debug(f"DEFINITELY {number}")
            return number
    return 0


def read_max_bpm(frame: NDArray):
    top_left_y = 470
    top_left_x = 715
    # bottom_right_y = 493
    # bottom_right_x = 805
    max_bpm_area = NumberArea(
        start_x=top_left_x,
        start_y=top_left_y,
        x_offset=30,
        y_offset=24,
        rows=1,
        digits_per_row=3,
        name="song_select_max_bpm",
    )
    numbers = get_numbers_from_area(frame, max_bpm_area, process_song_select_bpm_digits)
    return numbers[0]


def soflan_processor(block: NDArray):
    tilde_black_edges = [
        Point(x=19, y=15),
        Point(x=20, y=15),
        Point(x=21, y=15),
        Point(x=22, y=15),
    ]
    tilde_white_edges = [
        Point(x=19, y=14),
        Point(x=20, y=14),
        Point(x=21, y=14),
        Point(x=22, y=14),
    ]
    truth_set = frozenset([True])
    match_set = set([])
    for point in tilde_black_edges:
        match_set.add(is_black(block, point))
    for point in tilde_white_edges:
        match_set.add(is_white(block, point))
    log.debug(f"TILDES {match_set} {truth_set}")
    if match_set == truth_set:
        return 1
    return 0


def read_soflan(frame: NDArray) -> bool:
    top_left_y = 473
    top_left_x = 682
    # bottom_right_y = 490
    # bottom_right_x = 713
    soflan_area = NumberArea(
        start_x=top_left_x,
        start_y=top_left_y,
        x_offset=32,
        y_offset=18,
        rows=1,
        digits_per_row=1,
        name="song_select_soflan_tilde",
    )
    numbers = get_numbers_from_area(frame, soflan_area, soflan_processor)[0]
    log.debug(f"DOES MATCH? {numbers} {numbers == 1}")
    return numbers == 1


def read_min_bpm(frame: NDArray) -> int:
    top_left_y = 470
    top_left_x = 591
    # bottom_right_y = 805
    # bottom_right_x = 681
    min_bpm_area = NumberArea(
        start_x=top_left_x,
        start_y=top_left_y,
        x_offset=30,
        y_offset=24,
        rows=1,
        digits_per_row=3,
        name="song_select_min_bpm",
    )
    numbers = get_numbers_from_area(
        frame, min_bpm_area, process_song_select_bpm_digits
    )[0]
    return numbers


def read_bpm(frame: NDArray) -> tuple[int, int]:
    max_bpm = read_max_bpm(frame)
    min_bpm = max_bpm
    has_soflan = read_soflan(frame)
    log.debug(f"HAS SOFLAN? {has_soflan}")
    if has_soflan:
        min_bpm = read_min_bpm(frame)
    return min_bpm, max_bpm


def read_genre(frame: NDArray) -> OCRGenres:
    top_left_y = 278
    top_left_x = 211
    bottom_right_x = 913
    bottom_right_y = 305
    _ = grayscale_area(frame, top_left_y, top_left_x, bottom_right_y, bottom_right_x)
    _ = polarize_area(
        frame,
        top_left_y,
        top_left_x,
        bottom_right_y,
        bottom_right_x,
        cutoff_bgr=(240, 240, 240),
    )
    genre_slice = get_rectanglular_subsection_from_frame(
        frame, top_left_y, top_left_x, bottom_right_y, bottom_right_x
    )
    en_genre = str.strip(
        pytesseract.image_to_string(
            genre_slice, lang="eng", config=CONSTANTS.PYTESSERACT_LINE_OF_TEXT
        )
    )
    jp_genre = str.strip(
        pytesseract.image_to_string(
            genre_slice, lang="jpn", config=CONSTANTS.PYTESSERACT_LINE_OF_TEXT
        )
    )
    log.debug(f"ENG GENRE: {en_genre}")
    log.debug(f"JPN GENRE: {jp_genre}")
    return OCRGenres(en_genre=en_genre, jp_genre=jp_genre)


def __read_title_type(
    song_select_title_slice: NDArray, difficulty: Difficulty
) -> TitleType:
    if difficulty in [Difficulty.SP_LEGGENDARIA, Difficulty.DP_LEGGENDARIA]:
        return TitleType.LEGGENDARIA
    lines_to_read = [13, 23, 33]
    color_matches = {
        TitleType.NORMAL: 0,
        TitleType.INFINITAS: 0,
        TitleType.LEGGENDARIA: 0,
    }
    max_x = song_select_title_slice.shape[1]
    for y in lines_to_read:
        for x in range(max_x):
            color = (
                song_select_title_slice[y][x][0],
                song_select_title_slice[y][x][1],
                song_select_title_slice[y][x][2],
            )
            if color in text_gradients.TITLE_NORMAL:
                color_matches[TitleType.NORMAL] += 1
            if color in text_gradients.TITLE_INFINITAS:
                color_matches[TitleType.INFINITAS] += 1
            if color in text_gradients.TITLE_LEGGENDARIA:
                color_matches[TitleType.LEGGENDARIA] += 1
    largest_count = 0
    found_title_type = TitleType.NORMAL
    log.debug(f"TITLE TYPE COLOR MATCHES: {color_matches}")
    for title_type, count in color_matches.items():
        if count > largest_count:
            largest_count = count
            found_title_type = title_type
    return found_title_type


def __read_title(frame: NDArray, title_type: TitleType):
    if title_type == TitleType.LEGGENDARIA:
        gradient = text_gradients.TITLE_LEGGENDARIA
    elif title_type == TitleType.INFINITAS:
        gradient = text_gradients.TITLE_INFINITAS
    else:
        gradient = text_gradients.TITLE_NORMAL
    top_left_y = 517
    top_left_x = 1305
    bottom_right_x = 1871
    bottom_right_y = 562
    # log.debug(dump_colors(frame, 537, 1432, 552, 1434))
    song_select_title_slice = get_rectanglular_subsection_from_frame(
        frame, top_left_y, top_left_x, bottom_right_y, bottom_right_x
    )
    flatten_difficulty_gradients(
        frame,
        top_left_y,
        top_left_x,
        bottom_right_y,
        bottom_right_x,
        gradient,
        match_level=0,
        miss_level=255,
    )
    # show_frame(song_select_title_slice)
    scaled_slice = cv.resize(song_select_title_slice, None, fx=2, fy=2)
    en_title = str.strip(
        pytesseract.image_to_string(
            scaled_slice, lang="eng", config=CONSTANTS.PYTESSERACT_LINE_OF_TEXT
        )
    )
    jp_title = str.strip(
        pytesseract.image_to_string(
            scaled_slice, lang="jpn", config=CONSTANTS.PYTESSERACT_LINE_OF_TEXT
        )
    )
    en_title = en_title.replace("\n", "")
    jp_title = jp_title.replace("\n", "")
    log.debug(f"ENG SONG_SELECT_TITLE SONG: {en_title} ")
    log.debug(f"JPN SONG_SELECT_TITLE SONG: {jp_title}")

    return OCRSongTitles(
        en_title=en_title, en_artist="", jp_title=jp_title, jp_artist=""
    )


def __read_artist(frame: NDArray):
    top_left_y = 421
    top_left_x = 211
    bottom_right_x = 913
    bottom_right_y = 452
    _ = grayscale_area(frame, top_left_y, top_left_x, bottom_right_y, bottom_right_x)
    polarized_frame = polarize_area(
        frame, top_left_y, top_left_x, bottom_right_y, bottom_right_x
    )
    artist_slice = get_rectanglular_subsection_from_frame(
        polarized_frame,
        top_left_y,
        top_left_x,
        bottom_right_y,
        bottom_right_x,
    )
    en_artist = str.strip(
        pytesseract.image_to_string(
            artist_slice, lang="eng", config=CONSTANTS.PYTESSERACT_LINE_OF_TEXT
        )
    )
    jp_artist = str.strip(
        pytesseract.image_to_string(
            artist_slice, lang="jpn", config=CONSTANTS.PYTESSERACT_LINE_OF_TEXT
        )
    )
    log.debug(f"ENG ARTIST: {en_artist}")
    log.debug(f"JPN ARTIST: {jp_artist}")
    return OCRSongTitles(
        en_title="", en_artist=en_artist, jp_title="", jp_artist=jp_artist
    )


def process_score_and_miss_area(block: NDArray) -> int:
    bottom_left = Point(y=13, x=3)
    bottom_right = Point(y=13, x=16)
    center = Point(y=7, x=9)
    center_left = Point(y=7, x=3)
    center_right = Point(y=7, x=16)
    top_left_black = Point(y=4, x=3)
    top_right_black = Point(y=4, x=16)
    bottom_left_black = Point(y=11, x=3)
    top_center = Point(y=2, x=9)
    if not is_white(block, center):
        log.debug("PROBABLY 07")
        if not is_white(block, bottom_right):
            log.debug("DEFINITELY 0")
            return 0
        elif is_white(block, center_left):
            log.debug("DEFINITELY 0")
            return 0
        else:
            log.debug("DEFINITELY 7")
            return 7
    elif is_white(block, top_left_black):
        log.debug("PROBABLY 45689")
        if is_white(block, bottom_left_black):
            log.debug("PROBABLY 68")
            if is_white(block, top_right_black):
                log.debug("DEFINITELY 8")
                return 8
            else:
                log.debug("DEFINITELY 6")
                return 6
        else:
            log.debug("PROBABLY 459")
            if is_white(block, bottom_left):
                log.debug("DEFINITELY 5")
                return 5
            elif is_white(block, top_center):
                log.debug("DEFINITELY 9")
                return 9
            else:
                log.debug("DEFINITELY 4")
                return 4

    else:
        log.debug("PROBABLY 123")
        if is_white(block, center_right):
            log.debug("PROBABLY 23")
            if is_white(block, bottom_left_black):
                log.debug("DEFINITELY 2")
                return 2
            else:
                log.debug("DEFINITELY 3")
                return 3
        else:
            log.debug("DEFINITELY 1")
            return 1
    return 0


def read_total_score(frame: NDArray) -> int:
    score_area_start_x = 210
    score_area_start_y = 834
    # score_area_end_x = 295
    # score_area_end_y = 850
    score_area = NumberArea(
        start_x=score_area_start_x,
        start_y=score_area_start_y,
        x_offset=22,
        y_offset=16,
        rows=1,
        digits_per_row=4,
        name="song_select_score",
    )
    numbers = get_numbers_from_area(frame, score_area, process_score_and_miss_area)
    return numbers[0]


def read_miss_count(frame: NDArray):
    score_area_start_x = 210
    score_area_start_y = 862
    # score_area_end_x = 295
    # score_area_end_y = 850
    score_area = NumberArea(
        start_x=score_area_start_x,
        start_y=score_area_start_y,
        x_offset=22,
        y_offset=16,
        rows=1,
        digits_per_row=4,
        name="song_select_score",
    )
    numbers = get_numbers_from_area(frame, score_area, process_score_and_miss_area)
    return numbers[0]


def read_textage_id(
    frame: NDArray,
    song_reference: SongReference,
    bpm: tuple[int, int],
    difficulty: Difficulty,
    difficulty_level: int,
) -> tuple[Optional[str], OCRSongTitles]:
    # TODO: redo the workflow here such that we
    # can attempt to re-read stuff if we cannot
    # resolve it from title/artist
    title_type = __read_title_type(frame, difficulty)
    title = __read_title(frame, title_type)
    # large_title = __read_large_title(frame, title_type)
    artist = __read_artist(frame)
    ocr_genres = read_genre(frame)
    ocr_titles = OCRSongTitles(
        en_title=title.en_title,
        en_artist=artist.en_artist,
        jp_title=title.jp_title,
        jp_artist=artist.jp_artist,
    )
    log.debug(f"OCR GENRE IS {ocr_genres}")
    log.debug(f"OCR TITLES ARE {ocr_titles}")
    likely_textage_ids = song_reference.resolve_by_song_select_metadata(
        difficulty.name, difficulty_level, bpm, ocr_titles, ocr_genres
    )
    log.debug(f"LIKELY IDS: {likely_textage_ids}")
    if len(likely_textage_ids) != 1:
        tiebreak_data = sqlite_client.read_tiebreak_data(likely_textage_ids)
        textage_id = song_reference.resolve_ocr_and_metadata(
            ocr_titles,
            likely_textage_ids,
            tiebreak_data,
            difficulty.name,
            difficulty_level,
            ocr_genres,
        )
        log.debug(textage_id)
    else:
        textage_id = likely_textage_ids.pop()
    log.debug(textage_id)
    return textage_id, ocr_titles


def read_score_and_song_metadata(
    frame: NDArray, song_reference: SongReference
) -> tuple[str, Score, Difficulty, OCRSongTitles]:
    difficulty, level = read_difficulty(frame)
    total_score = read_total_score(frame)
    clear_type = read_clear_type(frame)
    miss_count = read_miss_count(frame)
    bpm = read_bpm(frame)
    log.debug(f"BPM IS {bpm}")
    log.debug(f"DIFFICULTY IS {difficulty.name} {level}")
    textage_id, ocr_titles = read_textage_id(
        frame, song_reference, bpm, difficulty, level
    )
    if not textage_id:
        raise RuntimeError(
            "Could not determine specific song from song select screen metadata"
        )
    notes = sqlite_client.read_notes(textage_id, difficulty.value)
    grade = calculate_grade_from_total_score(total_score, notes)
    score = Score(
        miss_count=miss_count,
        grade=grade,
        total_score=total_score,
        clear_type=clear_type.name,
    )
    return textage_id, score, difficulty, ocr_titles
