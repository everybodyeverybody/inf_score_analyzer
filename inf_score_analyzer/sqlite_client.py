#!/usr/bin/env python3
import io
import os
import uuid
import logging
import sqlite3
from datetime import datetime, date, timezone

import numpy
from numpy.typing import NDArray
import polyleven  # type: ignore

from . import constants as CONSTANTS
from .download_textage_tables import get_infinitas_song_metadata
from .kamaitachi_client import (
    download_kamaitachi_song_list,
    normalize_textage_to_kamaitachi,
)
from .local_dataclasses import Score, OCRSongTitles, SongReference, Difficulty

log = logging.getLogger(__name__)


def adapt_date_iso(date_value: date) -> str:
    """Adapt datetime.date to ISO 8601 date."""
    return date_value.isoformat()


def adapt_datetime_iso(datetime_value: datetime) -> str:
    """Adapt datetime.datetime to timezone-naive ISO 8601 date."""
    return datetime_value.isoformat()


def convert_date(val: bytes) -> date:
    """Convert ISO 8601 date to datetime.date object."""
    return date.fromisoformat(val.decode())


def convert_datetime(val: bytes) -> datetime:
    """Convert ISO 8601 datetime to datetime.datetime object."""
    return datetime.fromisoformat(val.decode())


def register_date_adapters() -> None:
    sqlite3.register_adapter(date, adapt_date_iso)
    sqlite3.register_adapter(datetime, adapt_datetime_iso)
    sqlite3.register_converter("date", convert_date)
    sqlite3.register_converter("datetime", convert_datetime)


def create_user_database():
    create_session_table_query = (
        "create table if not exists session("
        "session_uuid text primary key,"
        "start_time_utc text,"
        "end_time_utc text)"
    )
    create_score_table_query = (
        "create table if not exists score("
        "score_uuid text primary key,"
        "session_uuid text,"
        "textage_id text,"
        "difficulty_id integer,"
        "perfect_great integer,"
        "great integer,"
        "good integer,"
        "bad integer,"
        "poor integer,"
        "fast integer,"
        "slow integer,"
        "combo_break integer,"
        "grade text,"
        "clear_type text,"
        "failure_measure integer,"
        "failure_note integer,"
        "end_time_utc text)"
    )
    create_score_time_series_query = (
        "create table if not exists score_time_series("
        "score_uuid text primary key,"
        "time_utc text,"
        "perfect_great integer,"
        "great integer,"
        "good integer,"
        "bad integer,"
        "poor integer,"
        "fast integer,"
        "slow integer,"
        "combo_break integer)"
    )
    create_score_ocr_query = (
        "create table if not exists score_ocr("
        "score_uuid text primary key,"
        "result_screengrab blob,"
        "title_scaled blob,"
        "en_title_ocr text,"
        "en_artist_ocr text,"
        "jp_title_ocr text,"
        "jp_artist_ocr text)"
    )
    user_db_connection = sqlite3.connect(CONSTANTS.USER_DB)
    db_cursor = user_db_connection.cursor()
    db_cursor.execute(create_session_table_query)
    db_cursor.execute(create_score_table_query)
    db_cursor.execute(create_score_time_series_query)
    db_cursor.execute(create_score_ocr_query)


def populate_app_database():
    # TODO: have these generate from the class enums
    # These are the identifiers from textage
    populate_difficulty_query = (
        "insert or ignore into difficulty (difficulty_id,difficulty) values "
        "(2,'SP_NORMAL'),"
        "(3,'SP_HYPER'),"
        "(4,'SP_ANOTHER'),"
        "(5,'SP_LEGGENDARIA'),"
        "(7,'DP_NORMAL'),"
        "(8,'DP_HYPER'),"
        "(9,'DP_ANOTHER'),"
        "(10,'DP_LEGGENDARIA'),"
        "(99,'UNKNOWN')"
    )
    app_db_connection = sqlite3.connect(CONSTANTS.APP_DB)
    db_cursor = app_db_connection.cursor()
    db_cursor.execute(populate_difficulty_query)
    app_db_connection.commit()


