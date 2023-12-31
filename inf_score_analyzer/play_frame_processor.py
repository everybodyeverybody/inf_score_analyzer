#!/usr/bin/env python3
import logging
from typing import Tuple
import pytesseract  # type: ignore
from numpy.typing import NDArray
from .frame_utilities import (
    get_rectanglular_subsection_from_frame,
    get_array_as_ascii_art,
    is_white,
    is_black,
    read_pixel,
    dump_to_png,
)
from .local_dataclasses import Point, OCRSongTitles, VideoProcessingState
from . import constants as CONSTANTS

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


def lifebar_digit_reader(block: NDArray) -> str:
    log.debug("\n" + get_array_as_ascii_art(block))
    top_mid = Point(y=1, x=12)
    mid_top = Point(y=7, x=12)
    mid1 = Point(y=8, x=12)
    mid_left = Point(y=9, x=2)
    mid2 = Point(y=9, x=12)
    bottom_left = Point(y=15, x=2)
    top_right = Point(y=2, x=21)
    if is_white(read_pixel(block, mid1)):
        log.debug("MIGHT BE 123568")
        if is_white(read_pixel(block, mid_top)):
            log.debug("MIGHT BE 1568")
            if is_white(read_pixel(block, top_right)):
                log.debug("MIGHT BE 58")
                if is_white(read_pixel(block, mid_left)):
                    log.debug("DEFINITELY 8")
                    return "8"
                else:
                    log.debug("DEFINITELY 5")
                    return "5"
            elif is_white(read_pixel(block, mid_left)):
                log.debug("DEFINITELY 6")
                return "6"
            else:
                log.debug("DEFINITELY 1")
                return "1"
        else:
            log.debug("MIGHT BE 23")
            if is_white(read_pixel(block, mid_left)):
                log.debug("DEFINITELY 2")
                return "2"
            else:
                log.debug("DEFINITELY 3")
                return "3"
    else:
        log.debug("MIGHT BE 0479_")
        if is_white(read_pixel(block, mid2)):
            log.debug("MIGHT BE 49")
            if is_white(read_pixel(block, top_mid)):
                log.debug("DEFINITELY 9")
                return "9"
            else:
                log.debug("DEFINITELY 9")
                return "4"
        else:
            log.debug("MIGHT BE 07_")
            if is_white(read_pixel(block, bottom_left)):
                log.debug("DEFINITELY 0")
                return "0"
            elif is_white(read_pixel(block, top_mid)):
                log.debug("DEFINITELY 7")
                return "7"
            else:
                log.debug("DEFINITELY _")
                return " "


def get_percentage_from_percentage_area(
    frame: NDArray, origin: Point, x_offset: int, y_offset: int
) -> int:
    hundreds = Point(y=580, x=240)
    hundreds_color = read_pixel(frame, hundreds)
    if (
        hundreds_color[0] >= CONSTANTS.QUANTIZED_WHITE_MAX
        and hundreds_color[1] >= CONSTANTS.QUANTIZED_WHITE_MAX
        and hundreds_color[2] >= CONSTANTS.QUANTIZED_WHITE_MAX
    ):
        return 100
    places_count = 2
    digits = []
    for place in range(0, places_count):
        column_offset = place * x_offset
        top_left_with_offset = origin.x + column_offset
        bottom_right_with_offset = top_left_with_offset + x_offset
        top_left = Point(y=origin.y, x=top_left_with_offset)
        bottom_right = Point(y=origin.y + y_offset, x=bottom_right_with_offset)
        log.debug(f"TOP LEFT {top_left} BOTTOM_RIGHT {bottom_right}")
        digit_block = get_rectanglular_subsection_from_frame(
            frame, top_left.y, top_left.x, bottom_right.y, bottom_right.x
        )
        digits.append(lifebar_digit_reader(digit_block))
    log.debug(f"PERC {digits}")
    percentage_string = "".join(digits).strip()
    if percentage_string == "":
        return 0
    return int(percentage_string)


