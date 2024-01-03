#!/usr/bin/env python3
from inf_score_analyzer.local_dataclasses import SongReference
from inf_score_analyzer.sqlite_setup import read_song_data_from_db

SONG_REFERENCE: SongReference = read_song_data_from_db()


def test_get_song_reference_by_bpm():
    inu_waltz_bpm_tuple = (230, 320)
    inu_waltz_textage_id = "_valse17"
    assert SONG_REFERENCE.by_bpm[inu_waltz_bpm_tuple] == set([inu_waltz_textage_id])
