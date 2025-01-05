#!/usr/bin/env python3

import copy
import logging
from typing import Any
from decimal import Decimal
from concurrent.futures import ProcessPoolExecutor

import cv2 as cv  # type: ignore
import pytesseract  # type: ignore
from numpy.typing import NDArray  # type: ignore

from . import sqlite_client
from .local_dataclasses import (
    Point,
    Score,
    ClearType,
    Difficulty,
    OCRSongTitles,
    GameStatePixel,
    VideoProcessingState,
    GameState,
)
from .song_reference import SongReference
from .frame_utilities import (
    get_rectanglular_subsection_from_frame,
    is_white,
    is_bright,
    is_black,
    get_numbers_from_area,
    check_pixel_color_in_frame,
    dump_to_png,
)
from . import constants as CONSTANTS

log = logging.getLogger(__name__)


def fast_slow_digit_reader(block: NDArray) -> int:
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


def score_digit_reader(block: NDArray) -> int:
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


def calculate_grade_from_total_score(total_score: int, note_count: int) -> str:
    max_score = note_count * 2
    percentage = (Decimal(total_score) / Decimal(max_score)) * Decimal(100)
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


def calculate_grade(perfect_greats: int, greats: int, note_count: int) -> str:
    score = perfect_greats * 2 + greats
    return calculate_grade_from_total_score(score, note_count)


def get_side_from_results_screen(frame: NDArray) -> Any:
    pass


def get_level(level_area: NDArray, color: tuple[int, int, int]) -> int:
    top_left = GameStatePixel(
        name="top_left", x=3, y=3, b=color[0], g=color[1], r=color[2]
    )
    missing_corner_of_four = GameStatePixel(
        name="missing_corner_of_four", x=4, y=4, b=color[0], g=color[1], r=color[2]
    )
    bottom_right = GameStatePixel(
        name="bottom_right", x=20, y=14, b=color[0], g=color[1], r=color[2]
    )
    bottom_right_digit_gap = GameStatePixel(
        name="bottom_right_digit_gap", x=14, y=12, b=color[0], g=color[1], r=color[2]
    )
    tens_center = GameStatePixel(
        name="tens_center", x=15, y=9, b=color[0], g=color[1], r=color[2]
    )
    tens_top_middle = GameStatePixel(
        name="tens_top_middle", x=15, y=3, b=color[0], g=color[1], r=color[2]
    )
    top_right_digit_gap = GameStatePixel(
        name="top_right_digit_gap", x=15, y=6, b=color[0], g=color[1], r=color[2]
    )
    bottom_left_digit_gap = GameStatePixel(
        name="bottom_left_digit_gap", x=4, y=12, b=color[0], g=color[1], r=color[2]
    )
    top_left_digit_gap = GameStatePixel(
        name="top_left_digit_gap", x=4, y=6, b=color[0], g=color[1], r=color[2]
    )
    single_digit_center = GameStatePixel(
        name="single_digit_center", x=8, y=8, b=color[0], g=color[1], r=color[2]
    )

    log.debug("CHECKING SCORE DIFFICULTY")
    if check_pixel_color_in_frame(level_area, top_left):
        log.debug("PROBABLY 2 3 5 10 11 12")
        if check_pixel_color_in_frame(level_area, bottom_right):
            log.debug("PROBABLY 10 11 12")
            if check_pixel_color_in_frame(level_area, tens_center):
                log.debug("DEFINITELY 12")
                return 12
            elif check_pixel_color_in_frame(level_area, tens_top_middle):
                log.debug("DEFINITELY 10")
                return 10
            else:
                log.debug("DEFINITELY 11")
                return 11
        else:
            log.debug("PROBABLY 2 3 5")
            if check_pixel_color_in_frame(level_area, bottom_right_digit_gap):
                log.debug("PROBABLY 3 5")
                if check_pixel_color_in_frame(level_area, top_left_digit_gap):
                    log.debug("DEFINITELY 5")
                    return 5
                else:
                    log.debug("DEFINITELY 3")
                    return 3
            else:
                log.debug("DEFINITELY 2")
                return 2
    else:
        log.debug("PROBABLY 1 4 6 7 8 9")
        if check_pixel_color_in_frame(level_area, bottom_left_digit_gap):
            log.debug("PROBABLY 4 6 8")
            if not check_pixel_color_in_frame(level_area, missing_corner_of_four):
                log.debug("DEFINITELY 4")
                return 4
            elif check_pixel_color_in_frame(level_area, top_right_digit_gap):
                log.debug("DEFINITELY 8")
                return 8
            else:
                log.debug("DEFINITELY 6")
                return 6
        else:
            log.debug("PROBABLY 1 7 9")
            if not check_pixel_color_in_frame(level_area, missing_corner_of_four):
                log.debug("PROBABLY 1 7")
                if check_pixel_color_in_frame(level_area, single_digit_center):
                    log.debug("DEFINITELY 1")
                    return 1
                else:
                    log.debug("DEFINITELY 7")
                    return 7
            else:
                log.debug("DEFINITELY 9")
                return 9
    return 0