def create_app_database():
    create_song_table_query = (
        "create table if not exists songs("
        "textage_id text primary key,"
        "title text,"
        "artist text,"
        "genre text,"
        "textage_version_id integer,"
        "version text)"
    )
    create_song_difficulty_table_query = (
        "create table if not exists song_difficulty_metadata("
        "textage_id text,"
        "difficulty_id integer,"
        "level integer,"
        "notes integer,"
        "soflan integer,"
        "min_bpm integer,"
        "max_bpm integer)"
    )
    create_song_difficulty_index_query = (
        "create unique index if not exists song_difficulty_index "
        "on song_difficulty_metadata(textage_id, difficulty_id)"
    )
    create_difficulty_table_query = (
        "create table if not exists difficulty("
        "difficulty_id integer primary key,"
        "difficulty text)"
    )
    create_alternate_song_difficulty_table_query = (
        "create table if not exists alternate_song_difficulty("
        "textage_id text,"
        "difficulty_id integer,"
        "alternate_difficulty text,"
        "alternate_level text)"
    )
    create_third_party_id_table = (
        "create table if not exists third_party_song_ids("
        "textage_id text,"
        "third_party_name text,"
        "third_party_id text)"
    )
    create_third_party_id_table_index = (
        "create unique index if not exists third_party_id_index "
        "on third_party_song_ids(textage_id, third_party_name, third_party_id)"
    )
    app_db_connection = sqlite3.connect(CONSTANTS.APP_DB)
    db_cursor = app_db_connection.cursor()
    db_cursor.execute(create_song_table_query)
    db_cursor.execute(create_difficulty_table_query)
    db_cursor.execute(create_song_difficulty_table_query)
    db_cursor.execute(create_song_difficulty_index_query)
    db_cursor.execute(create_alternate_song_difficulty_table_query)
    db_cursor.execute(create_third_party_id_table)
    db_cursor.execute(create_third_party_id_table_index)


def should_update_app_db() -> bool:
    if not os.path.exists(CONSTANTS.APP_DB):
        return True
    mtime = int(os.path.getmtime(CONSTANTS.APP_DB))
    time_difference = datetime.now() - datetime.fromtimestamp(mtime)
    log.debug(
        f"app time diff: {int(time_difference.total_seconds())} > {CONSTANTS.MIN_APP_AGE_UPDATE_SECONDS}"
    )
    return int(time_difference.total_seconds()) >= CONSTANTS.MIN_APP_AGE_UPDATE_SECONDS


def sqlite_setup(force_update: bool = False) -> None:
    register_date_adapters()
    should_update_app_db()
    log.info("creating/refreshing user db")
    create_user_database()
    if force_update or should_update_app_db():
        log.info("creating/refreshing app db")
        create_app_database()
        log.info("populating app db constants")
        populate_app_database()
        log.info("loading textage data into db")
        populate_song_metadata_into_db()


def populate_song_metadata_into_db():
    song_metadata = get_infinitas_song_metadata()
    app_db_connection = sqlite3.connect(CONSTANTS.APP_DB)
    app_db_cursor = app_db_connection.cursor()
    song_difficulty_insert_query = (
        "insert or replace into song_difficulty_metadata ("
        "textage_id, "
        "difficulty_id, "
        "level, "
        "notes, "
        "soflan, "
        "min_bpm, "
        "max_bpm"
        ") values (?,?,?,?,?,?,?)"
    )
    song_insert_query = (
        "insert or replace into songs ( "
        "textage_id,"
        "title,"
        "artist,"
        "genre,"
        "textage_version_id, "
        "version"
        ") values (?,?,?,?,?,?)"
    )
    kamaitachi_third_party_insert_query = (
        "insert or replace into third_party_song_ids ("
        "textage_id, third_party_name, third_party_id"
        ") values (?,?,?)"
    )
    for textage_id, song in song_metadata.items():
        app_db_cursor.execute(
            song_insert_query,
            (
                song.textage_id,
                song.title,
                song.artist,
                song.genre,
                song.textage_version_id,
                song.version,
            ),
        )
        for difficulty in song.difficulty_metadata.keys():
            metadata = song.difficulty_metadata[difficulty]
            app_db_cursor.execute(
                song_difficulty_insert_query,
                (
                    song.textage_id,
                    difficulty.value,
                    metadata.level,
                    metadata.notes,
                    metadata.soflan,
                    metadata.min_bpm,
                    metadata.max_bpm,
                ),
            )
        app_db_connection.commit()
    song_reference = read_song_data_from_db()
    mapping = normalize_textage_to_kamaitachi(
        song_reference, download_kamaitachi_song_list()
    )
    for textage_id, kt_id in mapping.items():
        app_db_cursor.execute(
            kamaitachi_third_party_insert_query, (textage_id, "kamaitachi", kt_id)
        )
    app_db_connection.commit()