def get_percentage_area_origin(left_side: bool, is_double: bool) -> Point:
    if left_side and not is_double:
        return Point(y=572, x=246)
    else:
        # TODO: future work
        raise RuntimeError("2p is not implemented")


def get_lifebar_percentage(frame: NDArray, left_side: bool, is_double: bool) -> int:
    percentage_area_origin = get_percentage_area_origin(left_side, is_double)
    return get_percentage_from_percentage_area(
        frame,
        percentage_area_origin,
        CONSTANTS.PERCENTAGE_DIGIT_X_OFFSET,
        CONSTANTS.PERCENTAGE_DIGIT_Y_OFFSET,
    )


def get_ocr_song_title_from_play_frame(
    frame: NDArray, left_side: bool, is_double: bool
) -> OCRSongTitles:
    if not is_double:
        top_left_y = 36
        top_left_x = 350
        song_title_bottom_right_y = 63
        artist_bottom_right_y = 90
        bottom_right_x = 1000
    elif left_side:
        top_left_y = 30
        top_left_x = 0
        song_title_bottom_right_y = 62
        artist_bottom_right_y = 87
        bottom_right_x = 260
    else:
        top_left_y = 30
        top_left_x = 1020
        bottom_right_x = 1279
        song_title_bottom_right_y = 62
        artist_bottom_right_y = 87
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
    en_song = str.strip(pytesseract.image_to_string(song_frame_slice, lang="eng"))
    jp_song = str.strip(pytesseract.image_to_string(song_frame_slice, lang="jpn"))
    en_artist = str.strip(pytesseract.image_to_string(artist_frame_slice, lang="eng"))
    jp_artist = str.strip(pytesseract.image_to_string(artist_frame_slice, lang="jpn"))
    log.info(f"ENG SONG: {en_artist} {en_song} ")
    log.info(f"JPN SONG: {jp_artist} {jp_song}")
    return OCRSongTitles(
        en_title=en_song, en_artist=en_artist, jp_title=jp_song, jp_artist=jp_artist
    )


def read_play_level(play_frame: NDArray, left_side: bool, is_double: bool) -> int:
    if left_side and not is_double:
        origin = Point(y=107, x=425)
    elif not left_side and not is_double:
        origin = Point(y=107, x=867)
    elif left_side and is_double:
        origin = Point(y=110, x=80)
    elif not left_side and is_double:
        origin = Point(y=110, x=1099)
    at_least_ten = Point(y=origin.y + 5, x=origin.x + 3)
    top_left_1 = Point(y=origin.y + 2, x=origin.x + 7)
    top_left_2 = Point(y=origin.y + 3, x=origin.x + 7)
    top_right = Point(y=origin.y + 3, x=origin.x + 20)
    bottom_left = Point(y=origin.y + 7, x=origin.x + 7)
    bottom_right = Point(y=origin.y + 8, x=origin.x + 20)
    if is_white(read_pixel(play_frame, at_least_ten)):
        log.debug("prob 10 11 12")
        if not is_white(read_pixel(play_frame, bottom_left)):
            log.debug("prob 11 12")
            if is_white(read_pixel(play_frame, bottom_right)):
                log.debug("def 11")
                return 11
            else:
                log.debug("def 12")
                return 12
        else:
            log.debug("definitely 10")
            return 10
    elif is_white(read_pixel(play_frame, top_left_2)):
        log.debug("prob 5 6 8 9")
        if is_white(read_pixel(play_frame, top_right)):
            log.debug("prob 8 9")
            if is_white(read_pixel(play_frame, bottom_left)):
                log.debug("def 8")
                return 8
            else:
                log.debug("def 9")
                return 9
        else:
            log.debug("prob 5 6")
            if is_white(read_pixel(play_frame, bottom_left)):
                log.debug("def 6")
                return 6
            else:
                log.debug("def 5")
                return 5
    else:
        log.debug("prob 1 2 3 4 7")
        if is_white(read_pixel(play_frame, top_left_1)):
            log.debug("prob 2 3 7")
            if is_white(read_pixel(play_frame, bottom_left)):
                log.debug("def 2")
                return 2
            elif is_white(read_pixel(play_frame, bottom_right)):
                log.debug("def 3")
                return 3
            else:
                log.debug("def 7")
                return 7
        else:
            log.debug("prob 1 4")
            if is_white(read_pixel(play_frame, top_right)):
                log.debug("def 4")
                return 4
            else:
                log.debug("def 1")
                return 1


