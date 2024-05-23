#!/usr/bin/env python3
import os
import logging
from typing import Any
from pathlib import Path
import cv2 as cv  # type: ignore

from inf_score_analyzer.local_dataclasses import ClearType
from inf_score_analyzer.score_frame_processor import (
    get_clear_type_from_results_screen,
)


CLEAR_FILES_DIR = "./tests/hd_clear_type_images/"
CLEAR_FILES = [Path(file).absolute() for file in os.scandir(CLEAR_FILES_DIR)]
CLEAR_FILES_METADATA: dict[str, dict[str, Any]] = {}

for file in CLEAR_FILES:
    side, single_or_doubles, clear_type = file.name.split("_", maxsplit=2)
    clear_type = clear_type.replace(".png", "")
    # TODO: add 2p side files
    if side == "P1":
        left_side = True
    else:
        left_side = False
    CLEAR_FILES_METADATA[str(file.absolute())] = {
        "clear_type": ClearType[clear_type],
        "left_side": left_side,
    }


def test_clear_type_reader():
    for file, attributes in CLEAR_FILES_METADATA.items():
        logging.debug(f"{file}")
        frame = cv.imread(file)
        assert attributes["clear_type"] == get_clear_type_from_results_screen(
            frame, attributes["left_side"]
        )
