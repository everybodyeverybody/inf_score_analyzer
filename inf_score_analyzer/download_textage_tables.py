#!/usr/bin/env python3
import os
import re
import sys
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Callable, Dict, Any, Union, Tuple

import requests  # type: ignore
from .local_dataclasses import Difficulty, SongMetadata, Alphanumeric

log = logging.getLogger(__name__)


def _download_textage_javascript(javascript_file: str, output_path: Path) -> Path:
    update = False
    textage_base_url = "https://textage.cc/score/"
    textage_last_modified_format = "%a, %d %b %Y %H:%M:%S %Z"
    # we used enumerate because we wanted the files in a specific
    # order mentioned in the html
    url = f"{textage_base_url}{javascript_file}"
    log.info(f"downloading {url}")
    last_modified_file = output_path / Path(f"{javascript_file}.last_modified")
    output_filename = output_path / Path(f"{javascript_file}")
    response = requests.get(url)
    # make sure to write about this as well, that its chinese w/o it
    response.encoding = "shift_jis"

    if response.status_code not in [200]:
        raise RuntimeError(f"could not download {url}: {response.status_code}")
    if "Last-Modified" not in response.headers:
        raise RuntimeError(
            f"server no longer returning last modified: {response.headers}"
        )
    if not os.path.exists(last_modified_file):
        update = True
    else:
        latest_last_modified = datetime.strptime(
            response.headers["Last-Modified"], textage_last_modified_format
        )
        with open(last_modified_file, "rt") as last_modified_reader:
            current_last_modified_str = last_modified_reader.readlines()[0].strip()
            current_last_modified = datetime.strptime(
                current_last_modified_str, textage_last_modified_format
            )
        if latest_last_modified > current_last_modified:
            update = True
    if update:
        log.info(f"updating {output_path}")
        with open(last_modified_file, "wt") as last_modified_writer:
            last_modified_writer.write(response.headers["Last-Modified"])
        with open(output_filename, "wt") as file_writer:
            file_writer.write(response.text)
    else:
        log.info(
            f"{output_path} not modified since {response.headers['Last-Modified']}"
        )
    return output_filename


def _convert_javascript_and_write_to_json(
    file: Path,
    block_start_regex: str,
    block_end_regex: str,
    specialized_parser: Callable,
):
    log.info(f"converting {file} to json")
    open_close_char_mapping = {"{": "}", "[": "]"}
    start_char = ""
    source_file_name = os.path.basename(file)
    source_file_path = os.path.dirname(file)
    parsed_file = source_file_path / Path(f"parsed_{source_file_name}.json")
    with open(file, "rt") as js_file_reader, open(parsed_file, "wt") as parsed_writer:
        capture_output = False
        line_count = 0
        for line in js_file_reader:
            line_count += 1
            line_match = re.match(block_start_regex, line)
            if line_match:
                if not line_match.groups() or len(line_match.groups()) < 1:
                    raise RuntimeError(
                        "start_regex needs match '()' for struct char { [ "
                    )
                start_char = line_match.groups()[0]
                start_line_extras = ""
                if len(line_match.groups()) > 1:
                    start_line_extras = "".join(line_match.groups()[1:])
                parsed_writer.write(f"{start_char}\n{start_line_extras}\n")
                capture_output = True
                continue
            if capture_output:
                if re.match(block_end_regex, line):
                    end_char = open_close_char_mapping[start_char]
                    parsed_writer.write(end_char)
                    break
                else:
                    # remove comments
                    line = re.sub(r"^//.*", "", line.strip())
                    # skip blanks
                    if re.match(r"^\s*$", line):
                        continue
                    parsed_line = specialized_parser(line)
                    parsed_writer.write(parsed_line)
    return parsed_file


