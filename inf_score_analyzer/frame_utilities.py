#!/usr/bin/env python3
import os
import logging
from pathlib import Path
from typing import Callable
from datetime import datetime

import numpy  # type: ignore
import cv2 as cv  # type: ignore
from numpy.typing import NDArray  # type: ignore
from .local_dataclasses import NumberArea
from .constants import (
    QUANTIZED_WHITE_MAX,
    QUANTIZED_BLACK_MIN,
    BRIGHTNESS_HALFWAY_POINT,
    DATA_DIR,
    GRAYSCALE_BLUE,
    GRAYSCALE_GREEN,
    GRAYSCALE_RED,
)
from .local_dataclasses import GameStatePixel, Point

from line_profiler import profile  # type: ignore

log = logging.getLogger(__name__)


def dump_to_ndarray_zip_file(frame: NDArray, label: str, frame_id: int) -> Path:
    label = label.strip()
    current_date = datetime.now().strftime("%Y%m%d%H%m%s")
    write_dir = DATA_DIR / Path("ndarray-dumps")
    if not write_dir.exists():
        os.makedirs(write_dir, exist_ok=True)
    filename = Path(f"{current_date}_{label}_{frame_id}.npz")
    output_file = str(write_dir / filename)
    log.info(f"Dumping {label} frame:{frame_id} to {output_file}")
    numpy.savez_compressed(output_file, frame_slice=frame)
    log.info("Done dumping frame")
    return Path(output_file)


def read_from_ndarray_zip_file(ndarray_zip_file: Path) -> NDArray:
    return numpy.load(ndarray_zip_file)["frame_slice"]


def dump_to_png(frame: NDArray, label: str, frame_id: int) -> Path:
    current_date = datetime.now().strftime("%Y%m%d%H%m%s")
    write_dir = DATA_DIR / Path("png-dumps")
    if not write_dir.exists():
        os.makedirs(write_dir, exist_ok=True)
    filename = Path(f"{current_date}_{label}_{frame_id}.png")
    output_file = str(write_dir / filename)
    log.info(f"Dumping {label} frame:{frame_id} to {output_file}")
    cv.imwrite(output_file, frame)
    log.info("Done dumping frame")
    return Path(output_file)


def read_from_png(png_file: Path) -> NDArray:
    return cv.imread(str(png_file))


def get_rectanglular_subsection_from_frame(
    frame: NDArray,
    top_left_y: int,
    top_left_x: int,
    bottom_right_y: int,
    bottom_right_x: int,
) -> NDArray:
    """
    I cannot remember this syntax for the life of me so I redid it
    as a helper method.
    """

    if bottom_right_y < top_left_y:
        raise RuntimeError(
            f"bottom_right_y > top_left_y {bottom_right_y} > {top_left_y}. "
            "Cannot get subsection that does not have increasing coordinates."
        )

    if bottom_right_x < top_left_x:
        raise RuntimeError(
            f"bottom_right_x > top_left_x {bottom_right_x} > {top_left_x}. "
            "Cannot get subsection that does not have increasing coordinates."
        )
    return frame[top_left_y:bottom_right_y, top_left_x:bottom_right_x]


def get_array_as_ascii_art(block: NDArray, use_black: bool = False) -> str:
    output_string = ""
    rows = None
    columns = None
    for y_index, y in enumerate(block):
        if rows is None:
            rows = "".join([str(y % 10) for y in range(0, len(block))])
        for x_index, x in enumerate(y):
            if columns is None:
                columns = "#" + "".join([str(x % 10) for x in range(0, len(y))])
            if y_index == 0 and x_index == 0:
                output_string += columns + "\n"

            if x_index == 0:
                output_string += rows[y_index]
            if not use_black:
                if is_white_pixel(x[0:3]):
                    output_string += "X"
                else:
                    output_string += "_"
            else:
                if not is_black_pixel(x[0:3]):
                    output_string += "X"
                else:
                    output_string += "_"
        output_string += "\n"
    return output_string


def dump_colors(
    frame: NDArray,
    top_left_y: int,
    top_left_x: int,
    bottom_right_y: int,
    bottom_right_x: int,
) -> set[tuple[int, int, int]]:
    dumped_colors: set[tuple[int, int, int]] = set([])
    for y in range(top_left_y, bottom_right_y):
        for x in range(top_left_x, bottom_right_x):
            t = (
                int(frame[y][x][0]),
                int(frame[y][x][1]),
                int(frame[y][x][2]),
            )
            dumped_colors.add(t)
    return dumped_colors


