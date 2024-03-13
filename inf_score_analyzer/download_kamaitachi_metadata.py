#!/usr/bin/env python3
import re
import logging
import requests
from pathlib import Path
from typing import Dict, Any
from . import constants as CONSTANTS
from .local_dataclasses import SongReference

log = logging.getLogger(__name__)


def download_kamaitachi_song_list() -> dict:
    log.info("Downloading kamaitachi song list")
    kamaitachi_json_file = CONSTANTS.DATA_DIR / Path("kamaitachi-iidx-songs.json")
    with open(kamaitachi_json_file, "wt") as json_writer:
        song_list_json_response = requests.get(CONSTANTS.KAMAITACHI_SONG_LIST_URL)
        if song_list_json_response.status_code == 200:
            json_writer.write(song_list_json_response.text)
            return song_list_json_response.json()
        else:
            raise RuntimeError(
                f"could not download kamaitachi source from {CONSTANTS.KAMAITACHI_SONG_LIST_URL} "
                f"code: {song_list_json_response.status_code} error: {song_list_json_response.text}"
            )


def normalize_textage_to_kamaitachi(
    song_reference: SongReference, kamaitachi_song_list: Dict[str, Any]
) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    # These are cases where a single regex can't fix the titles to
    # match what is found in the kamaitachi data, likely due to spacing
    # or the round trip from shiftjis to ascii to utf8 not maintaining
    # perfect accuracy on text code points.
    #
    # kamaitachi does guarantee their ID ordering, so we can leave these
    # as constants. we could also feasibly index this by textage_id,
    # but this makes the parsing issues more obvious should
    # I figure out a better algorithm to do this kind of fuzzy text matching
    # across different encodings.
    special_cases: Dict[str, str] = {
        # fullwidth asterisk is very unique character
        "ハイ＊ビスカス ft. Kanae Asaba": "1737",
        # spacing and full width stuff
        "炸裂！イェーガー電光チョップ!! (JAEGER FINAL ATTACK)": "1467",
        # quotes
        'ピアノ協奏曲第１番"蠍火"': "471",
        # the tildes aren't exact matches
        "A MINSTREL 〜 ver.short-scape 〜": "1033",
        # accented characters not in kamaitachi db
        "L'amour et la liberté": "197",
        # ... gets shortened to … in many jp imes
        "Leaving…": "583",
        # kamaitachi uses full width ・・・ here
        "LOVE WILL…": "111",
        # kamaitachi's is something unique vim cant display
        "POLꓘAMAИIA": "1964",
        # spacing, black heart conversion
        "Raspberry♥Heart (English version)": "499",
        # the schwa is not an exact codepoint match
        "uәn": "2271",
    }

    kamaitachi_titles = {}
    kamaitachi_alt_titles = {}
    kamaitachi_titles_no_spaces_lowercase = {}
    kamaitachi_alt_no_spaces = {}
    log.info("Building kamaitachi matching tables for textage data")
    for entry in kamaitachi_song_list:
        title = entry["title"]
        title_no_spaces_lowercase = re.sub(r"\s+", "", title).lower()
        kamaitachi_titles[title] = entry["id"]
        kamaitachi_titles_no_spaces_lowercase[title_no_spaces_lowercase] = entry["id"]
        if len(entry["altTitles"]) > 0:
            for alt in entry["altTitles"]:
                kamaitachi_alt_titles[alt] = entry["id"]
                alt_no_spaces = re.sub(r"\s+", "", alt).lower()
                kamaitachi_alt_no_spaces[alt_no_spaces] = entry["id"]

    log.info("Normalizing kamaitachi song data to textage song data for infinitas")
    for entry in song_reference.by_title.keys():
        textage_id = song_reference.by_title[entry]
        entry_no_spaces_lowercase = re.sub(r"\s+", "", entry).lower()
        entry_clear_hearts = re.sub("♥", "♡", entry)
        entry_full_width_punctuation = re.sub(r"\?", "？", entry)
        entry_full_width_punctuation = re.sub("!", "！", entry_full_width_punctuation)
        entry_full_width_punctuation = re.sub("･", "・", entry_full_width_punctuation)

        entry_half_width_punctuation = re.sub("？", "?", entry)
        entry_half_width_punctuation = re.sub("！", "!", entry_half_width_punctuation)
        entry_half_width_punctuation = re.sub("・", "･", entry_half_width_punctuation)

        entry_full_width_punctuation_no_spaces = re.sub(
            r"\s+", "", entry_full_width_punctuation
        )
        if entry in kamaitachi_titles:
            mapping[textage_id] = kamaitachi_titles[entry]
            continue
        if entry_clear_hearts in kamaitachi_titles:
            mapping[textage_id] = kamaitachi_titles[entry_clear_hearts]
            continue
        if entry_full_width_punctuation in kamaitachi_titles:
            mapping[textage_id] = kamaitachi_titles[entry_full_width_punctuation]
            continue
        if (
            entry_full_width_punctuation_no_spaces
            in kamaitachi_titles_no_spaces_lowercase
        ):
            mapping[textage_id] = kamaitachi_titles_no_spaces_lowercase[
                entry_full_width_punctuation_no_spaces
            ]
            continue
        if entry_half_width_punctuation in kamaitachi_titles:
            mapping[textage_id] = kamaitachi_titles[entry_half_width_punctuation]
            continue
        if entry_no_spaces_lowercase in kamaitachi_titles_no_spaces_lowercase:
            mapping[textage_id] = kamaitachi_titles_no_spaces_lowercase[
                entry_no_spaces_lowercase
            ]
            continue
        if entry in kamaitachi_alt_titles:
            mapping[textage_id] = kamaitachi_alt_titles[entry]
            continue
        if entry_no_spaces_lowercase in kamaitachi_alt_no_spaces:
            mapping[textage_id] = kamaitachi_alt_no_spaces[entry_no_spaces_lowercase]
            continue
        if entry in special_cases:
            mapping[textage_id] = special_cases[entry]
            continue
        raise RuntimeError(
            f"Could not determine kamaitachi ID for textage infinitas song: {textage_id} {entry}"
        )
    log.info(f"Done normalizing data. Found {len(mapping)} matching songs.")
    return mapping
