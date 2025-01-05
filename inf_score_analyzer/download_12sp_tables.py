#!/usr/bin/env python3
import logging
import requests  # type: ignore

from . import constants as CONSTANTS
from . import sqlite_client
from .song_reference import SongReference
from .local_dataclasses import Difficulty, ClearType

log = logging.getLogger(__name__)


def write_table_to_sqlite(
    table: dict[tuple[str, Difficulty], dict[ClearType, str]],
    song_reference: SongReference,
) -> None:
    data_to_write: list[tuple] = []
    for entry in table.keys():
        if entry[0] not in song_reference.by_title:
            log.debug(
                f"Skipping writing 12SP for {entry[0]}, "
                "could not find in INFINITAS song reference"
            )
            continue

        for clear_type in table[entry].keys():
            label = table[entry][clear_type]
            row = tuple(
                [
                    CONSTANTS.COMMUNITY_RANK_TABLE_ID,
                    song_reference.by_title[entry[0]],
                    entry[1].value,
                    clear_type.value,
                    None,
                    label,
                ]
            )
            data_to_write.append(row)
    sqlite_client.add_alternate_difficulty_table(data_to_write)


def transform_table_json(
    table_json: list[dict],
) -> dict[tuple[str, Difficulty], dict[ClearType, str]]:
    difficulty_lookup_table = {
        "L": Difficulty.SP_LEGGENDARIA,
        "A": Difficulty.SP_ANOTHER,
        "H": Difficulty.SP_HYPER,
        "N": Difficulty.SP_NORMAL,
    }
    by_title_and_difficulty: dict[tuple[str, Difficulty], dict[ClearType, str]] = {}
    for entry in table_json:
        if "difficulty" not in entry:
            log.debug(f"Skipping 12SP {entry['name']}, missing difficulty.")
            continue
        if entry["normal"] == "":
            log.debug(f"Skipping 12SP {entry['name']}, missing normal ranking.")
            continue
        if entry["hard"] == "":
            log.debug(f"Skipping 12SP {entry['name']}, missing hard ranking.")
            continue
        song_difficulty = difficulty_lookup_table[entry["difficulty"]]
        name = entry["name"].strip()
        # I really don't want to depend on kamaitachi for everything
        # but also jesus why don't people use the same strings. Unicode
        # tildes and hearts are also a gigantic pain
        special_cases = {
            "キャトられ♥恋はモ～モク": "キャトられ♥恋はモ〜モク",
            "†渚の小悪魔ラヴリィ～レイディオ†(IIDX EDIT)": "†渚の小悪魔ラヴリィ〜レイディオ† (IIDX EDIT)",
            "カゴノトリ～弐式～": "カゴノトリ 〜弐式〜",
            "We're so Happy(P*Light Remix) IIDX ver.": "We're so Happy (P*Light Remix) IIDX ver.",
            "Timepiece phase II(CN Ver.)": "Timepiece phase II (CN Ver.)",
            "quell～the seventh slave～": "quell 〜the seventh slave〜",
            'ピアノ協奏曲第1番"蠍火"': 'ピアノ協奏曲第１番"蠍火"',
            "華爛漫-Flowers-": "華爛漫 -Flowers-",
            "旋律のドグマ～Misérables～": "旋律のドグマ 〜Misérables〜",
            "PARANOiA ～HADES～": "PARANOiA 〜HADES〜",
            "NEW GENERATION-もう、お前しか見えない-": "NEW GENERATION -もう、お前しか見えない-",
            "DEATH†ZIGOQ～怒りの高速爆走野郎～": "DEATH†ZIGOQ 〜怒りの高速爆走野郎〜",
            "Colors(radio edit)": "Colors (radio edit)",
            'Anisakis-somatic mutation type "Forza"-': 'Anisakis -somatic mutation type "Forza"-',
        }
        if name in special_cases:
            name = special_cases[name]

        key: tuple[str, Difficulty] = (
            name,
            song_difficulty,
        )
        by_title_and_difficulty[key] = {
            ClearType.NORMAL: entry["normal"],
            ClearType.HARD: entry["hard"],
        }
    return by_title_and_difficulty


def get_12sp_table_json() -> list[dict]:
    table_response = requests.get(CONSTANTS.COMMUNITY_RANK_TABLE_URL)
    table_response.raise_for_status()
    return table_response.json()


def download_and_normalize_data(song_reference: SongReference):
    table_json = get_12sp_table_json()
    lookup_table = transform_table_json(table_json)
    write_table_to_sqlite(lookup_table, song_reference)
