#!/usr/bin/env python3
import copy
import uuid
import logging
import sqlite3
import argparse
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Tuple, List, Any
from concurrent.futures import ProcessPoolExecutor

# library imports
import cv2 as cv  # type: ignore

# local imports
from . import frame_utilities
from . import constants as CONSTANTS
from .game_state_pixels import (
    ALL_STATE_PIXELS,
    SCORE_STATES,
    PLAY_STATES,
)
from .local_dataclasses import (
    GameState,
    GameStatePixel,
    SongReference,
    VideoProcessingState,
)
from .sqlite_setup import sqlite_setup, read_song_data_from_db
from .hd_play_frame_processor import (
    hd_get_ocr_song_title_from_play_frame,
    hd_read_play_metadata,
)
from . import hd_score_frame_processor as hd_result_processor
from .hd_game_state_frame_processor import (
    hd_get_game_state_from_frame,
)
from . import hd_play_frame_processor
from .kamaitachi_export import export_to_kamaitachi


def __loop_replacement(
    state_pixels: List[GameStatePixel],
    session_uuid: str,
    song_reference: SongReference,
    ocr: ProcessPoolExecutor,
    video: cv.VideoCapture,
) -> None:
    lookback = 90
    frame_count = 0
    v = VideoProcessingState()
    while video.isOpened():
        frame_loaded, frame = video.read()
        if not frame_loaded:
            log.info("End of video stream")
            return
        frame_count += 1
        state: GameState = hd_get_game_state_from_frame(frame, state_pixels)
        v.update_current_state(state)
        if frame_count % 300 == 0:
            log.info(f"frame#{frame_count} {v}")
        if frame_count % 1500 == 0:
            frame_utilities.dump_to_png(frame, state.name, frame_count)
        if v.current_state in PLAY_STATES and v.state_frame_count >= lookback:
            if v.play_metadata_missing():
                play_metadata = hd_read_play_metadata(frame_count, frame, v)
                v.update_play_metadata(play_metadata)
            if v.metadata_is_set_except_title():
                v.metadata_title = song_reference.resolve_by_play_metadata(
                    (v.difficulty, v.level), (v.min_bpm, v.max_bpm)
                )
            if v.know_sp_dp_and_sides_but_no_song_title():
                if v.ocr_song_future is None:
                    log.info(f"{v.current_state.name} frame#{frame_count} ocr call")
                    v.ocr_song_future = ocr.submit(
                        hd_get_ocr_song_title_from_play_frame,
                        frame,
                        v.left_side,
                        v.is_double,
                    )
                    log.info(
                        f"{v.current_state.name} frame#{frame_count} ocr future created"
                    )
                elif v.ocr_song_future.done():
                    v.ocr_song_title = v.ocr_song_future.result()
                    log.info("found ocr song title {v.ocr_song_title}")
        elif v.current_state in SCORE_STATES and v.state_frame_count >= lookback:
            if v.note_count is None:
                v.note_count = hd_result_processor.get_note_count(frame)
            if v.left_side is not None and v.is_double is not None:
                if v.score is None:
                    v.score = hd_result_processor.get_score_from_result_screen(
                        frame, v.left_side, v.is_double
                    )
                    log.debug(
                        f"frame#{frame_count}:{v.score}:NOTE COUNT {v.note_count}"
                    )
                if (
                    v.difficulty
                    and v.level
                    and v.min_bpm
                    and v.max_bpm
                    and v.note_count
                    and (v.metadata_title is None or len(v.metadata_title) > 1)
                ):
                    v.metadata_title = song_reference.resolve_by_play_metadata(
                        (v.difficulty, v.level),
                        (v.min_bpm, v.max_bpm),
                        v.note_count,
                    )
                if v.score_data_was_captured():
                    v.score_frame = copy.deepcopy(frame)
                    # if CONSTANTS.DEV_MODE:
                    #    frame_utilities.dump_to_png(frame, state.name, frame_count)
        elif v.current_state == GameState.LOADING and v.previous_state in SCORE_STATES:
            if (
                v.ocr_song_title is None
                and v.ocr_song_future is not None
                and v.ocr_song_future.done()
            ):
                v.ocr_song_title = v.ocr_song_future.result()
                log.info("found ocr song title {v.ocr_song_title}")
            if v.score_data_found_at_score_screen():
                log.info(f"frame#{frame_count}:writing score")
                hd_result_processor.write_score_sqlite(
                    session_uuid,  # type: ignore
                    v.ocr_song_title,  # type: ignore
                    v.score,  # type: ignore
                    v.difficulty,  # type: ignore
                    v.score_frame,  # type: ignore
                    song_reference,  # type: ignore
                    v.level,  # type: ignore
                    v.metadata_title,  # type: ignore
                )
                v = VideoProcessingState()
        elif v.current_state == GameState.SONG_SELECT:
            if v.returned_to_song_select_before_writing():
                log.warning(
                    f"frame#{frame_count}: Appears no write to "
                    "db succeeded, skipping previous results."
                )
                log.info(f"frame#{frame_count}:unblocking naming and scoring")
                v = VideoProcessingState()


