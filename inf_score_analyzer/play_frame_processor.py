#!/usr/bin/env python3
import logging
from typing import Tuple
from concurrent.futures import ProcessPoolExecutor

import pytesseract  # type: ignore
from numpy.typing import NDArray

from .frame_utilities import (
    get_rectanglular_subsection_from_frame,
    is_white,
    read_pixel,
    dump_to_png,
    get_numbers_from_area,
    read_from_png,
)
from . import constants as CONSTANTS
from .local_dataclasses import (
    Point,
    OCRSongTitles,
    VideoProcessingState,
    PlayMetadata,
    SongReference,
)

log = logging.getLogger(__name__)


# TODO: future work
# def __write_debug_files(frame: NDArray, frame_count: int, percentage: int) -> None:
#    percentage_area = __cut_lifebar_percentage(frame)
#    png_filename = f"data/percentages/percentage_{frame_count:06d}.png"
#    txt_filename = f"data/percentages/percentage_{frame_count:06d}.txt"
#    cv.imwrite(png_filename, percentage_area)
#    with open(txt_filename, "wt") as writer:
#        writer.write(f"{percentage}\n")
#    return
#
# def __cut_lifebar_percentage(frame: NDArray) -> NDArray:
#    top_left_y = 572
#    top_left_x = 235
#    bottom_right_y = 590
#    bottom_right_x = 296
#    frame_slice = get_rectanglular_subsection_from_frame(
#        frame, top_left_y, top_left_x, bottom_right_y, bottom_right_x
#    )
#    return frame_slice
#


def percentage_tens_reader(block: NDArray) -> int:
    bottom_left_corner = Point(y=21, x=5)
    bottom_left_gap = Point(y=17, x=5)
    top_left_gap = Point(y=8, x=5)
    center_upper = Point(y=12, x=18)
    center_lower = Point(y=14, x=18)
    top_right_corner = Point(y=4, x=31)
    top_middle = Point(y=4, x=18)
    if is_white(block, bottom_left_corner):
        log.debug("PROBABLY 023568")
        if is_white(block, bottom_left_gap):
            log.debug("PROBABLY 0268")
            if is_white(block, center_upper):
                log.debug("PROBABLY 268")
                if not is_white(block, top_right_corner):
                    log.debug("DEFINITELY 6")
                    return 6
                elif is_white(block, top_left_gap):
                    log.debug("DEFINITELY 8")
                    return 8
                else:
                    log.debug("DEFINITELY 2")
                    return 2
            else:
                log.debug("DEFINITELY 0")
                return 0
        else:
            log.debug("PROBABLY 35")
            if is_white(block, top_left_gap):
                log.debug("DEFINITELY 5")
                return 5
            else:
                log.debug("DEFINITELY 3")
                return 3
    else:
        log.debug("PROBABLY 1479")
        if is_white(block, top_middle):
            log.debug("PROBABLY 179")
            if not is_white(block, top_left_gap):
                log.debug("DEFINITELY 1")
                return 1
            elif is_white(block, center_lower):
                log.debug("DEFINITELY 9")
                return 9
            else:
                log.debug("DEFINITELY 7")
                return 7
        else:
            log.debug("DEFINITELY 4")
            return 4
    return 0


def percentage_hundreds_reader(block: NDArray) -> int:
    top_one = Point(y=3, x=4)
    if is_white(block, top_one):
        log.debug("MUST BE 1")
        return 1
    log.debug("MUST BE 0")
    return 0


def read_lifebar_percentage(frame_count: int, frame: NDArray) -> int:
    # TODO: add 2p and doubles and alternative layouts
    hundreds_area = CONSTANTS.PERCENTAGE_HUNDREDS_SP_1P
    tens_area = CONSTANTS.PERCENTAGE_TENS_SP_1P
    hundred = get_numbers_from_area(frame, hundreds_area, percentage_hundreds_reader)[0]
    tens = get_numbers_from_area(frame, tens_area, percentage_tens_reader)[0]
    percent_value: int = tens + (hundred * 100)
    log.debug(f"PERCENT VALUE: {percent_value}")
    return percent_value


