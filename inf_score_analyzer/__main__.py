#!/usr/bin/env python3
import copy
import json
import uuid
import logging
import sqlite3
import argparse
from pathlib import Path
from collections import deque
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Dict, Set, Tuple, List, Any
from concurrent.futures import ProcessPoolExecutor

# library imports
import cv2 as cv  # type: ignore

# local imports
from . import frame_utilities
from . import constants as CONSTANTS
from .local_dataclasses import (
    StatePixel,
    SongReference,
    VideoProcessingState,
)
from .sqlite_setup import sqlite_setup
from .play_frame_processor import (
    get_ocr_song_title_from_play_frame,
    read_play_metadata,
)
from . import score_frame_processor as result_processor
from .game_state_frame_processor import get_game_state_from_frame


def __loop(
    state_pixels: List[StatePixel],
    session_uuid: str,
    song_reference: SongReference,
    ocr: ProcessPoolExecutor,
    video: cv.VideoCapture,
) -> None:
    lookback = 90
    frame_count = 0
    frame_queue: deque[str] = deque(maxlen=lookback)
    v = VideoProcessingState()
    while video.isOpened():
        frame_loaded, frame = video.read()
        if not frame_loaded:
            log.info("End of video stream")
            return
        frame_count += 1
        game_state: str = get_game_state_from_frame(frame, state_pixels)
        if frame_count % 300 == 0:
            log.info(f"frame: {frame_count} GAME STATE: {game_state}")
            log.info(v)
        # TODO: this is way too nested, flatten it if possible
        if game_state == "SP_PLAY" or game_state == "DP_PLAY":
            if len(frame_queue) >= lookback:
                coalesced_states = set(frame_queue)
                if coalesced_states == {"SP_PLAY"} or coalesced_states == {"DP_PLAY"}:
                    if v.play_metadata_missing():
                        play_metadata = read_play_metadata(frame_count, frame)
                        v.difficulty = play_metadata[0]
                        v.level = play_metadata[1]
                        v.lifebar_type = play_metadata[2]
                        v.min_bpm = play_metadata[3]
                        v.max_bpm = play_metadata[4]
                        v.left_side = play_metadata[5]
                        v.is_double = play_metadata[6]
                    if (
                        v.metadata_title is None
                        and v.difficulty
                        and v.level
                        and v.min_bpm
                        and v.max_bpm
                    ):
                        v.metadata_title = song_reference.resolve_by_play_metadata(
                            (v.difficulty, v.level), (v.min_bpm, v.max_bpm)
                        )
                        if CONSTANTS.DEV_MODE:
                            frame_utilities.dump_to_png(frame, game_state, frame_count)
                    if (
                        v.ocr_song_title is None
                        and v.left_side is not None
                        and v.is_double is not None
                    ):
                        if v.ocr_song_future is None:
                            log.info(
                                f"{game_state} frame#{frame_count} async pytesseract call to get song title from play screen"
                            )
                            v.ocr_song_future = ocr.submit(
                                get_ocr_song_title_from_play_frame,
                                frame,
                                v.left_side,
                                v.is_double,
                            )
                        elif v.ocr_song_future.done():
                            v.ocr_song_title = v.ocr_song_future.result()
        elif game_state == "1P_SCORE" or game_state == "2P_SCORE":
            if len(frame_queue) >= lookback and v.score is None:
                coalesced_states = set(frame_queue)
                if coalesced_states == {"1P_SCORE"} or coalesced_states == {"2P_SCORE"}:
                    v.note_count = result_processor.get_note_count(frame)
                    if v.left_side is not None and v.is_double is not None:
                        v.score = result_processor.get_score_from_result_screen(
                            frame, v.left_side, v.is_double, v.note_count
                        )
                        log.info(
                            f"frame#{frame_count}:{v.score}:NOTE COUNT {v.note_count}"
                        )
                        if v.difficulty and v.level and v.min_bpm and v.max_bpm:
                            v.metadata_title = song_reference.resolve_by_play_metadata(
                                (v.difficulty, v.level),
                                (v.min_bpm, v.max_bpm),
                                v.note_count,
                            )
                        if v.score_data_was_captured():
                            v.score_frame = copy.deepcopy(frame)
                            if CONSTANTS.DEV_MODE:
                                frame_utilities.dump_to_png(
                                    frame, game_state, frame_count
                                )
        elif game_state == "SONG_SELECT":
            if v.returned_to_song_select_before_writing():
                log.warning(
                    f"frame#{frame_count}: Appears no write to "
                    "db succeeded, skipping previous results."
                )
                log.info(f"frame#{frame_count}:unblocking naming and scoring")
                v = VideoProcessingState()
        else:
            if v.score_data_found_at_score_screen():
                log.info(f"frame#{frame_count}:writing score")
                # TODO: this is annoying
                result_processor.write_score_sqlite(
                    session_uuid,  # type: ignore
                    v.ocr_song_title,  # type: ignore
                    v.score,  # type: ignore
                    v.difficulty,  # type: ignore
                    v.score_frame,  # type: ignore
                    song_reference,  # type: ignore
                    v.level,  # type: ignore
                    v.metadata_title,  # type: ignore
                )
                log.info(f"frame#{frame_count}:unblocking naming and scoring")
                v = VideoProcessingState()
        frame_queue.appendleft(game_state)