def filter_infinitas_only_songs(
    version_data: Dict[str, List[int]], song_titles: Dict[str, List[str]]
) -> Dict[str, List[str]]:
    """
    Filtering logic taken from debugging
    https://textage.cc/score/scrlist.js
    against the following textage URL showing all
    infinitas songs
    https://textage.cc/score/index.html?a021B000

    In the textage code, lc is the query parameter
    a021B000

    and mt represents the version data table bitfields
    """
    # https://textage.cc/score/scrlist.js
    # function push_check1
    infinitas_only_songs: Dict[str, List[str]] = {}
    for key, value in song_titles.items():
        if key not in version_data:
            continue
        version_flag = version_data[key][0]
        is_in_infinitas = version_flag & 2
        if is_in_infinitas != 0:
            infinitas_only_songs[key] = value
    return infinitas_only_songs


def _read_difficulty(version_data: Dict[str, Any]) -> Dict[str, Dict[Difficulty, int]]:
    # https://textage.cc/score/scrlist.js get_level
    difficulties_by_textage_id: Dict[str, Dict[Difficulty, int]] = {}
    for key in version_data.keys():
        difficulties_by_textage_id[key] = {}
        spl = version_data[key][Difficulty.SP_LEGGENDARIA.value * 2 + 1]
        spa = version_data[key][Difficulty.SP_ANOTHER.value * 2 + 1]
        sph = version_data[key][Difficulty.SP_HYPER.value * 2 + 1]
        spn = version_data[key][Difficulty.SP_NORMAL.value * 2 + 1]
        dpl = version_data[key][Difficulty.DP_LEGGENDARIA.value * 2 + 1]
        dpa = version_data[key][Difficulty.DP_ANOTHER.value * 2 + 1]
        dph = version_data[key][Difficulty.DP_HYPER.value * 2 + 1]
        dpn = version_data[key][Difficulty.DP_NORMAL.value * 2 + 1]
        difficulties_by_textage_id[key][Difficulty.SP_LEGGENDARIA] = spl
        difficulties_by_textage_id[key][Difficulty.SP_ANOTHER] = spa
        difficulties_by_textage_id[key][Difficulty.SP_HYPER] = sph
        difficulties_by_textage_id[key][Difficulty.SP_NORMAL] = spn
        difficulties_by_textage_id[key][Difficulty.DP_LEGGENDARIA] = dpl
        difficulties_by_textage_id[key][Difficulty.DP_ANOTHER] = dpa
        difficulties_by_textage_id[key][Difficulty.DP_HYPER] = dph
        difficulties_by_textage_id[key][Difficulty.DP_NORMAL] = dpn
    return difficulties_by_textage_id


def read_notes_and_bpm() -> Tuple[
    Dict[str, Tuple[bool, int, int]], Dict[str, Dict[Difficulty, int]]
]:
    bpm_by_textage_id: Dict[str, Tuple[bool, int, int]] = {}
    notes_by_textage_id: Dict[str, Dict[Difficulty, int]] = {}
    notes_and_bpm = _get_textage_note_counts_and_bpm()
    for key in notes_and_bpm.keys():
        notes_by_textage_id[key] = {}
        spn = int(notes_and_bpm[key][Difficulty.SP_NORMAL.value])
        sph = int(notes_and_bpm[key][Difficulty.SP_HYPER.value])
        spa = int(notes_and_bpm[key][Difficulty.SP_ANOTHER.value])
        spl = int(notes_and_bpm[key][Difficulty.SP_LEGGENDARIA.value])
        dpn = int(notes_and_bpm[key][Difficulty.DP_NORMAL.value])
        dph = int(notes_and_bpm[key][Difficulty.DP_HYPER.value])
        dpa = int(notes_and_bpm[key][Difficulty.DP_ANOTHER.value])
        dpl = int(notes_and_bpm[key][Difficulty.DP_LEGGENDARIA.value])
        notes_by_textage_id[key][Difficulty.SP_NORMAL] = spn
        notes_by_textage_id[key][Difficulty.SP_HYPER] = sph
        notes_by_textage_id[key][Difficulty.SP_ANOTHER] = spa
        notes_by_textage_id[key][Difficulty.SP_LEGGENDARIA] = spl
        notes_by_textage_id[key][Difficulty.DP_NORMAL] = dpn
        notes_by_textage_id[key][Difficulty.DP_HYPER] = dph
        notes_by_textage_id[key][Difficulty.DP_ANOTHER] = dpa
        notes_by_textage_id[key][Difficulty.DP_LEGGENDARIA] = dpl
        bpm = str(notes_and_bpm[key][11])
        if re.match(r"\d+〜\d+", bpm):
            min_bpm, max_bpm = bpm.split("〜", maxsplit=1)
            soflan = True
        else:
            min_bpm = bpm
            max_bpm = bpm
            soflan = False
        bpm_by_textage_id[key] = (soflan, int(min_bpm), int(max_bpm))
    return bpm_by_textage_id, notes_by_textage_id