def get_ocr_song_title_from_play_frame(
    frame: NDArray, left_side: bool, is_double: bool
) -> OCRSongTitles:
    # TODO: implement
    #    if not is_double:
    #        top_left_y = 36
    #        top_left_x = 350
    #        song_title_bottom_right_y = 63
    #        artist_bottom_right_y = 90
    #        bottom_right_x = 1000
    #    elif left_side:
    #        top_left_y = 30
    #        top_left_x = 0
    #        song_title_bottom_right_y = 62
    #        artist_bottom_right_y = 87
    #        bottom_right_x = 260
    #    else:
    #        top_left_y = 30
    #        top_left_x = 1020
    #        bottom_right_x = 1279
    #        song_title_bottom_right_y = 62
    #        artist_bottom_right_y = 87
    if left_side and not is_double:
        top_left_y = 60
        top_left_x = 734
        bottom_right_x = 1500
        song_title_bottom_right_y = 96
        artist_bottom_right_y = 120
    else:
        raise RuntimeError("2p and dp not yet supported")
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
    # TODO: wrap in debug
    # dump_to_png(song_frame_slice, "SONG_TITLE", 0)
    # dump_to_png(artist_frame_slice, "SONG_ARTIST", 0)
    en_song = str.strip(pytesseract.image_to_string(song_frame_slice, lang="eng"))
    jp_song = str.strip(pytesseract.image_to_string(song_frame_slice, lang="jpn"))
    en_artist = str.strip(pytesseract.image_to_string(artist_frame_slice, lang="eng"))
    jp_artist = str.strip(pytesseract.image_to_string(artist_frame_slice, lang="jpn"))
    log.info(f"ENG SONG: {en_artist} {en_song} ")
    log.info(f"JPN SONG: {jp_artist} {jp_song}")
    return OCRSongTitles(
        en_title=en_song, en_artist=en_artist, jp_title=jp_song, jp_artist=jp_artist
    )


def play_level_digit_reader(block: NDArray) -> int:
    left_most_column = Point(x=4, y=5)
    bottom_right_gap = Point(x=25, y=12)
    bottom_left_gap = Point(x=6, y=12)
    top_right_gap = Point(x=25, y=6)
    top_center_gap = Point(x=16, y=4)
    second_digit_middle = Point(x=20, y=8)
    bottom_left_corner = Point(x=6, y=15)
    if is_white(block, left_most_column):
        log.debug("MIGHT BE 6 9 10 11 12")
        if is_white(block, bottom_right_gap):
            if not is_white(block, bottom_left_gap):
                log.debug("DEFINITELY 9")
                return 9
            elif is_white(block, top_right_gap):
                log.debug("DEFINITELY 11")
                return 11
            else:
                log.debug("DEFINITELY 6")
                return 6
        else:
            log.debug("MIGHT BE 10 12")
            if is_white(block, second_digit_middle):
                log.debug("DEFINITELY 12")
                return 12
            else:
                log.debug("DEFINITELY 10")
                return 10
    elif is_white(block, bottom_right_gap):
        log.debug("MIGHT BE 3 4 5 8")
        if is_white(block, bottom_left_corner):
            log.debug("MIGHT BE 3 5")
            if is_white(block, top_right_gap):
                log.debug("DEFINITELY 3")
                return 3
            else:
                log.debug("DEFINITELY 5")
                return 5
        else:
            log.debug("MIGHT BE 4 8")
            if is_white(block, top_center_gap):
                log.debug("DEFINITELY 4")
                return 4
            else:
                log.debug("DEFINITELY 8")
                return 8
    else:
        if is_white(block, top_center_gap):
            log.debug("DEFINITELY 1")
            return 1
        elif is_white(block, bottom_left_corner):
            log.debug("DEFINITELY 2")
            return 2
        else:
            log.debug("DEFINITELY 7")
            return 7


def read_play_level(frame: NDArray, left_side: bool, is_double: bool) -> int:
    if is_double:
        raise RuntimeError("double not yet supported")
    elif left_side:
        level_area = CONSTANTS.LEVEL_SP_P1
    else:
        level_area = CONSTANTS.LEVEL_SP_P2
    return get_numbers_from_area(frame, level_area, play_level_digit_reader)[0]