def read_side_and_doubles(play_frame: NDArray) -> Tuple[bool, bool]:
    sp_left_play_point = Point(x=15, y=5)
    sp_right_play_point = Point(x=1265, y=5)
    dp_left_play_point = Point(x=270, y=60)
    dp_right_play_point = Point(x=1010, y=60)
    sp_left_color = read_pixel(play_frame, sp_left_play_point)
    sp_right_color = read_pixel(play_frame, sp_right_play_point)
    dp_left_color = read_pixel(play_frame, dp_left_play_point)
    dp_right_color = read_pixel(play_frame, dp_right_play_point)
    left_side = True
    is_double = False
    if (
        sp_left_color[2] <= 30
        and sp_left_color[1] >= 150
        and sp_left_color[1] <= 165
        and sp_left_color[0] >= 230
    ):
        left_side = True
        is_double = False
    elif (
        sp_right_color[2] <= 30
        and sp_right_color[1] >= 150
        and sp_right_color[1] <= 165
        and sp_right_color[0] >= 230
    ):
        left_side = False
        is_double = False
    elif (
        dp_left_color[2] <= 30
        and dp_left_color[1] >= 150
        and dp_left_color[1] <= 165
        and dp_left_color[0] >= 230
    ):
        left_side = True
        is_double = True
    elif (
        dp_right_color[2] <= 30
        and dp_right_color[1] >= 150
        and dp_right_color[1] <= 165
        and dp_right_color[0] >= 230
    ):
        left_side = False
        is_double = True
    else:
        dump_to_png(play_frame, "doubles", 1)
        log.error(f"sp left color: {sp_left_color}")
        log.error(f"sp right color: {sp_right_color}")
        log.error(f"dp left color: {dp_left_color}")
        log.error(f"dp right color: {dp_right_color}")
        raise RuntimeError("Could not read single doubles")
    return left_side, is_double


def read_play_difficulty(play_frame: NDArray, left_side: bool, is_double: bool) -> str:
    single_or_double = "SP"
    if is_double:
        single_or_double = "DP"
    difficulty_point = Point(x=375, y=90)
    if left_side and not is_double:
        # SP 1P
        difficulty_point = Point(x=375, y=90)
    elif not left_side and not is_double:
        # SP 2P
        difficulty_point = Point(x=817, y=90)
    elif left_side and is_double:
        # DP 1P
        difficulty_point = Point(x=30, y=91)
    elif not left_side and is_double:
        # DP 2P
        difficulty_point = Point(x=1048, y=91)
    color = read_pixel(play_frame, difficulty_point)
    difficulty = "UNKNOWN"
    if (
        (color[0] >= 200 and color[0] <= 210)
        and color[1] <= 10
        and (color[2] >= 145 and color[2] <= 155)
    ):
        difficulty = "LEGGENDARIA"
    elif (
        (color[0] >= 0 and color[0] <= 20)
        and color[1] <= 10
        and (color[2] >= 195 and color[2] <= 215)
    ):
        difficulty = "ANOTHER"
    elif (
        (color[0] >= 0 and color[0] <= 20)
        and (color[1] >= 155 and color[1] <= 165)
        and (color[2] >= 205 and color[2] <= 220)
    ):
        difficulty = "HYPER"
    elif (
        (color[0] >= 205 and color[0] <= 215)
        and (color[1] >= 130 and color[1] <= 140)
        and (color[2] >= 0 and color[2] <= 20)
    ):
        difficulty = "NORMAL"
    elif (
        (color[0] >= 0 and color[0] <= 20)
        and (color[1] >= 235 and color[1] <= 245)
        and (color[2] >= 110 and color[2] <= 120)
    ):
        difficulty = "BEGINNER"
    if difficulty == "UNKNOWN":
        if CONSTANTS.DEV_MODE:
            dump_to_png(play_frame, "play_difficulty", 112)
        return difficulty
    else:
        return f"{single_or_double}_{difficulty}"


