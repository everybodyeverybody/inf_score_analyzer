#!/usr/bin/env python3
import csv
import logging
import dataclasses
from pathlib import Path
from typing import Any

from .song_reference import SongReference
from .local_dataclasses import (
    ImportCsvType,
    Score,
    ClearType,
    Difficulty,
    ScoreDBRecord,
    calculate_grade_from_total_score,
)
from . import sqlite_client

log = logging.getLogger(__name__)


def determine_csv_type(csv_data: list[list[str]]) -> ImportCsvType:
    INF_SCORE_MINIMUM_HEADERS = frozenset(
        ["title", "difficulty", "clear_type", "total_score"]
    )
    header = set([column.lower() for column in csv_data[0]])
    if INF_SCORE_MINIMUM_HEADERS.issubset(header):
        return ImportCsvType.INF_SCORE_ANALYZER
    raise RuntimeError(
        "Could not determine the csv type (inf_score, other services not yet made)"
    )


def read_inf_score_csv_format(
    session_uuid: str, csv_data: list[list[Any]], song_reference: SongReference
) -> list[ScoreDBRecord]:
    def __sort(key_value_tuple):
        return key_value_tuple[1]

    score_fields = set([field.name for field in dataclasses.fields(Score)])
    valid_header_positions = {field: None for field in score_fields}
    valid_header_positions.update({"title": None, "difficulty": None})
    score_records: list[ScoreDBRecord] = []
    csv_column_names = []
    for row_index, row in enumerate(csv_data):
        line_number = row_index + 1
        if row_index == 0:
            for column_index, column in enumerate(row):
                if column in valid_header_positions:
                    valid_header_positions[column] = column_index  # type: ignore
            csv_column_names = [
                c
                for c, i in sorted(
                    [
                        (key, value)
                        for key, value in valid_header_positions.items()
                        if value is not None
                    ],
                    key=__sort,
                )
            ]
        else:
            textage_id = None
            score = Score()
            difficulty = Difficulty.UNKNOWN
            for column_index, column in enumerate(row):
                column_name = csv_column_names[column_index]
                if column_name in score_fields:
                    if column_name == "clear_type":
                        try:
                            _ = ClearType[column]
                        except KeyError as e:
                            raise RuntimeError(
                                f"Could not read clear_type {column} on line {line_number} from csv: {e}"
                            )
                    update: dict[str, Any] = {
                        csv_column_names[column_index]: row[column_index]
                    }
                    score = dataclasses.replace(score, **update)
                elif column_name == "difficulty":
                    try:
                        difficulty = Difficulty[column]
                    except KeyError as e:
                        raise RuntimeError(
                            f"Could not read difficulty {column} on line {line_number} from csv: {e}"
                        )
                elif column_name == "title":
                    if column not in song_reference.by_title:
                        raise RuntimeError(
                            f"Could not find {column} in song reference on line {line_number}"
                        )
                    textage_id = song_reference.by_title[column]
            if textage_id and difficulty and score.grade == "X":
                notes = sqlite_client.read_notes(textage_id, difficulty.value)
                score.grade = calculate_grade_from_total_score(score.total_score, notes)
            if textage_id and score and difficulty:
                db_record = ScoreDBRecord(
                    session_uuid=session_uuid,
                    textage_id=textage_id,
                    score=score,
                    difficulty=difficulty,
                )
                score_records.append(db_record)
            else:
                log.error(f"Failed to read line {line_number} of csv, skipping")
    return score_records


def validate_data(
    session_uuid: str, csv_data: list[list[str]], song_reference: SongReference
) -> list[ScoreDBRecord]:
    match determine_csv_type(csv_data):
        case ImportCsvType.INF_SCORE_ANALYZER:
            return read_inf_score_csv_format(session_uuid, csv_data, song_reference)


def read_csv(csv_file: Path) -> list[list[str]]:
    with open(csv_file, "rt") as reader:
        csv_reader = csv.reader(reader)
        return [row for row in csv_reader]


def import_scores_from_csv(
    session_uuid: str, csv_file: Path, song_reference: SongReference
):
    data = read_csv(csv_file)
    valid_data = validate_data(session_uuid, data, song_reference)
    for entry in valid_data:
        sqlite_client.write_score_from_record(entry)
