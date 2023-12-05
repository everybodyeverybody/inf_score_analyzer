#!/usr/bin/env python3
import os
import logging
from pathlib import Path
from typing import Optional
from datetime import datetime

import numpy
import cv2 as cv  # type: ignore
from numpy.typing import NDArray

from .constants import (
    QUANTIZED_WHITE_MAX,
    QUANTIZED_BLACK_MIN,
    BRIGHTNESS_HALFWAY_POINT,
    DATA_DIR,
)
from .local_dataclasses import StatePixel, Point

log = logging.getLogger(__name__)


def read_pixel(block: NDArray, point: Point) -> list:
    log.debug(f"{point} {block[point.y][point.x][0:3]}")
    return block[point.y][point.x][0:3]


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


def verify_image_size(result_screen: NDArray) -> bool:
    y, x, dimensions = result_screen.shape
    log.debug(f"image size {x}x{y}")
    if y != 720 or x != 1280:
        return False
    return True


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
                if is_white(x[0:3]):
                    output_string += "X"
                else:
                    output_string += "_"
            else:
                if not is_black(x[0:3]):
                    output_string += "X"
                else:
                    output_string += "_"
        output_string += "\n"
    return output_string


def is_white(rgb_or_bgr: list) -> bool:
    return (
        rgb_or_bgr[0] >= QUANTIZED_WHITE_MAX
        and rgb_or_bgr[1] >= QUANTIZED_WHITE_MAX
        and rgb_or_bgr[2] >= QUANTIZED_WHITE_MAX
    )


def is_black(rgb_or_bgr: list) -> bool:
    return (
        rgb_or_bgr[0] <= QUANTIZED_BLACK_MIN
        and rgb_or_bgr[1] <= QUANTIZED_BLACK_MIN
        and rgb_or_bgr[2] <= QUANTIZED_BLACK_MIN
    )


def is_bright(rgb_or_bgr: list) -> bool:
    brightness_check = 0
    for value in rgb_or_bgr:
        if value >= BRIGHTNESS_HALFWAY_POINT:
            brightness_check += 1
    return brightness_check >= 2


def check_pixel_color_in_frame(
    frame: NDArray,
    pixel: StatePixel,
    specific_color: Optional[tuple[int, int, int]] = None,
    tolerance: int = 15,
) -> bool:
    frame_value = frame[pixel.y][pixel.x]
    # log.debug(f"check_pixel_color_in_frame frame_value {frame_value}")
    if specific_color is None:
        max_red = pixel.r + tolerance
        min_red = pixel.r - tolerance
        max_green = pixel.g + tolerance
        min_green = pixel.g - tolerance
        max_blue = pixel.b + tolerance
        min_blue = pixel.b - tolerance
    else:
        max_red = specific_color[2] + tolerance
        min_red = specific_color[2] - tolerance
        max_green = specific_color[1] + tolerance
        min_green = specific_color[1] - tolerance
        max_blue = specific_color[0] + tolerance
        min_blue = specific_color[0] - tolerance
    if (
        frame_value[0] >= min_blue
        and frame_value[0] <= max_blue
        and frame_value[1] >= min_green
        and frame_value[1] <= max_green
        and frame_value[2] >= min_red
        and frame_value[2] <= max_red
    ):
        result = True
    else:
        result = False
    return result