def flatten_difficulty_gradients(
    frame: NDArray,
    top_left_y: int,
    top_left_x: int,
    bottom_right_y: int,
    bottom_right_x: int,
    gradient: set[tuple[int, int, int]],
    match_level=255,
    miss_level=0,
) -> None:
    for y in range(top_left_y, bottom_right_y):
        for x in range(top_left_x, bottom_right_x):
            pixel: tuple[int, int, int] = (
                int(frame[y][x][0]),
                int(frame[y][x][1]),
                int(frame[y][x][2]),
            )
            if pixel in gradient:
                frame[y][x][0] = match_level
                frame[y][x][1] = match_level
                frame[y][x][2] = match_level
            else:
                frame[y][x][0] = miss_level
                frame[y][x][1] = miss_level
                frame[y][x][2] = miss_level


def polarize_area(
    frame: NDArray,
    top_left_y: int,
    top_left_x: int,
    bottom_right_y: int,
    bottom_right_x: int,
    cutoff_bgr: tuple[int, int, int] = (145, 145, 145),
    cutoff_bgr_below_color: tuple[int, int, int] = (255, 255, 255),
    cutoff_bgr_above_color: tuple[int, int, int] = (0, 0, 0),
) -> NDArray:
    for y in range(top_left_y, bottom_right_y):
        for x in range(top_left_x, bottom_right_x):
            if (
                frame[y][x][0] < cutoff_bgr[0]
                and frame[y][x][1] < cutoff_bgr[1]
                and frame[y][x][2] < cutoff_bgr[2]
            ):
                frame[y][x][0] = cutoff_bgr_below_color[0]
                frame[y][x][1] = cutoff_bgr_below_color[1]
                frame[y][x][2] = cutoff_bgr_below_color[2]
            else:
                frame[y][x][0] = cutoff_bgr_above_color[0]
                frame[y][x][1] = cutoff_bgr_above_color[1]
                frame[y][x][2] = cutoff_bgr_above_color[2]
    return frame


def grayscale_area(
    frame: NDArray,
    top_left_y: int,
    top_left_x: int,
    bottom_right_y: int,
    bottom_right_x: int,
    keep_bright_whites: bool = True,
) -> NDArray:
    """
    reference: https://scikit-image.org/docs/0.25.x/auto_examples/color_exposure/plot_rgb_to_gray.html
    """
    for y in range(top_left_y, bottom_right_y):
        for x in range(top_left_x, bottom_right_x):
            point = Point(y=y, x=x)
            if keep_bright_whites and is_white(frame, point):
                continue
            gb = frame[y][x][0] * GRAYSCALE_BLUE
            gg = frame[y][x][1] * GRAYSCALE_GREEN
            gr = frame[y][x][2] * GRAYSCALE_RED
            grayscale_y = int((gb + gg + gr) / 3)
            frame[y][x][0] = grayscale_y
            frame[y][x][1] = grayscale_y
            frame[y][x][2] = grayscale_y
    return frame


def read_pixel(block: NDArray, point: Point) -> list:
    # TODO: only run if debug logging is on
    # log.debug(f"{point} {block[point.y][point.x][0:3]}")
    return block[point.y][point.x][0:3]


def is_white_pixel(rgb_or_bgr: list) -> bool:
    log.debug(
        "{} {} {}".format(
            rgb_or_bgr[0] >= QUANTIZED_WHITE_MAX,
            rgb_or_bgr[1] >= QUANTIZED_WHITE_MAX,
            rgb_or_bgr[2] >= QUANTIZED_WHITE_MAX,
        )
    )
    return (
        rgb_or_bgr[0] >= QUANTIZED_WHITE_MAX
        and rgb_or_bgr[1] >= QUANTIZED_WHITE_MAX
        and rgb_or_bgr[2] >= QUANTIZED_WHITE_MAX
    )


def is_white(block: NDArray, point: Point) -> bool:
    return is_white_pixel(read_pixel(block, point))


def is_black_pixel(rgb_or_bgr: list) -> bool:
    return (
        rgb_or_bgr[0] <= QUANTIZED_BLACK_MIN
        and rgb_or_bgr[1] <= QUANTIZED_BLACK_MIN
        and rgb_or_bgr[2] <= QUANTIZED_BLACK_MIN
    )


