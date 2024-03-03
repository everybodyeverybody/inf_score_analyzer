#!/usr/bin/env python3
import os
import logging
import sqlite3
from datetime import datetime
from dataclasses import asdict
from . import constants as CONSTANTS
from .download_textage_tables import get_infinitas_song_metadata
from .download_kamaitachi_metadata import (
    download_kamaitachi_song_list,
    normalize_textage_to_kamaitachi,
)
from .local_dataclasses import SongReference

log = logging.getLogger(__name__)


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