def read_play_lifebar_type(
    play_frame: NDArray, left_side: bool, is_double: bool
) -> str:
    if CONSTANTS.DEV_MODE:
        dump_to_png(play_frame, "play_lifebar", 1100)
    if left_side and not is_double:
        lifebar_point = Point(y=600, x=28)
    if not left_side and not is_double:
        lifebar_point = Point(y=600, x=1251)
    if left_side and is_double:
        lifebar_point = Point(y=586, x=492)
    if not left_side and is_double:
        lifebar_point = Point(y=586, x=786)
    lifebar_color = play_frame[lifebar_point.y][lifebar_point.x]
    if lifebar_color[0] >= 180 and lifebar_color[0] <= 220:
        return "NORMAL"
    elif lifebar_color[1] <= 30 and lifebar_color[2] >= 130:
        return "HARD"
    elif lifebar_color[1] >= 95 and lifebar_color[2] >= 170:
        return "EXHARD"
    else:
        log.warning(f"LIFEBAR COLOR: {lifebar_color}")
        return "UNKNOWN"


def min_max_bpm_digit_reader(block: NDArray) -> int:
    log.debug("\n" + get_array_as_ascii_art(block, use_black=True))
    lower_right = Point(y=9, x=14)
    lower_left = Point(y=9, x=2)
    lower_left_floor = Point(y=12, x=4)
    mid_low = Point(y=7, x=8)
    top_right = Point(y=3, x=14)
    mid_left = Point(y=6, x=2)
    top_empty_area = Point(y=3, x=8)
    if not is_black(read_pixel(block, lower_left)):
        log.debug("MIGHT BE 2680")
        if is_black(read_pixel(block, mid_low)):
            log.debug("MIGHT BE 60")
            if is_black(read_pixel(block, top_right)):
                log.debug("DEFINITELY 6")
                return 6
            else:
                log.debug("DEFINITELY 0")
                return 0
        else:
            log.debug("MIGHT BE 28")
            if is_black(read_pixel(block, lower_right)):
                log.debug("DEFINITELY 2")
                return 2
            else:
                log.debug("DEFINITELY 8")
                return 8
    else:
        log.debug("MIGHT BE 134579_")
        if is_black(read_pixel(block, mid_left)):
            log.debug("MIGHT BE 137_")
            if not is_black(read_pixel(block, top_empty_area)):
                log.debug("DEFINITELY 1")
                return 1
            elif is_black(read_pixel(block, lower_left_floor)):
                log.debug("MIGHT BE 7_")
                if is_black(read_pixel(block, top_right)):
                    log.debug("DEFINITELY _")
                    return 0
                else:
                    log.debug("DEFINITELY 7")
                    return 7
            else:
                log.debug("DEFINITELY 3")
                return 3
        else:
            log.debug("MIGHT BE 459")
            if is_black(read_pixel(block, top_right)):
                log.debug("DEFINITELY 5")
                return 5
            elif is_black(read_pixel(block, lower_left_floor)):
                log.debug("DEFINITELY 4")
                return 4
            else:
                log.debug("DEFINITELY 9")
                return 9