def get_difficulty_and_level(frame: NDArray, is_double: bool) -> tuple[Difficulty, int]:
    start_x = 719
    start_y = 1037
    end_x = 919
    end_y = 1055
    difficulty_area = get_rectanglular_subsection_from_frame(
        frame, start_y, start_x, end_y, end_x
    )
    # absolute screen area
    # legg = GameStatePixel(y=1040, x=722, b=255, g=104, r=253)
    legg = GameStatePixel(y=4, x=4, b=250, g=104, r=250)
    # absolute screen area
    # another = GameStatePixel(y=1046, x=820, b=104, g=104, r=255)
    another = GameStatePixel(y=9, x=101, b=104, g=90, r=250)
    hyper = GameStatePixel(y=9, x=101, b=104, g=250, r=250)
    normal = GameStatePixel(y=9, x=101, b=250, g=250, r=104)
    level_size = Point(y=19, x=24)
    legg_level_start_pixel = Point(x=174, y=0)
    another_level_start_pixel = Point(x=149, y=0)
    hyper_level_start_pixel = Point(x=133, y=0)
    normal_level_start_pixel = Point(x=144, y=0)

    difficulty_enum_index = 1
    if is_double:
        difficulty_enum_index = 6

    if check_pixel_color_in_frame(difficulty_area, legg):
        difficulty_enum_index += 4
        color = (legg.b, legg.g, legg.r)
        level_start_pixel = legg_level_start_pixel
    elif check_pixel_color_in_frame(difficulty_area, another):
        difficulty_enum_index += 3
        color = (another.b, another.g, another.r)
        level_start_pixel = another_level_start_pixel
    elif check_pixel_color_in_frame(difficulty_area, hyper):
        difficulty_enum_index += 2
        color = (hyper.b, hyper.g, hyper.r)
        level_start_pixel = hyper_level_start_pixel
    elif check_pixel_color_in_frame(difficulty_area, normal):
        difficulty_enum_index += 1
        color = (normal.b, normal.g, normal.r)
        level_start_pixel = normal_level_start_pixel
    else:
        difficulty_enum_index = 99
        color = None
        level_start_pixel = None

    difficulty = Difficulty(difficulty_enum_index)
    if difficulty == Difficulty.UNKNOWN or level_start_pixel is None or color is None:
        raise RuntimeError("Could not read difficulty from score screen")

    level_end_y = level_start_pixel.y + level_size.y
    level_end_x = level_start_pixel.x + level_size.x
    level_area = get_rectanglular_subsection_from_frame(
        difficulty_area,
        level_start_pixel.y,
        level_start_pixel.x,
        level_end_y,
        level_end_x,
    )
    # cv.imshow("beep", level_area)
    # _ = cv.waitKey(0)
    level = get_level(level_area, color)
    return difficulty, level


def get_play_type(frame: NDArray) -> bool:
    start_x = 937
    start_y = 1037
    end_x = 986
    end_y = 1064
    play_type = get_rectanglular_subsection_from_frame(
        frame, start_y, start_x, end_y, end_x
    )
    center_d = Point(y=10, x=10)
    if is_black(play_type, center_d):
        log.debug("IS DP")
        return True
    else:
        log.debug("IS SP")
        return False


def get_clear_type_from_results_screen(frame: NDArray, left_side: bool) -> ClearType:
    start_y = 417
    end_y = 437
    if left_side:
        start_x = 366
        end_x = 512
    else:
        start_x = 1716
        end_x = 1862
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
    return get_numbers_from_area(frame, CONSTANTS.NOTES_AREA, note_count_reader)[0]