def _check_textage_metadata_files(
    textage_javascript_file: str,
    parser_start_regex: str,
    parser_end_regex: str,
    parser_callback: Callable,
) -> Dict[str, Any]:
    script_path = Path(os.path.dirname(os.path.realpath(sys.argv[0])))
    textage_metadata_path = script_path / Path(".textage-metadata")
    os.makedirs(textage_metadata_path, exist_ok=True)
    javascript = _download_textage_javascript(
        textage_javascript_file, textage_metadata_path
    )
    textage_data_file = _convert_javascript_and_write_to_json(
        javascript, parser_start_regex, parser_end_regex, parser_callback
    )
    log.info(f"reading {textage_data_file}")
    with open(textage_data_file, "rt") as reader:
        textage_data = json.load(reader)
    return textage_data


def get_infinitas_song_metadata() -> Dict[str, SongMetadata]:
    version_data = get_textage_version_data()
    song_titles = get_textage_song_titles()
    all_difficulties = _read_difficulty(version_data)
    all_bpms, all_note_counts = read_notes_and_bpm()
    infinitas_only_songs = filter_infinitas_only_songs(version_data, song_titles)
    metadata: Dict[str, SongMetadata] = {}
    for textage_id in infinitas_only_songs.keys():
        difficulty_and_notes: Dict[Difficulty, Tuple[int, int]] = {}
        difficulty: Dict[Difficulty, int] = all_difficulties[textage_id]
        notes: Dict[Difficulty, int] = all_note_counts[textage_id]
        difficulty_and_notes = {
            difficulty_id: (difficulty[difficulty_id], notes[difficulty_id])
            for difficulty_id in difficulty.keys()
        }
        title = " ".join(infinitas_only_songs[textage_id][5:])
        metadata[textage_id] = SongMetadata(
            textage_id=textage_id,
            title=title,
            artist=infinitas_only_songs[textage_id][4],
            genre=infinitas_only_songs[textage_id][3],
            version_id=int(infinitas_only_songs[textage_id][0]),
            alphanumeric=check_alphanumeric_folder(title[0]),
            difficulty_and_notes=difficulty_and_notes,
            soflan=all_bpms[textage_id][0],
            min_bpm=all_bpms[textage_id][1],
            max_bpm=all_bpms[textage_id][2],
        )
    return metadata


def filter_current_version_songs(
    version_data: Dict[str, List[int]], song_titles: Dict[str, List[str]]
) -> Dict[str, List[str]]:
    current_version_songs: Dict[str, List[str]] = {}
    for tag, title in song_titles.items():
        if tag not in version_data:
            log.warning(f"could not find {tag}:{title}")
            continue
        # scrlist.js line 682
        current_version_flag = version_data[tag][0]
        is_in_current_version = current_version_flag & 1
        if is_in_current_version == 0:
            log.warning(f"skipping {tag}:{title}")
            continue
        current_version_songs[tag] = title
    return current_version_songs


def get_current_version_songs_not_in_infinitas(
    version_data: Dict[str, List[int]], song_titles: Dict[str, List[str]]
) -> List[str]:
    current_version_songs = filter_current_version_songs(version_data, song_titles)
    infinitas_only_songs = filter_infinitas_only_songs(version_data, song_titles)
    inf_keys = set(list(infinitas_only_songs.keys()))
    cur_ver_keys = set(list(current_version_songs.keys()))
    not_in_inf_keys = cur_ver_keys.difference(inf_keys)
    not_in_inf_song_titles = []
    for key in not_in_inf_keys:
        not_in_inf_song_titles.append("".join(song_titles[key][5:]))
    return sorted(not_in_inf_song_titles)