def video_processing_loop(
    source_id: int,
    state_pixels: List[StatePixel],
    session_uuid: str,
    song_reference: SongReference,
) -> None:
    with video_capture(source_id) as video, ProcessPoolExecutor(max_workers=1) as ocr:
        __loop(state_pixels, session_uuid, song_reference, ocr, video)
    return


def load_video_source(args: argparse.Namespace) -> cv.VideoCapture:
    # TODO: figure out how to enumerate system webcam IDs/hardware
    log.info("Reading frames from default webcam")
    return cv.VideoCapture(0)


def read_state_pixels() -> List[StatePixel]:
    log.info(f"Reading pixel config from {CONSTANTS.STATE_PIXEL_CONFIG_FILE}")
    with open(CONSTANTS.STATE_PIXEL_CONFIG_FILE, "rt") as state_pixel_reader:
        pixel_config_json = json.load(state_pixel_reader)
        return [StatePixel(**entry) for entry in pixel_config_json]


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    # TODO: figure out how to query for the correct video device
    # for cv
    # TODO: future work for images instead of video
    #    parser.add_argument(
    #        "--png-file",
    #        action="extend",
    #        type=str,
    #        nargs="*",
    #        dest="png_files",
    #        help="A png of the score screen",
    #        default=[],
    #    )
    parser.add_argument(
        "--force-update",
        action="store_const",
        dest="force_update",
        const=True,
        help="Will force a song metadata DB update regardless of recency",
        default=False,
    )
    return parser.parse_args()


def read_song_data_from_db() -> SongReference:
    query = (
        "select s.textage_id,d.difficulty,sd.level,sd.notes,s.min_bpm, "
        "s.max_bpm, s.artist,s.title "
        "from songs s "
        "join song_difficulty_and_notes sd "
        "on sd.textage_id=s.textage_id "
        "join difficulty d on d.difficulty_id=sd.difficulty_id "
        "where sd.level!=0 order by sd.textage_id,sd.level"
    )
    songs_by_title: Dict[str, str] = {}
    songs_by_artist: Dict[str, Set[str]] = {}
    songs_by_difficulty: Dict[Tuple[str, int], Set[str]] = {}
    songs_by_bpm: Dict[Tuple[int, int], Set[str]] = {}
    songs_by_notes: Dict[int, Set[str]] = {}
    app_db_connection = sqlite3.connect(CONSTANTS.APP_DB)
    db_cursor = app_db_connection.cursor()
    result = db_cursor.execute(query)
    for row in result.fetchall():
        textage_id = row[0]
        notes = row[3]
        cleaned_artist = row[6].strip()
        cleaned_title = row[7].strip()
        songs_by_title[cleaned_title] = textage_id
        bpm_tuple: Tuple[int, int] = (row[4], row[5])
        difficulty_tuple: Tuple[str, int] = (row[1], row[2])
        if cleaned_artist not in songs_by_artist:
            songs_by_artist[cleaned_artist] = set([])
        songs_by_artist[cleaned_artist].add(textage_id)
        if difficulty_tuple not in songs_by_difficulty:
            songs_by_difficulty[difficulty_tuple] = set([])
        songs_by_difficulty[difficulty_tuple].add(textage_id)
        if bpm_tuple not in songs_by_bpm:
            songs_by_bpm[bpm_tuple] = set([])
        if notes not in songs_by_notes:
            songs_by_notes[notes] = set([])
        songs_by_bpm[bpm_tuple].add(textage_id)
        songs_by_notes[notes].add(textage_id)
    return SongReference(
        by_artist=songs_by_artist,
        by_difficulty=songs_by_difficulty,
        by_title=songs_by_title,
        by_note_count=songs_by_notes,
        by_bpm=songs_by_bpm,
    )


def end_session(session_uuid: str) -> None:
    session_end_time_utc = datetime.now(timezone.utc)
    session_end_query = "update session set end_time_utc=? where session_uuid=?"
    user_db_connection = sqlite3.connect(CONSTANTS.USER_DB)
    db_cursor = user_db_connection.cursor()
    db_cursor.execute(session_end_query, (session_end_time_utc, session_uuid))
    user_db_connection.commit()


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


# TODO: future work for pngs
# def load_pngs(png_files: List[str]) -> List[Path]:
#    pngs: List[Path] = []
#    for filename in png_files:
#        absolute_location = Path(filename).absolute()
#        if absolute_location.exists():
#            pngs.append(absolute_location)
#    if pngs:
#        log.info(f"Reading image files from {pngs}")
#    return pngs


def startup() -> Tuple[List[Path], List[StatePixel], SongReference]:
    args = parse_arguments()
    sqlite_setup(args.force_update)
    state_pixels = read_state_pixels()
    song_reference = read_song_data_from_db()
    # TODO: future work for pngs
    # png_paths = load_pngs(args.png_files)
    png_paths: List[Path] = []
    return png_paths, state_pixels, song_reference


def main() -> None:
    png_paths, state_pixels, song_reference = startup()
    source_id = 0
    try:
        session_uuid = start_session()
        video_processing_loop(source_id, state_pixels, session_uuid, song_reference)
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
