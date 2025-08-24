#!/usr/bin/env python3
import re
import sys
import time
import logging
from typing import Any
from pathlib import Path
from copy import deepcopy
from datetime import datetime

import requests  # type: ignore

from . import sqlite_client
from . import constants as CONSTANTS
from .local_dataclasses import ClearType
from .song_reference import SongReference

log = logging.getLogger(__name__)


def submit_score_request(scores: dict[str, Any]) -> None:
    headers = {"Authorization": f"Bearer {CONSTANTS.TACHI_API_TOKEN}"}
    response = requests.post(CONSTANTS.KAMAITACHI_API_URL, headers=headers, json=scores)
    if response.status_code in [200, 202]:
        response_json = response.json()
        queue_url = response_json["body"]["url"]
        while True:
            queue_response = requests.get(queue_url, headers=headers)
            log.info(queue_response.status_code)
            log.info(queue_response.text)
            if queue_response.status_code not in [200, 202]:
                break
            status = queue_response.json()["body"]["importStatus"]
            if status == "completed":
                break
            time.sleep(5)
    else:
        log.error(
            f"Submit score request failed: {response.status_code} {response.text}"
        )
    return


def translate_clear_type_to_lamp(clear_type: str) -> str:
    kt_lamp = "FAILED"
    # TODO: stop being lazy
    clear_type_enum = ClearType[clear_type]
    if clear_type_enum == ClearType.NORMAL:
        kt_lamp = "CLEAR"
    elif clear_type_enum == ClearType.EXHARD:
        kt_lamp = "EX HARD CLEAR"
    elif clear_type_enum == ClearType.FULL_COMBO:
        kt_lamp = "FULL COMBO"
    elif clear_type_enum in [
        ClearType.ASSIST,
        ClearType.EASY,
        ClearType.HARD,
    ]:
        kt_lamp = f"{clear_type_enum.name} CLEAR"
    return kt_lamp


def build_score_entry(score: tuple) -> dict[str, Any]:
    base_score: dict[str, Any] = {
        "score": None,
        "lamp": None,
        "matchType": "tachiSongID",
        "identifier": None,
        "difficulty": None,
        "timeAchieved": None,
        "comment": None,
        "judgements": {},
        "optional": {},
    }
    clear_type = score[8]
    time = score[9]
    difficulty = score[10].split("_")[1]
    title = score[11]
    kt_id = score[12]
    total_score = score[13]
    miss_count = score[14]
    kt_lamp = translate_clear_type_to_lamp(clear_type)
    play_datetime = datetime.fromisoformat(time)
    kt_time_achieved_ms = int(play_datetime.timestamp() * 1000)
    base_score["comment"] = f"{title} {difficulty}"
    base_score["score"] = total_score
    base_score["lamp"] = kt_lamp
    base_score["identifier"] = kt_id
    base_score["difficulty"] = difficulty
    base_score["timeAchieved"] = kt_time_achieved_ms
    if sum(score[1:8]) != 0:
        pgreat, great, good, bad, poor, fast, slow = score[1:8]
        base_score["judgements"] = {
            "pgreat": pgreat,
            "great": great,
            "good": good,
            "bad": bad,
            "poor": poor,
        }
        base_score["optional"] = {"fast": fast, "slow": slow, "bp": miss_count}
    else:
        base_score["optional"] = {"bp": miss_count}
    return base_score


def transform_scores(scores: list[tuple]) -> tuple[dict[str, Any], ...]:
    base_meta = {"meta": {"game": "iidx", "service": "infinitas"}, "scores": []}
    sp_scores: dict[str, Any] = deepcopy(base_meta)
    sp_scores["meta"]["playtype"] = "SP"
    dp_scores: dict[str, Any] = deepcopy(base_meta)
    dp_scores["meta"]["playtype"] = "DP"
    # TODO: stop hobby programming when youve been programming all day
    for score in scores:
        single_or_double = score[10].split("_")[0]
        score_json = build_score_entry(score)
        if single_or_double == "SP":
            sp_scores["scores"].append(score_json)
        elif single_or_double == "DP":
            dp_scores["scores"].append(score_json)
        else:
            raise RuntimeError(f"bad difficulty: '{score[10]}'")
    return sp_scores, dp_scores