def read_min_bpm_area(
    frame: NDArray, place_index: int, left_side: bool, is_double: bool
) -> int:
    if is_double:
        min_bpm_area_x_origin = CONSTANTS.MIN_BPM_DP_AREA_X_ORIGIN
        min_bpm_area_y_origin = CONSTANTS.MIN_BPM_DP_AREA_Y_ORIGIN
    elif left_side:
        min_bpm_area_x_origin = CONSTANTS.MIN_BPM_SP_1P_AREA_X_ORIGIN
        min_bpm_area_y_origin = CONSTANTS.MIN_BPM_SP_1P_AREA_Y_ORIGIN
    else:
        min_bpm_area_x_origin = CONSTANTS.MIN_BPM_SP_2P_AREA_X_ORIGIN
        min_bpm_area_y_origin = CONSTANTS.MIN_BPM_SP_2P_AREA_Y_ORIGIN
    column_offset = place_index * CONSTANTS.MIN_MAX_BPM_DIGIT_X_OFFSET
    top_left_x_with_offset = min_bpm_area_x_origin + column_offset
    bottom_right_x_with_offset = (
        top_left_x_with_offset + CONSTANTS.MIN_MAX_BPM_DIGIT_X_OFFSET
    )
    top_left = Point(y=min_bpm_area_y_origin, x=top_left_x_with_offset)
    bottom_right = Point(
        y=min_bpm_area_y_origin + CONSTANTS.MIN_MAX_BPM_DIGIT_Y_OFFSET,
        x=bottom_right_x_with_offset,
    )
    log.debug(f"TOP LEFT {top_left} BOTTOM_RIGHT {bottom_right}")
    digit_block = get_rectanglular_subsection_from_frame(
        frame, top_left.y, top_left.x, bottom_right.y, bottom_right.x
    )
    return min_max_bpm_digit_reader(digit_block)


def read_max_bpm_area(
    frame: NDArray, place_index: int, left_side: bool, is_double: bool
) -> int:
    if is_double:
        max_bpm_area_x_origin = CONSTANTS.MAX_BPM_DP_AREA_X_ORIGIN
        max_bpm_area_y_origin = CONSTANTS.MAX_BPM_DP_AREA_Y_ORIGIN
    elif left_side:
        max_bpm_area_x_origin = CONSTANTS.MAX_BPM_SP_1P_AREA_X_ORIGIN
        max_bpm_area_y_origin = CONSTANTS.MAX_BPM_SP_1P_AREA_Y_ORIGIN
    else:
        max_bpm_area_x_origin = CONSTANTS.MAX_BPM_SP_2P_AREA_X_ORIGIN
        max_bpm_area_y_origin = CONSTANTS.MAX_BPM_SP_2P_AREA_Y_ORIGIN
    column_offset = place_index * CONSTANTS.MIN_MAX_BPM_DIGIT_X_OFFSET
    top_left_x_with_offset = max_bpm_area_x_origin + column_offset
    bottom_right_x_with_offset = (
        top_left_x_with_offset + CONSTANTS.MIN_MAX_BPM_DIGIT_X_OFFSET
    )
    top_left = Point(y=max_bpm_area_y_origin, x=top_left_x_with_offset)
    bottom_right = Point(
        y=max_bpm_area_y_origin + CONSTANTS.MIN_MAX_BPM_DIGIT_Y_OFFSET,
        x=bottom_right_x_with_offset,
    )
    log.debug(f"TOP LEFT {top_left} BOTTOM_RIGHT {bottom_right}")
    digit_block = get_rectanglular_subsection_from_frame(
        frame, top_left.y, top_left.x, bottom_right.y, bottom_right.x
    )
    return min_max_bpm_digit_reader(digit_block)


def current_bpm_digit_reader(block: NDArray) -> int:
    log.debug("\n" + get_array_as_ascii_art(block))
    top_mid = Point(y=1, x=12)
    mid1 = Point(y=7, x=12)
    mid_left = Point(y=9, x=2)
    mid2 = Point(y=9, x=12)
    mid_right_curve = Point(y=9, x=24)
    bottom_left_floor = Point(y=15, x=4)
    bottom_left_leg = Point(y=12, x=4)
    top_right = Point(y=3, x=22)
    if is_white(read_pixel(block, mid1)):
        log.debug("MIGHT BE 123568")
        if is_white(read_pixel(block, mid_right_curve)):
            log.debug("MIGHT BE 568")
            if is_white(read_pixel(block, top_right)):
                log.debug("DEFINITELY 8")
                return 8
            elif is_white(read_pixel(block, bottom_left_leg)):
                log.debug("DEFINITELY 6")
                return 6
            else:
                log.debug("DEFINITELY 5")
                return 5
        else:
            log.debug("MIGHT BE 123")
            if is_white(read_pixel(block, mid_left)):
                log.debug("DEFINITELY 2")
                return 2
            elif is_white(read_pixel(block, bottom_left_floor)):
                log.debug("DEFINITELY 3")
                return 3
            else:
                log.debug("DEFINITELY 1")
                return 1
    else:
        log.debug("MIGHT BE 0479_")
        if is_white(read_pixel(block, mid2)):
            log.debug("MIGHT BE 49")
            if is_white(read_pixel(block, top_mid)):
                log.debug("DEFINITELY 9")
                return 9
            else:
                log.debug("DEFINITELY 9")
                return 4
        else:
            log.debug("MIGHT BE 07_")
            if is_white(read_pixel(block, bottom_left_floor)):
                log.debug("DEFINITELY 0")
                return 0
            elif is_white(read_pixel(block, top_mid)):
                log.debug("DEFINITELY 7")
                return 7
            else:
                log.debug("DEFINITELY _")
                return 0


