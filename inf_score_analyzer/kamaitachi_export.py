#!/usr/bin/env python3
import sys
import time
import logging
import sqlite3
from copy import deepcopy
from datetime import datetime
from typing import List, Tuple, Dict, Any

import requests

from . import constants as CONSTANTS
from .local_dataclasses import ClearType

log = logging.getLogger(__name__)


def submit_score_request(scores: Dict[str, Any]) -> None:
    url = "https://kamaitachi.xyz/ir/direct-manual/import"
    headers = {"Authorization": f"Bearer {CONSTANTS.TACHI_API_TOKEN}"}
    response = requests.post(url, headers=headers, json=scores)
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
        log.info(response.status_code)
        log.info(response.text)
    return


def get_scores_by_session(session_id: str) -> List[Tuple]:
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
        "where session.session_uuid=?;"
    )
    app_db_connection = sqlite3.connect(CONSTANTS.APP_DB)
    db_cursor = app_db_connection.cursor()
    _ = db_cursor.execute(double_db, (str(CONSTANTS.USER_DB),))
    results = db_cursor.execute(query, (session_id,))
    return [result for result in results]


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


def build_score_entry(score: Tuple) -> Dict[str, Any]:
    base_score = {
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
    session_uuid = score[0]
    pgreat, great, good, bad, poor, fast, slow = score[1:8]
    total_score = great + (pgreat * 2)
    clear_type = score[8]
    time = score[9]
    difficulty = score[10].split("_")[1]
    title = score[11]
    kt_id = score[12]
    kt_lamp = translate_clear_type_to_lamp(clear_type)
    play_datetime = datetime.fromisoformat(time)
    kt_time_achieved_ms = int(play_datetime.timestamp() * 1000)
    base_score["comment"] = f"{title} {difficulty}"
    base_score["score"] = total_score
    base_score["lamp"] = kt_lamp
    base_score["identifier"] = kt_id
    base_score["difficulty"] = difficulty
    base_score["timeAchieved"] = kt_time_achieved_ms
    base_score["judgements"] = {
        "pgreat": pgreat,
        "great": great,
        "good": good,
        "bad": bad,
        "poor": poor,
    }
    base_score["optional"] = {
        "fast": fast,
        "slow": slow,
    }
    return base_score


def transform_scores(scores: List[Tuple]) -> Tuple[Dict[str, Any], ...]:
    base_meta = {"meta": {"game": "iidx", "service": "infinitas"}, "scores": []}
    sp_scores: Dict[str, Any] = deepcopy(base_meta)
    sp_scores["meta"]["playtype"] = "SP"
    dp_scores: Dict[str, Any] = deepcopy(base_meta)
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
    if CONSTANTS.TACHI_API_TOKEN == "":
        log.error(
            "Kamaitachi export failed, must set TACHI_API_TOKEN in env for script"
        )
        return
    scores = get_scores_by_session(session_id)
    sp_scores_json, dp_scores_json = transform_scores(scores)
    if len(sp_scores_json["scores"]) > 0:
        submit_score_request(sp_scores_json)
    if len(dp_scores_json["scores"]) > 0:
        submit_score_request(dp_scores_json)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format=CONSTANTS.LOG_FORMAT)
    if len(sys.argv) < 2:
        log.error("provide a session_uuid or list of session_uuids")
        sys.exit(1)
    for session in sys.argv[1:]:
        log.info(f"exporting {session}")
        export_to_kamaitachi(session)
        log.info("rate limiting, sleeping 60 seconds")
        time.sleep(60)
