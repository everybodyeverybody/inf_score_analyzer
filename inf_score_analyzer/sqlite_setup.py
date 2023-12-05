#!/usr/bin/env python3
import os
import logging
import sqlite3
from datetime import datetime
from dataclasses import asdict
from . import constants as CONSTANTS
from .download_textage_tables import get_infinitas_song_metadata

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
        "soflan integer,"
        "min_bpm integer,"
        "max_bpm integer,"
        "version_id integer)"
    )
    create_song_difficulty_table_query = (
        "create table if not exists song_difficulty_and_notes("
        "textage_id text,"
        "difficulty_id integer,"
        "level integer,"
        "notes integer)"
    )
    create_song_difficulty_index_query = (
        "create unique index if not exists song_difficulty_index "
        "on song_difficulty_and_notes(textage_id, difficulty_id)"
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
    app_db_connection = sqlite3.connect(CONSTANTS.APP_DB)
    db_cursor = app_db_connection.cursor()
    db_cursor.execute(create_song_table_query)
    db_cursor.execute(create_difficulty_table_query)
    db_cursor.execute(create_song_difficulty_table_query)
    db_cursor.execute(create_song_difficulty_index_query)
    db_cursor.execute(create_alternate_song_difficulty_table_query)


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
        "insert or replace into song_difficulty_and_notes "
        "(textage_id,difficulty_id,level,notes) values (?,?,?,?);"
    )
    for textage_id, song_data in song_metadata.items():
        song_insert_query = (
            "insert or replace into songs ( "
            "textage_id,"
            "title,"
            "artist,"
            "genre,"
            "soflan,"
            "min_bpm,"
            "max_bpm,"
            "version_id) values ("
            ":textage_id,"
            ":title,"
            ":artist,"
            ":genre,"
            ":soflan,"
            ":min_bpm,"
            ":max_bpm,"
            "0"
            ");"
        )
        app_db_cursor.execute(song_insert_query, asdict(song_data))
        for difficulty in song_data.difficulty_and_notes.keys():
            level = song_data.difficulty_and_notes[difficulty][0]
            notes = song_data.difficulty_and_notes[difficulty][1]
            app_db_cursor.execute(
                song_difficulty_insert_query,
                (song_data.textage_id, difficulty.value, level, notes),
            )
        app_db_connection.commit()