def read_current_bpm_area(
    frame: NDArray, place_index: int, left_side: bool, is_double: bool
) -> int:
    if is_double:
        bpm_area_x_origin = CONSTANTS.BPM_DP_AREA_X_ORIGIN
        bpm_area_y_origin = CONSTANTS.BPM_DP_AREA_Y_ORIGIN
    elif left_side:
        bpm_area_x_origin = CONSTANTS.BPM_SP_1P_AREA_X_ORIGIN
        bpm_area_y_origin = CONSTANTS.BPM_SP_1P_AREA_Y_ORIGIN
    else:
        bpm_area_x_origin = CONSTANTS.BPM_SP_2P_AREA_X_ORIGIN
        bpm_area_y_origin = CONSTANTS.BPM_SP_2P_AREA_Y_ORIGIN
    column_offset = place_index * CONSTANTS.BPM_DIGIT_X_OFFSET
    top_left_x_with_offset = bpm_area_x_origin + column_offset
    bottom_right_x_with_offset = top_left_x_with_offset + CONSTANTS.BPM_DIGIT_X_OFFSET
    top_left = Point(y=bpm_area_y_origin, x=top_left_x_with_offset)
    bottom_right = Point(
        y=bpm_area_y_origin + CONSTANTS.BPM_DIGIT_Y_OFFSET,
        x=bottom_right_x_with_offset,
    )
    log.debug(f"TOP LEFT {top_left} BOTTOM_RIGHT {bottom_right}")
    digit_block = get_rectanglular_subsection_from_frame(
        frame, top_left.y, top_left.x, bottom_right.y, bottom_right.x
    )
    return current_bpm_digit_reader(digit_block)


def read_bpm(frame: NDArray, left_side: bool, is_double: bool) -> Tuple[int, int]:
    places_count = 3
    cur_bpm = 0
    min_bpm = 0
    max_bpm = 0
    for place in range(0, places_count):
        exponent = (places_count - 1) - place
        tens_place = 10**exponent
        cur_bpm += tens_place * read_current_bpm_area(
            frame, place, left_side, is_double
        )
        min_bpm += tens_place * read_min_bpm_area(frame, place, left_side, is_double)
        max_bpm += tens_place * read_max_bpm_area(frame, place, left_side, is_double)
    if not min_bpm and not max_bpm:
        min_bpm = cur_bpm
        max_bpm = cur_bpm
    return min_bpm, max_bpm


def read_play_metadata(
    play_frame_count: int,
    play_frame: NDArray,
    video_processing_state: VideoProcessingState,
) -> Tuple[str, int, str, int, int, bool, bool]:

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
        lifebar_type = video_processing_state.difficulty
    if video_processing_state.min_bpm is None or video_processing_state.max_bpm is None:
        min_bpm, max_bpm = read_bpm(play_frame, left_side, is_double)
    else:
        min_bpm = video_processing_state.min_bpm
        max_bpm = video_processing_state.max_bpm
    return difficulty, level, lifebar_type, min_bpm, max_bpm, left_side, is_double