def read_song_data_from_db() -> SongReference:
    log.info(f"Loading in song info from {CONSTANTS.APP_DB}")
    query = (
        "select s.textage_id,d.difficulty,sd.level,sd.notes,sd.min_bpm, "
        "sd.max_bpm, s.artist,s.title "
        "from songs s "
        "join song_difficulty_metadata sd "
        "on sd.textage_id=s.textage_id "
        "join difficulty d on d.difficulty_id=sd.difficulty_id "
        "where sd.level!=0 order by sd.textage_id,sd.level"
    )
    songs_by_title: dict[str, str] = {}
    songs_by_artist: dict[str, set[str]] = {}
    songs_by_difficulty: dict[tuple[str, int], set[str]] = {}
    songs_by_bpm: dict[tuple[int, int], set[str]] = {}
    songs_by_notes: dict[int, set[str]] = {}
    app_db_connection = sqlite3.connect(CONSTANTS.APP_DB)
    db_cursor = app_db_connection.cursor()
    result = db_cursor.execute(query)
    for row in result.fetchall():
        textage_id = row[0]
        notes = row[3]
        cleaned_artist = row[6].strip()
        cleaned_title = row[7].strip()
        songs_by_title[cleaned_title] = textage_id
        bpm_tuple: tuple[int, int] = (row[4], row[5])
        difficulty_tuple: tuple[str, int] = (row[1], row[2])
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


def write_session_start(session_start_time_utc: datetime, session_uuid: str) -> None:
    session_query = "insert into session values (?,?,?)"
    user_db_connection = sqlite3.connect(CONSTANTS.USER_DB)
    db_cursor = user_db_connection.cursor()
    db_cursor.execute(session_query, (session_uuid, session_start_time_utc, None))
    user_db_connection.commit()
    return None


def write_session_end(session_uuid: str) -> None:
    session_end_time_utc = datetime.now(timezone.utc)
    session_end_query = "update session set end_time_utc=? where session_uuid=?"
    user_db_connection = sqlite3.connect(CONSTANTS.USER_DB)
    db_cursor = user_db_connection.cursor()
    db_cursor.execute(session_end_query, (session_end_time_utc, session_uuid))
    user_db_connection.commit()
    return None


def write_score(
    session_uuid: str,
    title: OCRSongTitles,
    score: Score,
    difficulty: str,
    score_frame: NDArray,
    song_reference: SongReference,
    level: int,
    metadata_title: set[str],
) -> None:
    referenced_textage_id = None
    # TODO: extract this somewhere else
    resolved_song_info = song_reference.resolve_ocr(title, difficulty, level)
    if resolved_song_info is not None:
        referenced_textage_id = resolved_song_info
    else:
        if len(metadata_title) == 1:
            referenced_textage_id = next(iter(metadata_title))
            log.info(f"Using metadata title: {referenced_textage_id}")
        else:
            log.warning(f"Found too much metadata, {metadata_title}, tiebreaking")
            referenced_textage_id = metadata_lookup_tiebreaker(metadata_title, title)
            log.warning(f"Tiebreaker found: {referenced_textage_id}")
    difficulty_id = Difficulty[difficulty].value
    score_uuid = str(uuid.uuid4())
    end_time_utc = datetime.now(timezone.utc)

    score_frame_bytes = io.BytesIO()
    numpy.savez(score_frame_bytes, frame_slice=score_frame)
    score_frame_bytes.seek(0)

    score_query = (
        "insert into score values ("
        ":score_uuid,"
        ":session_uuid,"
        ":textage_id,"
        ":difficulty_id,"
        ":perfect_great,"
        ":great,"
        ":good,"
        ":bad,"
        ":poor,"
        ":fast,"
        ":slow,"
        ":combo_break,"
        ":grade,"
        ":clear_type,"
        ":failure_measure,"
        ":failure_note,"
        ":end_time_utc"
        ")"
    )
    user_db_connection = sqlite3.connect(CONSTANTS.USER_DB)
    db_cursor = user_db_connection.cursor()
    log.info("TRYING SQLITE WRITE")
    db_cursor.execute(
        score_query,
        {
            "score_uuid": score_uuid,
            "session_uuid": session_uuid,
            "textage_id": referenced_textage_id,
            "difficulty_id": difficulty_id,
            "perfect_great": score.fgreat,
            "great": score.great,
            "good": score.good,
            "bad": score.bad,
            "poor": score.poor,
            "fast": score.fast,
            "slow": score.slow,
            "combo_break": None,
            "grade": score.grade,
            "clear_type": score.clear_type,
            "failure_measure": None,
            "failure_note": None,
            "end_time_utc": end_time_utc,
        },
    )
    ocr_query = (
        "insert into score_ocr "
        "values (:score_uuid, :result_screengrab, :title_scaled,"
        ":en_title_ocr, :en_artist_ocr, :jp_title_ocr, :jp_artist_ocr)"
    )
    db_cursor.execute(
        ocr_query,
        {
            "score_uuid": score_uuid,
            "result_screengrab": score_frame_bytes.getvalue(),
            "title_scaled": None,
            "en_title_ocr": title.en_title,
            "en_artist_ocr": title.en_artist,
            "jp_title_ocr": title.jp_title,
            "jp_artist_ocr": title.jp_artist,
        },
    )
    user_db_connection.commit()
    return None