def get_textage_version_data() -> Dict[str, Any]:
    def __convert_version_bitfield_to_json(bitfield: str) -> str:
        key, values = bitfield.split(":", maxsplit=1)
        if key == "'__dmy__'":
            return ""
        values = re.sub("A", "10", values)
        values = re.sub("B", "11", values)
        values = re.sub("C", "12", values)
        values = re.sub("D", "13", values)
        values = re.sub("E", "14", values)
        values = re.sub("F", "15", values)
        values = re.sub(r"//\d+", "", values)
        values = re.sub(',"<span.*span>"', "", values)
        key = re.sub("'", '"', key)
        return f"{key}:{values}\n"

    return _check_textage_metadata_files(
        textage_javascript_file="actbl.js",
        parser_start_regex=r"^\s*actbl=({).*$",
        parser_end_regex=r"\s*}\s*;\s*",
        parser_callback=__convert_version_bitfield_to_json,
    )


def get_textage_song_titles():
    def __remove_title_table_html(title_values: str) -> str:
        key, values = title_values.split(":", maxsplit=1)
        if key == "'__dmy__'":
            return ""
        values = re.sub(r".fontcolor\(.*?\)", "", values)
        values = re.sub("<span style='.*?'>", "", values)
        values = re.sub(r"<\\/span>", "", values)
        values = re.sub(r"<div class=.*?>", "", values)
        values = re.sub(r"<\\/div>", "", values)
        values = re.sub(r"<br>", "", values)
        values = re.sub(r"<b>", "", values)
        values = re.sub(r"<\\/b>", "", values)
        values = re.sub(r"^\[SS", "[-1", values)
        values = re.sub(r"\t", "", values)
        key = re.sub("'", '"', key)
        return f"{key}:{values}\n"

    return _check_textage_metadata_files(
        textage_javascript_file="titletbl.js",
        parser_start_regex=r"^\s*titletbl=({).*$",
        parser_end_regex=r"\s*}\s*;\s*",
        parser_callback=__remove_title_table_html,
    )


def _get_textage_note_counts_and_bpm() -> Dict[str, List[Union[int, str]]]:
    def __read_notes_and_bpm(notes_and_bpm_line: str) -> str:
        line = re.sub("'", '"', notes_and_bpm_line)
        return f"{line}\n"

    return _check_textage_metadata_files(
        textage_javascript_file="datatbl.js",
        parser_start_regex=r"^datatbl\s*=\s*({).*$",
        parser_end_regex=r"\s*}\s*;\s*",
        parser_callback=__read_notes_and_bpm,
    )


def get_textage_version_list() -> Any:
    def __read_vertbl(line: str) -> Any:
        line = re.sub(";", "", line)
        line = re.sub("]$", "", line)
        line = re.sub(r"vertbl\[35\]=", ",", line)
        return line

    return _check_textage_metadata_files(
        textage_javascript_file="scrlist.js",
        parser_start_regex=r"^vertbl\s*=\s*(\[)(.*)$",
        parser_end_regex=r"^\s*$",
        parser_callback=__read_vertbl,
    )


def check_alphanumeric_folder(char: str) -> Alphanumeric:
    if re.match("[ABCD]", char, re.IGNORECASE):
        return Alphanumeric.ABCD
    elif re.match("[EFGH]", char, re.IGNORECASE):
        return Alphanumeric.EFGH
    elif re.match("[IJKL]", char, re.IGNORECASE):
        return Alphanumeric.IJKL
    elif re.match("[MNOP]", char, re.IGNORECASE):
        return Alphanumeric.MNOP
    elif re.match("[QRST]", char, re.IGNORECASE):
        return Alphanumeric.QRST
    elif re.match("[UVWXYZ]", char, re.IGNORECASE):
        return Alphanumeric.UVWXYZ
    else:
        return Alphanumeric.OTHERS