def read_side_and_doubles(play_frame: NDArray) -> Tuple[bool, bool]:
    # TODO: implement
    return True, False


def read_play_difficulty(frame: NDArray, left_side: bool, is_double) -> str:
    single_or_double = "SP"
    if is_double:
        raise RuntimeError("double not yet supported")
    if left_side:
        difficulty_point = Point(x=580, y=75)
    else:
        difficulty_point = Point(x=1208, y=75)
    color = read_pixel(frame, difficulty_point)
    # normal = [215, 132, 0]
    # hyper = [0, 157, 215]
    # another = [0, 0, 215]
    # leggendaria = [215, 0, 163]
    known_difficulty = "UNKNOWN"
    if color[0] < 10:
        if color[1] >= 128:
            known_difficulty = "HYPER"
        else:
            known_difficulty = "ANOTHER"
    else:
        if color[1] >= 128:
            known_difficulty = "NORMAL"
        else:
            known_difficulty = "LEGGENDARIA"
    log.debug(f"difficulty color {color}")
    log.debug(f"difficulty {known_difficulty}")
    return f"{single_or_double}_{known_difficulty}"


def read_play_lifebar_type(
    play_frame: NDArray, left_side: bool, is_double: bool
) -> str:
    # TODO: implement
    if CONSTANTS.DEV_MODE:
        dump_to_png(play_frame, "play_lifebar", 1100)
    return "UNKNOWN"


def current_bpm_digit_reader(block: NDArray) -> int:
    center_line_middle = Point(x=15, y=10)
    center_line_top = Point(x=15, y=8)
    center_line_bottom = Point(x=15, y=12)
    top_left_gap = Point(x=4, y=5)
    top_line_middle = Point(x=15, y=1)
    top_right_gap = Point(x=28, y=5)
    bottom_right_gap = Point(x=28, y=15)
    bottom_left_gap = Point(x=4, y=15)
    if is_white(block, center_line_middle):
        log.debug("MIGHT BE 1238")
        if not is_white(block, top_right_gap):
            log.debug("DEFINITELY 1")
            return 1
        else:
            log.debug("MIGHT BE 238")
            if not is_white(block, bottom_right_gap):
                log.debug("DEFINITELY 2")
                return 2
            elif is_white(block, top_left_gap):
                log.debug("DEFINITELY 8")
                return 8
            else:
                log.debug("DEFINITELY 3")
                return 3
    else:
        log.debug("MIGHT BE _045679")
        if is_white(block, top_right_gap):
            log.debug("MIGHT BE 0479")
            if is_white(block, center_line_bottom):
                log.debug("MIGHT BE 49")
                if is_white(block, top_line_middle):
                    log.debug("DEFINITELY 9")
                    return 9
                else:
                    log.debug("DEFINITELY 4")
                    return 4
            else:
                log.debug("MIGHT BE 07")
                if is_white(block, bottom_left_gap):
                    log.debug("DEFINITELY 0")
                    return 0
                else:
                    log.debug("DEFINITELY 7")
                    return 7
        else:
            log.debug("MIGHT BE _56")
            if not is_white(block, center_line_top):
                log.debug("DEFINITELY ' '")
                return 0
            elif is_white(block, bottom_left_gap):
                log.debug("DEFINITELY 6")
                return 6
            else:
                log.debug("DEFINITELY 5")
                return 5