def export_to_kamaitachi(session_id: str) -> None:
    if not CONSTANTS.TACHI_API_TOKEN:
        log.error(
            "Kamaitachi export failed, must set TACHI_API_TOKEN in env for script"
        )
        return
    scores = sqlite_client.get_scores_by_session(session_id)
    sp_scores_json, dp_scores_json = transform_scores(scores)
    if len(sp_scores_json["scores"]) > 0:
        submit_score_request(sp_scores_json)
    if len(dp_scores_json["scores"]) > 0:
        submit_score_request(dp_scores_json)


def download_kamaitachi_song_list() -> dict[str, Any]:
    log.info("Downloading kamaitachi song list")
    kamaitachi_json_file = CONSTANTS.DATA_DIR / Path("kamaitachi-iidx-songs.json")
    with open(kamaitachi_json_file, "wt") as json_writer:
        song_list_json_response = requests.get(CONSTANTS.KAMAITACHI_SONG_LIST_URL)
        if song_list_json_response.status_code == 200:
            json_writer.write(song_list_json_response.text)
            return song_list_json_response.json()
        else:
            raise RuntimeError(
                f"could not download kamaitachi source from "
                "{CONSTANTS.KAMAITACHI_SONG_LIST_URL} "
                f"code: {song_list_json_response.status_code} "
                f"error: {song_list_json_response.text}"
            )


def normalize_textage_to_kamaitachi(
    song_reference: SongReference, kamaitachi_song_list: list[dict[str, Any]]
) -> dict[str, str]:
    mapping: dict[str, str] = {}
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
    special_cases: dict[str, str] = {
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
        # new unique character! need to fix the encoding here
        "ジオメトリック�塔eィーパーティー": "2352",
        # another new unique quoting here
        'ピアノ協奏曲第１番"蠍火" (BlackY Remix)': "1905",
        "≡＋≡": "2161",
        # equals and multiplier signs are different
        "恋愛=精度×認識力": "2252",
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
    for title in song_reference.by_title.keys():
        textage_id = song_reference.by_title[title]
        entry_no_spaces_lowercase = re.sub(r"\s+", "", title).lower()
        entry_clear_hearts = re.sub("♥", "♡", title)
        entry_full_width_punctuation = re.sub(r"\?", "？", title)
        entry_full_width_punctuation = re.sub("!", "！", entry_full_width_punctuation)
        entry_full_width_punctuation = re.sub("･", "・", entry_full_width_punctuation)

        entry_half_width_punctuation = re.sub("？", "?", title)
        entry_half_width_punctuation = re.sub("！", "!", entry_half_width_punctuation)
        entry_half_width_punctuation = re.sub("・", "･", entry_half_width_punctuation)

        entry_full_width_punctuation_no_spaces = re.sub(
            r"\s+", "", entry_full_width_punctuation
        )
        if textage_id == "_geo_tea":
            # TODO: fix
            _ = "ジオメトリック∮ティーパーティー"
            pass
        if title in kamaitachi_titles:
            mapping[textage_id] = kamaitachi_titles[title]
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
        if title in kamaitachi_alt_titles:
            mapping[textage_id] = kamaitachi_alt_titles[title]
            continue
        if entry_no_spaces_lowercase in kamaitachi_alt_no_spaces:
            mapping[textage_id] = kamaitachi_alt_no_spaces[entry_no_spaces_lowercase]
            continue
        if title in special_cases:
            mapping[textage_id] = special_cases[title]
            continue
        raise RuntimeError(
            f"Could not determine kamaitachi ID for textage infinitas song: {textage_id} {title}"
        )
    log.info(f"Done normalizing data. Found {len(mapping)} matching songs.")
    return mapping


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format=CONSTANTS.LOG_FORMAT)
    if len(sys.argv) < 2:
        log.error("provide a session_uuid or list of session_uuids")
        sys.exit(1)
    for session in sys.argv[1:]:
        log.info(f"exporting {session}")
        export_to_kamaitachi(session)
        log.info("rate limiting, sleeping 60 seconds")
        # TODO: change to queue so this is optional
        time.sleep(60)