def get_score_from_result_screen(
    frame: NDArray, left_side: bool, is_double: bool
) -> Score:
    log.info("reading score...")
    if left_side:
        score_area = CONSTANTS.SCORE_P1_AREA
        fast_slow_area = CONSTANTS.FAST_SLOW_P1_AREA
    else:
        score_area = CONSTANTS.SCORE_P2_AREA
        fast_slow_area = CONSTANTS.FAST_SLOW_P2_AREA
    scores = get_numbers_from_area(frame, score_area, score_digit_reader)
    fast_slow = get_numbers_from_area(frame, fast_slow_area, fast_slow_digit_reader)
    note_count = get_note_count(frame)
    log.debug(f"SCORES: {scores}")
    log.debug(f"FAST_SLOW {fast_slow}")
    log.debug(f"NOTE COUNT {note_count}")
    if note_count is None:
        grade = "X"
    else:
        grade = calculate_grade(scores[0], scores[1], note_count)
    total_score = (scores[0] * 2) + scores[1]
    miss_count = scores[3] + scores[4]
    clear_type = get_clear_type_from_results_screen(frame, left_side)
    score_data: list[Any] = []
    score_data.extend(scores)
    score_data.extend(fast_slow)
    score_data.append(grade)
    score_data.append(clear_type.name)
    score_data.append(total_score)
    score_data.append(miss_count)
    log.debug(score_data)
    return Score(*score_data)


def note_count_reader(block: NDArray) -> int:
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


def get_title_and_artist(frame: NDArray, ocr: ProcessPoolExecutor) -> OCRSongTitles:
    top_left_y = 960
    top_left_x = 550
    bottom_right_x = 1370
    song_title_bottom_right_y = 996
    artist_bottom_right_y = 1030

    # TODO: extract this, see same code in play frame processor
    grey_r = 145
    grey_g = 145
    grey_b = 145
    for y in range(top_left_y, artist_bottom_right_y):
        for x in range(top_left_x, bottom_right_x):
            if (
                frame[y][x][0] < grey_b
                and frame[y][x][1] < grey_g
                and frame[y][x][2] < grey_r
            ):
                frame[y][x][0] = 255
                frame[y][x][1] = 255
                frame[y][x][2] = 255
            else:
                frame[y][x][0] = 0
                frame[y][x][1] = 0
                frame[y][x][2] = 0

    song_frame_slice = get_rectanglular_subsection_from_frame(
        frame, top_left_y, top_left_x, song_title_bottom_right_y, bottom_right_x
    )
    artist_frame_slice = get_rectanglular_subsection_from_frame(
        frame,
        song_title_bottom_right_y,
        top_left_x,
        artist_bottom_right_y,
        bottom_right_x,
    )
    en_title = str.strip(pytesseract.image_to_string(song_frame_slice, lang="eng"))
    jp_title = str.strip(pytesseract.image_to_string(song_frame_slice, lang="jpn"))
    en_artist = str.strip(pytesseract.image_to_string(artist_frame_slice, lang="eng"))
    jp_artist = str.strip(pytesseract.image_to_string(artist_frame_slice, lang="jpn"))
    log.debug(f"ENG SONG: '{en_artist}' '{en_title}'")
    log.debug(f"JPN SONG: '{jp_artist}' '{jp_title}'")

    if not en_title and not en_artist and not jp_title and not jp_artist:
        scaled_song = cv.resize(song_frame_slice, None, fx=4, fy=4)
        scaled_artist = cv.resize(artist_frame_slice, None, fx=4, fy=4)
        en_title = str.strip(pytesseract.image_to_string(scaled_song, lang="eng"))
        jp_title = str.strip(pytesseract.image_to_string(scaled_song, lang="jpn"))
        en_artist = str.strip(pytesseract.image_to_string(scaled_artist, lang="eng"))
        jp_artist = str.strip(pytesseract.image_to_string(scaled_artist, lang="jpn"))
        if not en_title and not en_artist and not jp_title and not jp_artist:
            raise RuntimeError("Could not read artist or title from frame")

    ocr_song_titles: OCRSongTitles = OCRSongTitles(
        en_title, en_artist, jp_title, jp_artist
    )
    return ocr_song_titles