def min_max_bpm_digit_reader(block: NDArray) -> int:
    center_line_top = Point(x=12, y=6)
    center_line_bottom = Point(x=12, y=8)
    top_left_gap = Point(x=2, y=3)
    top_right_gap = Point(x=19, y=3)
    bottom_right_gap = Point(x=19, y=9)
    bottom_left_gap = Point(x=2, y=9)
    bottom_line_center = Point(y=13, x=6)
    if is_white(block, center_line_top):
        log.debug("MIGHT BE 123568")
        if is_white(block, top_left_gap):
            log.debug("MIGHT BE 568")
            if is_white(block, top_right_gap):
                log.debug("DEFINITELY 8")
                return 8
            elif is_white(block, bottom_left_gap):
                log.debug("DEFINITELY 6")
                return 6
            else:
                log.debug("DEFINITELY 5")
                return 5
        else:
            log.debug("MIGHT BE 123")
            if not is_white(block, top_right_gap):
                log.debug("DEFINITELY 1")
                return 1
            elif is_white(block, bottom_right_gap):
                log.debug("DEFINITELY 3")
                return 3
            else:
                log.debug("DEFINITELY 2")
                return 2
    else:
        log.debug("MIGHT BE _0479")
        if not is_white(block, bottom_right_gap):
            log.debug("DEFINITELY ' '")
            return 0
        elif is_white(block, bottom_line_center):
            log.debug("MIGHT BE 09")
            if is_white(block, center_line_bottom):
                log.debug("DEFINITELY 9")
                return 9
            else:
                log.debug("DEFINITELY 0")
                return 0
        else:
            log.debug("MIGHT BE 47")
            if is_white(block, center_line_bottom):
                log.debug("DEFINITELY 4")
                return 4
            else:
                log.debug("DEFINITELY 7")
                return 7


def read_bpm(frame: NDArray, left_side: bool, is_double: bool) -> Tuple[int, int]:
    if is_double:
        raise RuntimeError("doubles is not yet implemented")
    elif left_side:
        cur_bpm_area = CONSTANTS.BPM_P1_AREA
        min_bpm_area = CONSTANTS.MIN_BPM_P1_AREA
        max_bpm_area = CONSTANTS.MAX_BPM_P1_AREA
    else:
        cur_bpm_area = CONSTANTS.BPM_P2_AREA
        min_bpm_area = CONSTANTS.MIN_BPM_P2_AREA
        max_bpm_area = CONSTANTS.MAX_BPM_P2_AREA
    cur_bpm = 0
    min_bpm = 0
    max_bpm = 0
    cur_bpm = get_numbers_from_area(frame, cur_bpm_area, current_bpm_digit_reader)[0]
    min_bpm = get_numbers_from_area(frame, min_bpm_area, min_max_bpm_digit_reader)[0]
    max_bpm = get_numbers_from_area(frame, max_bpm_area, min_max_bpm_digit_reader)[0]
    if not min_bpm and not max_bpm:
        min_bpm = cur_bpm
        max_bpm = cur_bpm
    log.debug(f"cur bpm: {cur_bpm}")
    return min_bpm, max_bpm


def play_judge_digit_reader(block: NDArray) -> int:
    upper_left_edge = Point(x=3, y=4)
    lower_left_edge = Point(x=3, y=8)
    right_edge = Point(x=11, y=4)
    center_center = Point(x=7, y=6)
    top_center = Point(x=7, y=1)
    if is_white(block, upper_left_edge):
        log.debug("MIGHT BE 56890")
        if is_white(block, right_edge):
            log.debug("MIGHT BE 089")
            if is_white(block, lower_left_edge):
                log.debug("MIGHT BE 08")
                if is_white(block, center_center):
                    log.debug("DEFINITELY 8")
                    return 8
                else:
                    log.debug("DEFINITELY 0")
                    return 0
            else:
                log.debug("DEFINITELY 9")
                return 9
        else:
            log.debug("MIGHT BE 56")
            if is_white(block, lower_left_edge):
                log.debug("DEFINITELY 6")
                return 6
            else:
                log.debug("DEFINITELY 5")
                return 5
    else:
        log.debug("MIGHT BE 12347_")
        if is_white(block, right_edge):
            log.debug("MIGHT BE 234")
            if is_white(block, center_center):
                log.debug("MIGHT BE 23")
                if is_white(block, lower_left_edge):
                    log.debug("DEFINITELY 2")
                    return 2
                else:
                    log.debug("DEFINITELY 3")
                    return 3
            else:
                log.debug("DEFINITELY 4")
                return 4
        else:
            log.debug("MIGHT BE 17_")
            if is_white(block, center_center):
                log.debug("DEFINITELY 1")
                return 1
            else:
                log.debug("MIGHT BE 7_")
                if is_white(block, top_center):
                    log.debug("DEFINITELY 7")
                    return 7
                else:
                    log.debug("DEFINITELY _")
                    return 0