def get_current_version_song_metadata_not_in_infinitas() -> Dict[str, SongMetadata]:
    # This file was combined from two projects that had not yet settled
    # on an API, and so has some repeat methods
    version_data = get_textage_version_data()
    song_titles = get_textage_song_titles()
    all_bpms, all_note_counts = read_notes_and_bpm()
    all_difficulties = _read_difficulty(version_data)
    version_list = get_textage_version_list()
    current_version_songs = filter_current_version_songs(version_data, song_titles)
    infinitas_only_songs = filter_infinitas_only_songs(version_data, song_titles)
    inf_keys = set(list(infinitas_only_songs.keys()))
    cur_ver_keys = set(list(current_version_songs.keys()))
    not_in_inf_keys = cur_ver_keys.difference(inf_keys)
    not_in_inf_song_metadata = {}
    for textage_id in sorted(not_in_inf_keys):
        version_id = int(current_version_songs[textage_id][0])
        title = " ".join(song_titles[textage_id][5:])
        # substream is last in textage js
        if version_id == 35:
            version_id = -1
        difficulty_and_notes: Dict[Difficulty, Tuple[int, int]] = {}
        difficulty: Dict[Difficulty, int] = all_difficulties[textage_id]
        notes: Dict[Difficulty, int] = all_note_counts[textage_id]
        difficulty_and_notes = {
            difficulty_id: (difficulty[difficulty_id], notes[difficulty_id])
            for difficulty_id in difficulty.keys()
        }
        song_metadata = SongMetadata(
            textage_id=textage_id,
            title=title,
            artist=song_titles[textage_id][4],
            genre=song_titles[textage_id][3],
            version_id=version_id,
            version=version_list[version_id],
            difficulty_and_notes=difficulty_and_notes,
            alphanumeric=check_alphanumeric_folder(title[0]),
            soflan=all_bpms[textage_id][0],
            min_bpm=all_bpms[textage_id][1],
            max_bpm=all_bpms[textage_id][2],
        )
        not_in_inf_song_metadata[textage_id] = song_metadata
    return not_in_inf_song_metadata


def get_all_song_metadata() -> Dict[str, SongMetadata]:
    all_song_metadata: Dict[str, SongMetadata] = {}
    version_data = get_textage_version_data()
    song_titles = get_textage_song_titles()
    all_bpms, all_note_counts = read_notes_and_bpm()
    all_difficulties = _read_difficulty(version_data)
    version_list = get_textage_version_list()
    song_titles_by_textage_id = {}
    for tag, title_version_metadata in song_titles.items():
        if tag not in version_data:
            log.warning(f"could not find {tag}:{title_version_metadata}")
            continue
        # scrlist.js line 682
        song_titles_by_textage_id[tag] = title_version_metadata

    for textage_id in version_data.keys():
        version_id = song_titles_by_textage_id[textage_id][0]
        title = " ".join(song_titles[textage_id][5:])
        difficulty_and_notes: Dict[Difficulty, Tuple[int, int]] = {}
        difficulty: Dict[Difficulty, int] = all_difficulties[textage_id]
        notes: Dict[Difficulty, int] = all_note_counts[textage_id]
        difficulty_and_notes = {
            difficulty_id: (difficulty[difficulty_id], notes[difficulty_id])
            for difficulty_id in difficulty.keys()
        }
        song_metadata = SongMetadata(
            textage_id=textage_id,
            title=title,
            artist=song_titles[textage_id][4],
            genre=song_titles[textage_id][3],
            version_id=version_id,
            version=version_list[version_id],
            difficulty_and_notes=difficulty_and_notes,
            alphanumeric=check_alphanumeric_folder(title[0]),
            soflan=all_bpms[textage_id][0],
            min_bpm=all_bpms[textage_id][1],
            max_bpm=all_bpms[textage_id][2],
        )
        all_song_metadata[textage_id] = song_metadata
    return all_song_metadata


if __name__ == "__main__":
    for key, value in get_all_song_metadata().items():
        print(value.to_dict())