def read_score_from_png(
    frame: NDArray, left_side: bool, is_double: bool, ocr: ProcessPoolExecutor
):
    is_double = get_play_type(frame)
    score = get_score_from_result_screen(frame, left_side, is_double)
    notes = get_note_count(frame)
    ocr_song_titles = get_title_and_artist(frame, ocr)
    difficulty, level = get_difficulty_and_level(frame, is_double)
    return score, notes, ocr_song_titles, difficulty, level


def update_video_processing_state(
    frame: NDArray,
    frame_count: int,
    v: VideoProcessingState,
    song_reference: SongReference,
) -> None:
    # total note count only exists on the score frame
    if v.note_count is None:
        v.note_count = get_note_count(frame)
    if v.left_side is not None and v.is_double is not None:
        if v.score is None:
            v.score = get_score_from_result_screen(frame, v.left_side, v.is_double)
        # only if no lookup for titles by song metadata have been determined
        if (
            v.difficulty
            and v.level
            and v.min_bpm
            and v.max_bpm
            and v.note_count
            and (v.metadata_title is None or len(v.metadata_title) > 1)
        ):
            v.metadata_title = song_reference.resolve_by_play_metadata(
                (v.difficulty.name, v.level),
                (v.min_bpm, v.max_bpm),
                v.note_count,
            )
        # if all score data is found but the frame is not saved
        if (
            v.ocr_song_title is not None
            and v.score is not None
            and v.score_frame is None
        ):
            v.score_frame = copy.deepcopy(frame)
    return


def handle_score_transition(
    frame_count: int,
    v: VideoProcessingState,
    song_reference: SongReference,
    session_uuid: str,
) -> None:
    if (
        v.ocr_song_title is None
        and v.ocr_song_future is not None
        and v.ocr_song_future.done()
    ):
        v.ocr_song_title = v.ocr_song_future.result()
        log.info("found ocr song title {v.ocr_song_title}")

    if (
        v.score is not None
        and v.score_frame is not None
        and v.ocr_song_title is not None
        and v.difficulty is not None
        and v.level is not None
        and v.metadata_title is not None
    ):
        log.info(f"frame#{frame_count}:writing score")
        tiebreak_data = sqlite_client.read_tiebreak_data(v.metadata_title)
        textage_id = song_reference.resolve_ocr_and_metadata(
            v.ocr_song_title,
            v.metadata_title,
            tiebreak_data,
            v.difficulty.name,
            v.level,
        )
        if textage_id:
            sqlite_client.write_score(
                session_uuid,
                textage_id,
                v.score,
                v.difficulty,
                v.ocr_song_title,
                v.score_frame,
            )
        else:
            bug_file = dump_to_png(v.score_frame, "BAD_SCORE_FRAME", 0)
            log.error(
                "Could not determine specific song title from score result frame metadata."
                f"Dumping frame to {bug_file} for bug reporting purposes."
            )
    return


def read_score_and_song_metadata(
    frame: NDArray,
    song_reference: SongReference,
    game_state: GameState,
    ocr: ProcessPoolExecutor,
):
    left_side = True
    play_side, _ = game_state.value.split("_")
    if play_side == "P2":
        left_side = False
    is_double = get_play_type(frame)
    # TODO: have this run the ocr on the screen frame
    score, notes, ocr_titles, difficulty, level = read_score_from_png(
        frame, left_side, is_double, ocr
    )
    log.debug(f"returned score: {score}")
    log.debug(f"returned notes: {notes}")
    log.debug(f"returned title: {ocr_titles}")
    log.debug(f"returned diff : {difficulty}")
    log.debug(f"returned level: {level}")
    metadata_titles = song_reference.resolve_by_score_metadata(
        difficulty.name, level, notes
    )
    # TODO: construct tiebreak data in songreference on initialization
    tiebreak_data = sqlite_client.read_tiebreak_data(metadata_titles)
    # TODO: have resolve take the enum
    textage_id = song_reference.resolve_ocr_and_metadata(
        ocr_titles, metadata_titles, tiebreak_data, difficulty.name, level
    )
    return textage_id, score, difficulty, ocr_titles