def video_processing_loop(
    source_id: int,
    state_pixels: List[GameStatePixel],
    session_uuid: str,
    song_reference: SongReference,
) -> None:
    with video_capture(source_id) as video, ProcessPoolExecutor(max_workers=1) as ocr:
        log.info("Starting video processing loop")
        __loop_replacement(state_pixels, session_uuid, song_reference, ocr, video)
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
    session_end_time_utc = datetime.now(timezone.utc)
    session_end_query = "update session set end_time_utc=? where session_uuid=?"
    user_db_connection = sqlite3.connect(CONSTANTS.USER_DB)
    db_cursor = user_db_connection.cursor()
    db_cursor.execute(session_end_query, (session_end_time_utc, session_uuid))
    user_db_connection.commit()
    export_to_kamaitachi(session_uuid)


def start_session():
    session_start_time_utc = datetime.now(timezone.utc)
    session_uuid = str(uuid.uuid4())
    session_query = "insert into session values (?,?,?)"
    user_db_connection = sqlite3.connect(CONSTANTS.USER_DB)
    db_cursor = user_db_connection.cursor()
    db_cursor.execute(session_query, (session_uuid, session_start_time_utc, None))
    user_db_connection.commit()
    return session_uuid


@contextmanager
def video_capture(video_source_id: int = 0) -> Any:
    video_source = cv.VideoCapture(video_source_id)
    try:
        yield video_source
    finally:
        video_source.release()


def read_scores_from_pngs(
    png_files: List[Path], state_pixels: List[GameStatePixel]
) -> None:
    for image in png_files:
        frame = cv.imread(str(image.absolute()))
        # TODO: fix SELECT_OPTIONS
        # TODO: fix DP_PLAY
        # TODO: fix alternative layouts
        # TODO: have this use the same code path as the video loop
        game_state: GameState = hd_get_game_state_from_frame(frame, state_pixels)
        is_double = False
        left_side = True
        log.info(f"png game state: {game_state}")
        if game_state in SCORE_STATES:
            logging.info(f"reading score from {image}")
            # TODO: fix this
            score = hd_result_processor.get_score_from_result_screen(
                frame, left_side, is_double
            )
            notes = hd_result_processor.get_note_count(frame)
            log.info(f"returned score: {score}")
            log.info(f"returned notes: {notes}")
        elif game_state in PLAY_STATES:
            player, single_or_double, _ = game_state.value.split("_")
            if player == "2P":
                left_side = False
            if single_or_double == "DP":
                is_double = True
            min_bpm, max_bpm = hd_play_frame_processor.hd_read_bpm(
                frame, left_side, is_double
            )
            play_level = hd_play_frame_processor.hd_read_play_level(
                frame, left_side, is_double
            )
            difficulty = hd_play_frame_processor.hd_read_play_difficulty(
                frame, left_side, is_double
            )
            song_titles = hd_play_frame_processor.hd_get_ocr_song_title_from_play_frame(
                frame, left_side, is_double
            )
            log.info(f"returned bpm: {min_bpm} {max_bpm}")
            log.info(f"play level: {play_level}")
            log.info(f"play difficulty: {difficulty}")
            log.info(f"song titles: {song_titles}")


def load_pngs(png_files: List[str]) -> List[Path]:
    pngs: List[Path] = []
    for filename in png_files:
        absolute_location = Path(filename).absolute()
        if absolute_location.exists():
            pngs.append(absolute_location)
    if pngs:
        log.info(f"Reading image files from {pngs}")
    return pngs


def startup() -> Tuple[List[Path], SongReference]:
    args = parse_arguments()
    sqlite_setup(args.force_update)
    song_reference = read_song_data_from_db()
    png_paths = load_pngs(args.png_files)
    return png_paths, song_reference


def main() -> None:
    png_paths, song_reference = startup()
    if png_paths:
        read_scores_from_pngs(png_paths, ALL_STATE_PIXELS)
        return
    source_id = 0
    try:
        session_uuid = start_session()
        video_processing_loop(source_id, ALL_STATE_PIXELS, session_uuid, song_reference)
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