def read_tiebreak_data(metadata_titles: set[str]) -> list[tuple[str, str, str]]:
    app_db_connection = sqlite3.connect(CONSTANTS.APP_DB)
    db_cursor = app_db_connection.cursor()
    ids_as_string = ",".join([f"'{id}'" for id in metadata_titles])
    query = (
        "select textage_id, artist, title "
        "from songs "
        f"where textage_id in ({ids_as_string})"
    )
    results = db_cursor.execute(query).fetchall()
    return results


def metadata_lookup_tiebreaker(
    metadata_titles: set[str], ocr_titles: OCRSongTitles
) -> str:
    """
    Calculates the levenshtein distance on songs that match
    play metadata (note count, difficulty, bpm) versus
    what is provided by our OCR library to determine
    the song title.

    In cases of ties, this raises an exception, indicating
    we have missed some special case or overlap, or that
    OCR is underperforming or outputting garbage.

    https://en.wikipedia.org/wiki/Levenshtein_distance
    """
    lowest_score = -1
    lowest_textage_id = None
    lowest_has_tie = False
    results = read_tiebreak_data(metadata_titles)
    scores = {}
    for textage_id, artist, title in results:
        score = polyleven.levenshtein(ocr_titles.en_artist, artist)
        score += polyleven.levenshtein(ocr_titles.en_title, title)
        score += polyleven.levenshtein(ocr_titles.jp_artist, artist)
        score += polyleven.levenshtein(ocr_titles.jp_title, title)
        scores[textage_id] = score
    # We only care about ties for the lowest score
    # so we sort to get the elements in ascending score order
    sorted_scores = {t: scores[t] for t in sorted(scores, key=scores.get)}  # type: ignore
    for textage_id, score in sorted_scores.items():
        if lowest_score != -1 and score == lowest_score:
            lowest_has_tie = True
        if lowest_score == -1 or score < lowest_score:
            lowest_textage_id = textage_id
            lowest_score = score
    if lowest_has_tie or lowest_textage_id is None:
        raise RuntimeError(
            "Couldn't figure out song title from OCR data and metadata. "
            f"song metadata: {metadata_titles} "
            f"ocr data: {ocr_titles} "
            f"similarity scores: {sorted_scores} "
        )
    return lowest_textage_id


def get_scores_by_session(session_id: str) -> list[tuple]:
    double_db = "attach ? AS user;"
    query = (
        "select session.session_uuid session_uuid, "
        "score.perfect_great pgreat,"
        "score.great great,"
        "score.good good,"
        "score.bad bad,"
        "score.poor poor,"
        "score.fast fast,"
        "score.slow slow,"
        "score.clear_type clear_type, "
        "score.end_time_utc score_time, "
        "difficulty.difficulty difficulty, "
        "songs.title title, "
        "third_party_song_ids.third_party_id kamaitachi_id "
        "from user.session session "
        "join user.score score on score.session_uuid=session.session_uuid "
        "join songs songs on songs.textage_id=score.textage_id "
        "join difficulty on difficulty.difficulty_id=score.difficulty_id "
        "join third_party_song_ids on third_party_song_ids.textage_id=songs.textage_id and third_party_song_ids.third_party_name='kamaitachi' "
        "where session.session_uuid=? and clear_type!='';"
    )
    app_db_connection = sqlite3.connect(CONSTANTS.APP_DB)
    db_cursor = app_db_connection.cursor()
    _ = db_cursor.execute(double_db, (str(CONSTANTS.USER_DB),))
    results = db_cursor.execute(query, (session_id,))
    return [result for result in results]
