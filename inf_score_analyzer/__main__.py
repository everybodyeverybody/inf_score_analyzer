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
from numpy.typing import NDArray  # type: ignore

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
    Score,
    GameState,
    Difficulty,
    GameStatePixel,
    VideoProcessingState,
    OCRSongTitles,
)
from .song_reference import SongReference
from . import kamaitachi_client
from . import csv_processor


def process_video(
    state_pixels: list[GameStatePixel],
    session_uuid: str,
    song_reference: SongReference,
    ocr: ProcessPoolExecutor,
    video: cv.VideoCapture,
) -> None:
    """
    Reads song and score metadata from a live, raw hdmi stream of data.

    The game loop goes between the following screen-types:

    Song Select -> White Flash -> Song Selection Confirmed -> Fade to Black ->
    Fade in to Play Screen -> Song Completion OR Song Failure Transition -> Fade to Black ->
    Score Result Screen -> Song Select OR Retry Transition

    Each of these screens contain different kinds of metadata about the song we
    use to resolve what song is being played without directly going to OCR. The
    ordering of screens is stable, so we can figure out where we're at in the
    processing loop and read the available song metadata we need when it is available.
    This is loaded into a VideoProcessingState that is generated and cleared once per loop.

    We generally OCR asynchronously as to not interrup the state processing loop,
    but there are cases where we try to resolve the title on the Score Result screen which
    may call OCR and block temporarily.

    The loop is currently broken by KeyboardInterrupt, the stream ending, process kills, or
    unhandled exceptions. We tried to make this resillient to failure so that
    most exceptions are handled by failing to read the score and not by crashing
    out of the application.

    This was previously the focus of this script, but I found it easier to dump
    and process pngs in terms of my gaming PC setup, so I added that later.
    """
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


def manually_validate(
    song_reference: SongReference,
    image: Path,
    textage_id: str,
    score: Score,
    difficulty: Difficulty,
    ocr_titles: OCRSongTitles,
    frame: NDArray,
):
    print("")
    print(f"Here's the details of {image}:")
    print(f"song: {song_reference.by_textage_id[textage_id]}")
    print(f"score: {score}")
    print(f"score: {difficulty}")
    print("is this correct (y/n)?")
    cv.imshow("Validation", frame)
    answer = cv.waitKey(0)
    print(answer)
    if answer in [ord("y"), ord("Y")]:
        print("Validated.")
        valid = True
    else:
        print("Rejected.")
        valid = False
    print("")
    return valid


def read_scores_from_pngs(
    png_files: list[Path],
    state_pixels: list[GameStatePixel],
    session_uuid: str,
    song_reference: SongReference,
    manual_validation: bool,
) -> None:
    """
    Use combination of module methods and tesseract to
    read song score data from a screenshot of either the Song Select
    screen or the Score Results screen.

    We launch a subprocess to contain the tesseract worker subprocess.
    """
    for image in png_files:
        log.info(f"Reading score from {image}")
        frame = cv.imread(str(image.absolute()))
        game_state: GameState = get_game_state_from_frame(frame, state_pixels)
        log.debug(f"PNG GAME STATE: {game_state}")
        try:
            if game_state in game_state_pixels.SCORE_STATES:
                textage_id, score, difficulty, ocr_titles = (
                    score_frame_processor.read_score_and_song_metadata(
                        frame, song_reference, game_state
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
                if manual_validation:
                    valid = manually_validate(
                        song_reference,
                        image,
                        textage_id,
                        score,
                        difficulty,
                        ocr_titles,
                        frame,
                    )
                    if not valid:
                        log.info(
                            f"Rejecting {image} {textage_id} {score} {difficulty} {ocr_titles} manually"
                        )
                        continue

                sqlite_client.write_score(
                    session_uuid, textage_id, score, difficulty, ocr_titles, frame
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
    """
    Validate the list of files provided to the script that they exist
    before attempting to read them. Skips any files not found by
    the script with a warning.
    """
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
        "--csv",
        type=str,
        help=("Optional. A CSV file to import data from."),
        default=None,
        dest="csv_file",
    )
    parser.add_argument(
        "screenshots", help=("A list of paths to screenshots."), nargs="*"
    )
    parser.add_argument(
        "--batch-screenshot-dir",
        type=str,
        help=(
            "Optional. Will read all screenshots from a directory and attempt to parse them."
        ),
        default=None,
        dest="batch_screenshot_dir",
    )
    parser.add_argument(
        "--manual-validation",
        action="store_true",
        help=(
            "Optional. Allows manual validation of screenshots. Used for debugging the script."
        ),
        dest="manual_validation",
    )
    return parser.parse_args()


def get_screenshot_list_from_dir(batch_screenshot_dir: str) -> list[Path]:
    screenshot_dir_path = Path(batch_screenshot_dir)
    return [
        file for file in screenshot_dir_path.iterdir() if file.suffix.lower() == ".png"
    ]


def startup() -> tuple[argparse.Namespace, SongReference]:
    """
    Reads in commandline arguments and sets up song metadata
    sqlite entries, returning a SongReference for lookups
    based on song metadata.
    """
    args = parse_arguments()
    sqlite_client.sqlite_setup(args.force_update)
    # TODO: make song reference a standalone module that can be called statically
    song_reference = sqlite_client.read_song_data_from_db()
    download_12sp_tables.download_and_normalize_data(song_reference)
    return args, song_reference


def main() -> None:
    """
    Entrypoint. Each instantiation generates a session uuid
    to mark off when scores were generated.

    Depending on flags runs in either video, csv,
    or png processing mode.

    On completion of any processing loop, closes the session,
    writes any unwritten score data to the db and attempts
    to export the session's scores to kamaitachi.
    """
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
    elif args.csv_file:
        try:
            csv_processor.import_scores_from_csv(
                session_uuid, Path(args.csv_file), song_reference
            )
        finally:
            shutdown(session_uuid)
    else:
        try:
            pngs: list[Path] = []
            if args.batch_screenshot_dir:
                pngs.extend(get_screenshot_list_from_dir(args.batch_screenshot_dir))
            else:
                pngs.extend(load_pngs(args.screenshots))
            read_scores_from_pngs(
                pngs,
                game_state_pixels.ALL_STATE_PIXELS,
                session_uuid,
                song_reference,
                args.manual_validation,
            )
        finally:
            shutdown(session_uuid)
    return


logging.basicConfig(
    filename="inf_score_analyzer.log", level=logging.INFO, format=CONSTANTS.LOG_FORMAT
)
log = logging.getLogger(__name__)
log.info("starting up")
main()
log.info("done")
