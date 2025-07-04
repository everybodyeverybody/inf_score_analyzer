#!/usr/bin/env python3
import io
import os
import uuid
import logging
import sqlite3
from pathlib import Path
from datetime import datetime, date, timezone

import numpy  # type: ignore
from numpy.typing import NDArray  # type: ignore

from . import constants as CONSTANTS
from .download_textage_tables import get_infinitas_song_metadata
from .kamaitachi_client import (
    download_kamaitachi_song_list,
    normalize_textage_to_kamaitachi,
)
from .song_reference import SongReference
from .local_dataclasses import Score, OCRSongTitles, Difficulty

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
    add_total_score_to_score_table = (
        "alter table score add column total_score integer default 0"
    )
    add_miss_count_to_score_table = (
        "alter table score add column miss_count integer default 0;"
    )
    user_db_connection = sqlite3.connect(CONSTANTS.USER_DB)
    db_cursor = user_db_connection.cursor()
    db_cursor.execute(create_session_table_query)
    db_cursor.execute(create_score_table_query)
    db_cursor.execute(create_score_time_series_query)
    db_cursor.execute(create_score_ocr_query)
    if not check_table_schema_for_column(CONSTANTS.USER_DB, "score", "total_score"):
        db_cursor.execute(add_total_score_to_score_table)
    if not check_table_schema_for_column(CONSTANTS.USER_DB, "score", "miss_count"):
        db_cursor.execute(add_miss_count_to_score_table)
    return


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
    populate_alternate_difficulty_query = (
        "insert or replace into alternate_difficulty_table("
        "difficulty_table_id,"
        "difficulty_table_url) "
        "values (?,?)"
    )
    app_db_connection = sqlite3.connect(CONSTANTS.APP_DB)
    db_cursor = app_db_connection.cursor()
    db_cursor.execute(populate_difficulty_query)
    db_cursor.execute(
        populate_alternate_difficulty_query,
        (CONSTANTS.COMMUNITY_RANK_TABLE_ID, CONSTANTS.COMMUNITY_RANK_TABLE_URL),
    )
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
    create_alternate_difficulty_table_query = (
        "create table if not exists alternate_difficulty_table("
        "difficulty_table_id text,"
        "difficulty_table_url text)"
    )
    create_alternate_difficulty_table_index_query = (
        "create unique index if not exists alternate_difficulty_table_index "
        "on alternate_difficulty_table(difficulty_table_id, difficulty_table_url)"
    )
    create_alternate_difficulty_table_songs_query = (
        "create table if not exists alternate_difficulty_table_songs("
        "difficulty_table_id text,"
        "textage_id text,"
        "difficulty_id integer,"
        "clear_type integer, "
        "alternate_difficulty text,"
        "alternate_level text)"
    )
    create_alternate_difficulty_table_songs_index_query = (
        "create unique index if not exists alternate_difficulty_table_songs_index "
        "on alternate_difficulty_table_songs "
        "( difficulty_table_id, textage_id, difficulty_id, clear_type)"
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
    db_cursor.execute(create_alternate_difficulty_table_query)
    db_cursor.execute(create_alternate_difficulty_table_index_query)
    db_cursor.execute(create_alternate_difficulty_table_songs_query)
    db_cursor.execute(create_alternate_difficulty_table_songs_index_query)
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
        "sd.max_bpm, s.artist,s.title, s.genre "
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
    songs_by_difficulty_and_notes: dict[tuple[str, int, int], set[str]] = {}
    songs_by_genre: dict[str, set[str]] = {}
    app_db_connection = sqlite3.connect(CONSTANTS.APP_DB)
    db_cursor = app_db_connection.cursor()
    result = db_cursor.execute(query)
    for row in result.fetchall():
        textage_id = row[0]
        notes = row[3]
        cleaned_artist = row[6].strip()
        cleaned_title = row[7].strip()
        cleaned_genre = row[8].strip()
        songs_by_title[cleaned_title] = textage_id
        bpm_tuple: tuple[int, int] = (row[4], row[5])
        difficulty_tuple: tuple[str, int] = (row[1], row[2])
        difficulty_and_notes_tuple: tuple[str, int, int] = (row[1], row[2], notes)
        if cleaned_artist not in songs_by_artist:
            songs_by_artist[cleaned_artist] = set([])
        songs_by_artist[cleaned_artist].add(textage_id)
        if difficulty_tuple not in songs_by_difficulty:
            songs_by_difficulty[difficulty_tuple] = set([])
        songs_by_difficulty[difficulty_tuple].add(textage_id)
        if bpm_tuple not in songs_by_bpm:
            songs_by_bpm[bpm_tuple] = set([])
        if difficulty_and_notes_tuple not in songs_by_difficulty_and_notes:
            songs_by_difficulty_and_notes[difficulty_and_notes_tuple] = set([])
        if notes not in songs_by_notes:
            songs_by_notes[notes] = set([])
        if cleaned_genre not in songs_by_genre:
            songs_by_genre[cleaned_genre] = set([])
        songs_by_genre[cleaned_genre].add(textage_id)
        songs_by_difficulty_and_notes[difficulty_and_notes_tuple].add(textage_id)
        songs_by_bpm[bpm_tuple].add(textage_id)
        songs_by_notes[notes].add(textage_id)
    return SongReference(
        by_artist=songs_by_artist,
        by_difficulty=songs_by_difficulty,
        by_title=songs_by_title,
        by_note_count=songs_by_notes,
        by_bpm=songs_by_bpm,
        by_difficulty_and_notes=songs_by_difficulty_and_notes,
        by_genre=songs_by_genre,
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


def check_table_schema_for_column(db: Path, table_name: str, column: str) -> bool:
    query = f"PRAGMA table_info({table_name})"
    user_db_connection = sqlite3.connect(db)
    db_cursor = user_db_connection.cursor()
    results = [column[1] for column in db_cursor.execute(query).fetchall()]
    return column in results


def write_score(
    session_uuid: str,
    textage_id: str,
    score: Score,
    difficulty: Difficulty,
    ocr_titles: OCRSongTitles,
    score_frame: NDArray,
) -> None:
    difficulty_id = difficulty.value
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
        ":end_time_utc,"
        ":total_score,"
        ":miss_count"
        ")"
    )
    user_db_connection = sqlite3.connect(CONSTANTS.USER_DB)
    db_cursor = user_db_connection.cursor()
    artist, title = get_artist_and_title_by_textage_id(textage_id)
    log.info(
        f"Provided score for Artist: {artist} Title: {title} Difficulty: {difficulty.name}"
    )
    log.info(f"Writing to sqlite: {textage_id} {difficulty} {score}")
    return
    db_cursor.execute(
        score_query,
        {
            "score_uuid": score_uuid,
            "session_uuid": session_uuid,
            "textage_id": textage_id,
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
            "total_score": score.total_score,
            "miss_count": score.miss_count,
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
            "en_title_ocr": ocr_titles.en_title,
            "en_artist_ocr": ocr_titles.en_artist,
            "jp_title_ocr": ocr_titles.jp_title,
            "jp_artist_ocr": ocr_titles.jp_artist,
        },
    )
    user_db_connection.commit()
    return None


def read_notes(textage_id: str, difficulty_id: int) -> int:
    query = (
        "select sdm.notes "
        "from song_difficulty_metadata sdm "
        "join songs songs on sdm.textage_id = songs.textage_id "
        f"where songs.textage_id = '{textage_id}' "
        f"and sdm.difficulty_id = {difficulty_id} "
    )
    app_db_connection = sqlite3.connect(CONSTANTS.APP_DB)
    db_cursor = app_db_connection.cursor()
    results = db_cursor.execute(query).fetchall()
    return results[0][0]


def read_tiebreak_data(metadata_titles: set[str]) -> list[tuple[str, str, str, str]]:
    app_db_connection = sqlite3.connect(CONSTANTS.APP_DB)
    db_cursor = app_db_connection.cursor()
    ids_as_string = ",".join([f"'{id}'" for id in metadata_titles])
    query = (
        "select textage_id, artist, title, genre "
        "from songs "
        f"where textage_id in ({ids_as_string})"
    )
    results = db_cursor.execute(query).fetchall()
    return results


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
        "third_party_song_ids.third_party_id kamaitachi_id, "
        "score.total_score total_score, "
        "score.miss_count miss_count "
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


def add_alternate_difficulty_table(table_entries: list[tuple]) -> None:
    app_db_connection = sqlite3.connect(CONSTANTS.APP_DB)
    app_db_cursor = app_db_connection.cursor()
    query = (
        "insert or replace into alternate_difficulty_table_songs("
        "difficulty_table_id,"
        "textage_id,"
        "difficulty_id,"
        "clear_type, "
        "alternate_difficulty,"
        "alternate_level) values "
        "(?,?,?,?,?,?)"
    )
    for entry in table_entries:
        app_db_cursor.execute(query, entry)
    app_db_connection.commit()


def get_artist_and_title_by_textage_id(textage_id: str) -> tuple[str, str]:
    app_db_connection = sqlite3.connect(CONSTANTS.APP_DB)
    app_db_cursor = app_db_connection.cursor()
    query = f"select artist, title from songs where textage_id='{textage_id}';"
    results = app_db_cursor.execute(query)
    return results.fetchone()