def read_play_judge_accuracy_area(
    play_frame_count: int, play_frame: NDArray
) -> list[int]:
    # TODO: add 2p and doubles and alt arrangements
    play_judge_accuracy_area = CONSTANTS.PLAY_JUDGE_SP_P1
    play_judge_fast_area = CONSTANTS.PLAY_JUDGE_FAST_SP_P1
    play_judge_slow_area = CONSTANTS.PLAY_JUDGE_SLOW_SP_P1
    # [fg, gr, g, b, p, cb, fast, slow]
    score_and_accuracy: list[int] = []
    score_and_accuracy.extend(
        get_numbers_from_area(
            play_frame, play_judge_accuracy_area, play_judge_digit_reader
        )
    )
    score_and_accuracy.extend(
        get_numbers_from_area(play_frame, play_judge_fast_area, play_judge_digit_reader)
    )
    score_and_accuracy.extend(
        get_numbers_from_area(play_frame, play_judge_slow_area, play_judge_digit_reader)
    )
    return score_and_accuracy


def read_play_metadata(
    play_frame_count: int,
    play_frame: NDArray,
    video_processing_state: VideoProcessingState,
) -> PlayMetadata:
    if (
        video_processing_state.left_side is None
        or video_processing_state.is_double is None
    ):
        left_side, is_double = read_side_and_doubles(play_frame)
    else:
        left_side = video_processing_state.left_side
        is_double = video_processing_state.is_double
    if video_processing_state.difficulty is None:
        difficulty = read_play_difficulty(play_frame, left_side, is_double)
    else:
        difficulty = video_processing_state.difficulty
    if video_processing_state.level is None:
        level = read_play_level(play_frame, left_side, is_double)
    else:
        level = video_processing_state.level
    if video_processing_state.lifebar_type is None:
        lifebar_type = read_play_lifebar_type(play_frame, left_side, is_double)
    else:
        lifebar_type = video_processing_state.lifebar_type
    if video_processing_state.min_bpm is None or video_processing_state.max_bpm is None:
        min_bpm, max_bpm = read_bpm(play_frame, left_side, is_double)
    else:
        min_bpm = video_processing_state.min_bpm
        max_bpm = video_processing_state.max_bpm
    return PlayMetadata(
        difficulty, level, lifebar_type, min_bpm, max_bpm, left_side, is_double
    )


def update_video_processing_state(
    frame: NDArray,
    frame_count: int,
    v: VideoProcessingState,
    song_reference: SongReference,
    ocr: ProcessPoolExecutor,
) -> None:
    if v.play_metadata_missing():
        play_metadata = read_play_metadata(frame_count, frame, v)
        v.update_play_metadata(play_metadata)

    # song metadata is all set except title
    if (
        v.metadata_title is None
        and v.difficulty is not None
        and v.level is not None
        and v.min_bpm is not None
        and v.max_bpm is not None
    ):
        v.metadata_title = song_reference.resolve_by_play_metadata(
            (v.difficulty, v.level),
            (v.min_bpm, v.max_bpm),  # type: ignore
        )
    # know layout but not song title ocr data
    if v.ocr_song_title is None and v.left_side is not None and v.is_double is not None:
        if v.ocr_song_future is None:
            log.info(f"{v.current_state.name} frame#{frame_count} ocr call")
            v.ocr_song_future = ocr.submit(
                get_ocr_song_title_from_play_frame,
                frame,
                v.left_side,
                v.is_double,
            )
            log.info(f"{v.current_state.name} frame#{frame_count} ocr future created")
        elif v.ocr_song_future.done():
            v.ocr_song_title = v.ocr_song_future.result()
            log.info("found ocr song title {v.ocr_song_title}")
    return


if __name__ == "__main__":
    import sys
    from pathlib import Path

    # logging.basicConfig(level=logging.DEBUG)
    frame = read_from_png(Path(sys.argv[1]))
    score_and_accuracy = read_play_judge_accuracy_area(-1, frame)
    lifebar_percentage = read_lifebar_percentage(-1, frame)
    score_and_accuracy.append(lifebar_percentage)
    print(score_and_accuracy)