def is_black(block: NDArray, point: Point) -> bool:
    return is_black_pixel(read_pixel(block, point))


def is_bright_pixel(rgb_or_bgr: list, brightness_cutoff: int = 2) -> bool:
    brightness_check = 0
    log.debug(f"{rgb_or_bgr}")
    for value in rgb_or_bgr:
        if value >= BRIGHTNESS_HALFWAY_POINT:
            brightness_check += 1
        log.debug(f"{value} >= {BRIGHTNESS_HALFWAY_POINT}")
    log.debug(f"BRIGHTNESS CHECK: {brightness_check} >= {brightness_cutoff}")
    return brightness_check >= brightness_cutoff


def is_bright(block: NDArray, point: Point, brightness_cutoff: int = 2) -> bool:
    return is_bright_pixel(read_pixel(block, point), brightness_cutoff)


def check_point_color(
    frame: NDArray, point: Point, color_bgr: tuple[int, int, int], tolerance: int = 15
):
    game_state_pixel = GameStatePixel(
        y=point.y, x=point.x, b=color_bgr[0], g=color_bgr[1], r=color_bgr[2]
    )
    return check_pixel_color_in_frame(frame, game_state_pixel, tolerance)


@profile
def check_pixel_color_in_frame(
    frame: NDArray,
    pixel: GameStatePixel,
    tolerance: int = 15,
) -> bool:
    if pixel.r >= 0:
        max_red = pixel.r + tolerance
        min_red = pixel.r - tolerance
    else:
        max_red = 255
        min_red = 0

    if pixel.g >= 0:
        max_green = pixel.g + tolerance
        min_green = pixel.g - tolerance
    else:
        max_green = 255
        min_green = 0

    if pixel.b >= 0:
        max_blue = pixel.b + tolerance
        min_blue = pixel.b - tolerance
    else:
        max_blue = 255
        min_blue = 0

    blue_match: bool = (
        frame[pixel.y][pixel.x][0] >= min_blue
        and frame[pixel.y][pixel.x][0] <= max_blue
    )
    green_match: bool = (
        frame[pixel.y][pixel.x][1] >= min_green
        and frame[pixel.y][pixel.x][1] <= max_green
    )
    red_match: bool = (
        frame[pixel.y][pixel.x][2] >= min_red and frame[pixel.y][pixel.x][2] <= max_red
    )

    if red_match and blue_match and green_match:
        result = True
    else:
        result = False

    output = "frame pixel: {}, b:{}:{} g:{}:{} r:{}:{}".format(
        pixel,
        frame[pixel.y][pixel.x][0],
        blue_match,
        frame[pixel.y][pixel.x][1],
        green_match,
        frame[pixel.y][pixel.x][2],
        red_match,
    )
    log.debug(output)
    return result


def get_numbers_from_area(
    frame: NDArray,
    area: NumberArea,
    block_reader: Callable,
) -> list[int]:
    numbers: list[int] = []
    log.debug(f"Using {area.name} for coordinates: {area}")
    for row in range(area.rows):
        number: int = 0
        row_start_y = area.start_y + (row * area.y_offset)
        for column_index in range(area.digits_per_row):
            kerning_offset = 0
            if area.kerning_offset:
                kerning_offset = area.kerning_offset[column_index]
            place = 10 ** (area.digits_per_row - (column_index + 1))
            end_y = row_start_y + area.y_offset
            block_start_x = (
                area.start_x + (area.x_offset * column_index) + kerning_offset
            )
            block_end_x = block_start_x + area.x_offset
            score_digit_block = get_rectanglular_subsection_from_frame(
                frame, row_start_y, block_start_x, end_y, block_end_x
            )
            if logging.getLogger().isEnabledFor(logging.DEBUG):
                log.debug("ASCII\n%s", get_array_as_ascii_art(score_digit_block))
            read_number = block_reader(score_digit_block)
            number += read_number * place
        numbers.append(number)
    return numbers


def show_frame(frame: NDArray) -> None:
    key = "s"
    log.info(f"PRESS {key} TO CLOSE PREVIEW")
    cv.imshow("Display", frame)
    k = cv.waitKey(0)
    if k == ord(key):
        return
