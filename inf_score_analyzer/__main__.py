#!/usr/bin/env python3
import uuid
import logging
import argparse
from typing import Any
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime, timezone
from concurrent.futures import ProcessPoolExecutor

# library imports
import cv2 as cv  # type: ignore

# local imports
from . import sqlite_client
from . import frame_utilities
from . import game_state_pixels
from . import play_frame_processor
from . import score_frame_processor
from .game_state_frame_processor import get_game_state_from_frame
from . import download_12sp_tables

from . import constants as CONSTANTS
from .local_dataclasses import (
    GameState,
    GameStatePixel,
    SongReference,
    VideoProcessingState,
)
from .kamaitachi_client import export_to_kamaitachi


def process_video(
    state_pixels: list[GameStatePixel],
    session_uuid: str,
    song_reference: SongReference,
    ocr: ProcessPoolExecutor,
    video: cv.VideoCapture,
) -> None:
    lookback = 90
    frame_count = 0
    v = VideoProcessingState()
    score_frame_dumped = False
    while video.isOpened():
        frame_loaded, frame = video.read()
        if not frame_loaded:
            log.info("End of video stream")
            return
        frame_count += 1
        state: GameState = get_game_state_from_frame(frame, state_pixels)
        v.update_current_state(state)
        if frame_count % 300 == 0:
            log.info(f"frame#{frame_count} {v}")
            if CONSTANTS.DEV_MODE and (frame_count % 3000 == 0):
                frame_utilities.dump_to_png(frame, state.value, frame_count)
        if v.state_frame_count >= lookback:
            if v.current_state in game_state_pixels.PLAY_STATES:
                play_frame_processor.update_video_processing_state(
                    frame, frame_count, v, song_reference, ocr
                )
            elif v.current_state in game_state_pixels.SCORE_STATES:
                score_frame_processor.update_video_processing_state(
                    frame, frame_count, v, song_reference
                )
                if not score_frame_dumped:
                    frame_utilities.dump_to_png(frame, state.value, frame_count)
                    score_frame_dumped = True
        elif (
            v.current_state == GameState.LOADING
            and v.previous_state in game_state_pixels.SCORE_STATES
        ):
            score_frame_processor.handle_score_transition(
                frame_count, v, song_reference, session_uuid
            )
            log.info(f"frame#{frame_count}:unblocking naming and scoring")
            v = VideoProcessingState()
            score_frame_dumped = False
        elif v.current_state == GameState.SONG_SELECT:
            if v.returned_to_song_select_before_writing():
                log.warning(
                    f"frame#{frame_count}: Appears no write to "
                    "db succeeded, skipping previous results."
                )
                log.info(f"frame#{frame_count}:unblocking naming and scoring")
                v = VideoProcessingState()
                score_frame_dumped = False
    return


def video_processing_loop(
    source_id: int,
    state_pixels: list[GameStatePixel],
    session_uuid: str,
    song_reference: SongReference,
) -> None:
    with video_capture(source_id) as video, ProcessPoolExecutor(max_workers=1) as ocr:
        log.info("Starting video processing loop")
        # TODO: check the size of the frame before processing
        process_video(state_pixels, session_uuid, song_reference, ocr, video)
    return


def load_video_source(args: argparse.Namespace) -> cv.VideoCapture:
    # TODO: figure out how to enumerate system webcam IDs/hardware
    log.info("Reading frames from default webcam")
    return cv.VideoCapture(0)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    # TODO: figure out how to query for the correct video device
    parser.add_argument(
        "--png-file",
        action="extend",
        type=str,
        nargs="*",
        dest="png_files",
        help="A png of the score screen",
        default=[],
    )
    parser.add_argument(
        "--force-update",
        action="store_const",
        dest="force_update",
        const=True,
        help="Will force a song metadata DB update regardless of recency",
        default=False,
    )
    return parser.parse_args()


def end_session(session_uuid: str) -> None:
    sqlite_client.write_session_end(session_uuid)
    export_to_kamaitachi(session_uuid)


def start_session() -> str:
    session_start_time_utc = datetime.now(timezone.utc)
    session_uuid = str(uuid.uuid4())
    sqlite_client.write_session_start(session_start_time_utc, session_uuid)
    return session_uuid


@contextmanager
def video_capture(video_source_id: int = 0) -> Any:
    video_source = cv.VideoCapture(video_source_id)
    try:
        yield video_source
    finally:
        video_source.release()


def read_scores_from_pngs(
    png_files: list[Path], state_pixels: list[GameStatePixel]
) -> None:
    for image in png_files:
        frame = cv.imread(str(image.absolute()))
        # TODO: fix SELECT_OPTIONS
        # TODO: fix DP_PLAY
        # TODO: fix alternative layouts
        # TODO: have this use the same code path as the video loop
        game_state: GameState = get_game_state_from_frame(frame, state_pixels)
        is_double = False
        left_side = True
        log.info(f"png game state: {game_state}")
        if game_state in game_state_pixels.SCORE_STATES:
            logging.info(f"reading score from {image}")
            # TODO: fix this
            score = score_frame_processor.get_score_from_result_screen(
                frame, left_side, is_double
            )
            notes = score_frame_processor.get_note_count(frame)
            log.info(f"returned score: {score}")
            log.info(f"returned notes: {notes}")
        elif game_state in game_state_pixels.PLAY_STATES:
            player, single_or_double, _ = game_state.value.split("_")
            if player == "2P":
                left_side = False
            if single_or_double == "DP":
                is_double = True
            min_bpm, max_bpm = play_frame_processor.read_bpm(
                frame, left_side, is_double
            )
            play_level = play_frame_processor.read_play_level(
                frame, left_side, is_double
            )
            difficulty = play_frame_processor.read_play_difficulty(
                frame, left_side, is_double
            )
            song_titles = play_frame_processor.get_ocr_song_title_from_play_frame(
                frame, left_side, is_double
            )
            log.info(f"returned bpm: {min_bpm} {max_bpm}")
            log.info(f"play level: {play_level}")
            log.info(f"play difficulty: {difficulty}")
            log.info(f"song titles: {song_titles}")


def load_pngs(png_files: list[str]) -> list[Path]:
    pngs: list[Path] = []
    for filename in png_files:
        absolute_location = Path(filename).absolute()
        if absolute_location.exists():
            pngs.append(absolute_location)
    if pngs:
        log.info(f"Reading image files from {pngs}")
    return pngs


def startup() -> tuple[list[Path], SongReference]:
    args = parse_arguments()
    sqlite_client.sqlite_setup(args.force_update)
    song_reference = sqlite_client.read_song_data_from_db()
    png_paths = load_pngs(args.png_files)
    download_12sp_tables.download_and_normalize_data(song_reference)
    return png_paths, song_reference


def main() -> None:
    png_paths, song_reference = startup()
    if png_paths:
        read_scores_from_pngs(png_paths, game_state_pixels.ALL_STATE_PIXELS)
        return
    source_id = 0
    try:
        session_uuid = start_session()
        video_processing_loop(
            source_id, game_state_pixels.ALL_STATE_PIXELS, session_uuid, song_reference
        )
    except KeyboardInterrupt:
        pass
    finally:
        log.info("closing session and shutting down")
        end_session(session_uuid)
    return


logging.basicConfig(level=logging.INFO, format=CONSTANTS.LOG_FORMAT)
log = logging.getLogger(__name__)
log.info("starting up")
main()
log.info("done")
