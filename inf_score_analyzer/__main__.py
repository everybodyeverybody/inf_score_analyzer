#!/usr/bin/env python3
import uuid
import logging
import argparse
import traceback
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
from . import song_select_frame_processor

from . import download_12sp_tables

from . import constants as CONSTANTS
from .local_dataclasses import (
    GameState,
    GameStatePixel,
    VideoProcessingState,
)
from .song_reference import SongReference
from . import kamaitachi_client


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
    log.info(f"Reading frames from video source: {args.video_source_id}")
    return cv.VideoCapture(args.video_source_id)


def shutdown(session_uuid: str) -> None:
    log.info(f"Closing session {session_uuid} and shutting down")
    sqlite_client.write_session_end(session_uuid)
    kamaitachi_client.export_to_kamaitachi(session_uuid)


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
    png_files: list[Path],
    state_pixels: list[GameStatePixel],
    session_uuid: str,
    song_reference: SongReference,
) -> None:
    with ProcessPoolExecutor(max_workers=1) as ocr:
        for image in png_files:
            logging.info(f"Reading score from {image}")
            frame = cv.imread(str(image.absolute()))
            game_state: GameState = get_game_state_from_frame(frame, state_pixels)
            log.debug(f"PNG GAME STATE: {game_state}")
            try:
                if game_state in game_state_pixels.SCORE_STATES:
                    textage_id, score, difficulty, ocr_titles = (
                        score_frame_processor.read_score_and_song_metadata(
                            frame, song_reference, game_state, ocr
                        )
                    )
                elif game_state in game_state_pixels.SONG_SELECT_STATES:
                    textage_id, score, difficulty, ocr_titles = (
                        song_select_frame_processor.read_score_and_song_metadata(
                            frame, song_reference
                        )
                    )
                else:
                    log.error(
                        f"Could not read song select or score result from {image}, continuing"
                    )
                    continue
                sqlite_client.write_score(
                    session_uuid, textage_id, score, difficulty, ocr_titles, frame
                )
            except Exception as e:
                log.error(
                    f"Could not determine score from {image} and skipping : {e} : {traceback.format_exc()}"
                )
                continue
    return


def load_pngs(png_files: list[str]) -> list[Path]:
    pngs: list[Path] = []
    for filename in png_files:
        absolute_location = Path(filename).absolute()
        if absolute_location.exists():
            pngs.append(absolute_location)
        else:
            log.warning(
                f"Could not find screenshot file {absolute_location}, skipping."
            )
    if pngs:
        log.info(f"Reading game score screenshots from {pngs}")
    return pngs


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--force-update",
        action="store_true",
        help="Will force a song metadata DB update regardless of recency",
        dest="force_update",
    )
    parser.add_argument(
        "--video-mode",
        action="store_true",
        help=(
            "Sets script to run scanning a raw 1920x1080 video source "
            "for the game inputs instead of screenshots."
        ),
        dest="video_mode",
    )
    parser.add_argument(
        "--video-source-id",
        type=int,
        help=(
            "The ID for the video input device. Defaults to 0, "
            "the first input device found on the system."
        ),
        default=0,
        dest="video_source_id",
    )
    parser.add_argument(
        "screenshots", help=("A list of paths to screenshots."), nargs="*"
    )
    return parser.parse_args()


def startup() -> tuple[argparse.Namespace, SongReference]:
    args = parse_arguments()
    sqlite_client.sqlite_setup(args.force_update)
    song_reference = sqlite_client.read_song_data_from_db()
    download_12sp_tables.download_and_normalize_data(song_reference)
    return args, song_reference


def main() -> None:
    args, song_reference = startup()
    log.info(f"Running with arguments: {args}")
    session_uuid = start_session()
    if args.video_mode:
        try:
            video_processing_loop(
                args.video_source_id,
                game_state_pixels.ALL_STATE_PIXELS,
                session_uuid,
                song_reference,
            )
        except KeyboardInterrupt:
            pass
        finally:
            shutdown(session_uuid)
    else:
        try:
            pngs = load_pngs(args.screenshots)
            read_scores_from_pngs(
                pngs, game_state_pixels.ALL_STATE_PIXELS, session_uuid, song_reference
            )
        finally:
            shutdown(session_uuid)
    return


logging.basicConfig(level=logging.INFO, format=CONSTANTS.LOG_FORMAT)
log = logging.getLogger(__name__)
log.info("starting up")
main()
log.info("done")
