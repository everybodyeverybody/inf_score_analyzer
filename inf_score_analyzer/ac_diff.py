#!/usr/bin/env python3
import logging
from datetime import datetime, timezone
from typing import List, Dict, Callable, Tuple
from .local_dataclasses import SongMetadata, Difficulty

from .download_textage_tables import (
    get_current_version_song_metadata_not_in_infinitas as get_em,
)


def check_optional_difficulties(
    song: SongMetadata,
) -> Dict[Difficulty, str]:
    optional_difficulties: Dict[Difficulty, str] = {}
    for difficulty in Difficulty:
        if difficulty == Difficulty.UNKNOWN:
            continue
        optional_difficulties[difficulty] = ""
        if (
            difficulty in song.difficulty_metadata
            and song.difficulty_metadata[difficulty].level != 0
        ):
            optional_difficulties[difficulty] = str(
                song.difficulty_metadata[difficulty].level
            )
    return optional_difficulties


def build_table(table_id: Tuple[str, str], songs: List[SongMetadata]) -> str:
    display = "none"
    # TODO: pass this in as a flag or something
    if table_id[0] == "alphanumeric":
        display = "block"
    table_block_start = (
        f"<div id='{table_id[0]}' class='table_area' style='display: {display}'>"
        "<table>\n"
    )
    # TODO: make this column aware to allow for styling/highlighting via css
    table_block_end = "</table></div>\n"
    header = """
        <tr>
            <td class='header' colspan=3>Folders</td>
            <td class='header' colspan=4>Single</td>
            <td class='header' colspan=4>Double</td>
        </tr>
        <tr>
            <td class='header'>Song</td>
            <td class='header'>Version</td>
            <td class='header'>Alpha</td>
            <td class='header' title='Single Play Normal'>N</td>
            <td class='header' title='Single Play Hyper'>H</td>
            <td class='header' title='Single Play Another'>A</td>
            <td class='header' title='Single Play Leggendaria'>L</td>
            <td class='header' title='Double Play Normal'>N</td>
            <td class='header' title='Double Play Hyper'>H</td>
            <td class='header' title='Double Play Another'>A</td>
            <td class='header' title='Double Play Leggendaria'>L</td>
        </tr>
    """

    tags_list = []
    for song in songs:
        difficulties = check_optional_difficulties(song)
        song_row = (
            "<tr>"
            "<td class='song'>"
            f"<div class='title'>{song.title}</div>"
            f"<div class='genre'>{song.genre}</div>"
            f"<div class='artist'>{song.artist}</div>"
            "</td>"
            f"<td class='version'>{song.version}</td>"
            f"<td class='alphanumeric'>{song.alphanumeric.name}</td>"
            f"<td class='spn'>{difficulties[Difficulty.SP_NORMAL]}</td>"
            f"<td class='sph'>{difficulties[Difficulty.SP_HYPER]}</td>"
            f"<td class='spa'>{difficulties[Difficulty.SP_ANOTHER]}</td>"
            f"<td class='spl'>{difficulties[Difficulty.SP_LEGGENDARIA]}</td>"
            f"<td class='dpn'>{difficulties[Difficulty.DP_NORMAL]}</td>"
            f"<td class='dph'>{difficulties[Difficulty.DP_HYPER]}</td>"
            f"<td class='dpa'>{difficulties[Difficulty.DP_ANOTHER]}</td>"
            f"<td class='dpl'>{difficulties[Difficulty.DP_LEGGENDARIA]}</td>"
            "</tr>"
        )

        tags_list.append(song_row)
    row_tags = "\n".join(tags_list)
    return f"{table_block_start}\n{header}\n{row_tags}\n{table_block_end}\n"


def build_javascript(table_list: List[Tuple[str, str]]) -> str:
    javascript_template = """
    <script>
        const registeredTables = new Map();
        {registered_tables}
    """
    untemplated_js = """
        function showOneTable(visibleTableId) {
            if (registeredTables.get(visibleTableId) == undefined) {
                console.log("table not registered " + visibleTableId);
                return;
            }
            console.log("table to show: " +visibleTableId);
            var tables = document.querySelectorAll("div.table_area");
            for (const table of tables) {
                if (table.id == visibleTableId) {
                    console.log("showing " + table.id);
                    table.style.display = "block";
                } else {
                    console.log("hiding " + table.id);
                    table.style.display = "none";
                }
            }
            var inputs = document.querySelectorAll("input");
            var clickedInput = "sort_" + visibleTableId;
            for (const input of inputs) {
                if(input.id == clickedInput) {
                    console.log("Clicked " + input.id);
                    input.style.background = "#000";
                    input.style.color = "#fff";
                } else{
                    console.log("Unclicked " + input.id);
                    input.removeAttribute("style");
                }
            }
            return;
        }
    </script>
    """
    registered_tables = "\n".join(
        [f"registeredTables.set('{table_id[0]}',true);" for table_id in table_list]
    )
    all_js = (
        javascript_template.format(registered_tables=registered_tables) + untemplated_js
    )
    return all_js


def build_buttons(sorted_tables: List[Tuple[str, str]]) -> str:
    buttons = []
    buttons_table = "<table id='sort_buttons'>{buttons}</table>"
    input_template = (
        "<td>"
        "<input id='sort_{table_id}' "
        "type='button' "
        "value='{table_label}' "
        "onclick='showOneTable(\"{table_id}\")'>"
        "</input>"
        "</td>"
    )
    for index, table_id in enumerate(sorted_tables):
        button = input_template.format(table_id=table_id[0], table_label=table_id[1])
        if index % 2 == 0:
            button = "<tr>" + button
        else:
            button = button + "</tr>"
        buttons.append(button)
    button_html = "\n".join(buttons)
    return buttons_table.format(buttons=button_html)


def write_html(sorted_tables: Dict[Tuple[str, str], str]):
    utc_now = datetime.now(tz=timezone.utc).isoformat()
    table_ids: List[Tuple[str, str]] = [table for table in sorted_tables.keys()]
    javascript = build_javascript(table_ids)
    buttons = build_buttons(table_ids)
    version_name = "Pinky Crush"
    version_number = 32

    css = """
    @media screen and (max-width:376px) {
         td {    
            font-family: sans-serif;    
             border: 1px solid #000000;     
            text-align: center;     
            padding: 0.1em;  
        }

        table#sort_buttons td { border: none; }
        table#sort_buttons input { padding: 1ch; }
        td.song { text-align: left; max-width: 20ch; }
        div.update { font-size: 0.6em; }
        div.title { font-size: 0.8em; font-weight: bold; }
        div.genre { font-size: 0.4em; font-weight: bold; }
        div.artist { font-size: 0.4em; font-style: italic;  }
        td.version { min-width:11ch; font-weight: bold; font-size: 0.4em; }
        td.alphanumeric { min-width:7ch; font-weight: bold; font-size: 0.4em; }
        td.spn { background: #66FFFF; min-width:2ch; font-weight: bold;  font-size: 0.6em; }
        td.sph { background: #FFFF45; min-width:2ch; font-weight: bold;  font-size: 0.6em; }
        td.spa { background: #F89B86; min-width:2ch; font-weight: bold;  font-size: 0.6em; }
        td.spl { background: #EC98F7; min-width:2ch; font-weight: bold;  font-size: 0.6em; }
        td.dpn { background: #66FFFF; min-width:2ch; font-weight: bold;  font-size: 0.6em; }
        td.dph { background: #FFFF45; min-width:2ch; font-weight: bold;  font-size: 0.6em; }
        td.dpa { background: #F89B86; min-width:2ch; font-weight: bold;  font-size: 0.6em; }
        td.dpl { background: #EC98F7; min-width:2ch; font-weight: bold;  font-size: 0.6em; }
        td.header { font-size: 0.6em; background-color: #484848; font-weight: bold; color: #ffffff; }
           
        input { min-width: 16ch; margin: 0.6ch;}
        h3 { font-family: sans-serif; font-weight: bold; }
        }
        @media screen and (min-width:376px) {
        td {     font-family: sans-serif;     border: 1px solid #000000;     text-align: center;     padding: 0.2em;  }
        table#sort_buttons td { border: none; }
        table#sort_buttons input { padding: 1ch; }
        td.song { text-align: left; min-width: 20ch; max-width:50ch; } 
        div.title { font-size: 1.2em; font-weight: bold; }
        div.genre { font-size: 0.6em; font-weight: bold; }
        div.artist { font-size: 0.6em; font-style: italic;  }
        td.version { min-width:12ch; font-weight: bold; font-size: 0.8em; }
        td.alphanumeric { min-width:8ch; font-weight: bold; font-size: 0.8em; }
        td.spn { background: #66FFFF; min-width:2ch; font-weight: bold;  font-size: 1.2em; }
        td.sph { background: #FFFF45; min-width:2ch; font-weight: bold;  font-size: 1.2em; }
        td.spa { background: #F89B86; min-width:2ch; font-weight: bold;  font-size: 1.2em; }
        td.spl { background: #EC98F7; min-width:2ch; font-weight: bold;  font-size: 1.2em; }
        td.dpn { background: #66FFFF; min-width:2ch; font-weight: bold;  font-size: 1.2em; }
        td.dph { background: #FFFF45; min-width:2ch; font-weight: bold;  font-size: 1.2em; }
        td.dpa { background: #F89B86; min-width:2ch; font-weight: bold;  font-size: 1.2em; }
        td.dpl { background: #EC98F7; min-width:2ch; font-weight: bold;  font-size: 1.2em; }
        td.header { background-color: #484848; font-weight: bold; color: #ffffff; }
        input { min-width: 16ch; margin: 0.4ch;}
        h3 { font-family: sans-serif; font-weight: bold; }
    }"""

    html_template = (
        "<!DOCTYPE html>"
        "<meta charset='utf-8' />"
        "<meta name='viewport' content='width=device-width,initial-scale=1' />"
        "<html>"
        "<title>Songs in IIDX {version_number} {version_name} Not in Infinitas</title>"
        "<head><style>\n"
        "{css}"
        "\n"
        "</style></head>\n"
        "<body>\n"
        "<h3>Songs in IIDX {version_number} {version_name} Not in Infinitas</h3>"
        "{javascript}"
        "<div class='update'>Generated from <a href='https://textage.cc/score/'>Textage</a> by <a href='https://github.com/everybodyeverybody/inf_score_analyzer/ac_diff.py'>ac_diff.py</a></div>\n"
        "<div class='update'>Last Update: <b>{utc_now}</b></div>\n"
        "{buttons}"
        "{tables}"
        "</body>"
        "</html>"
    )
    tables = "\n".join([table for table in sorted_tables.values()])
    html = html_template.format(
        utc_now=utc_now,
        css=css,
        javascript=javascript,
        buttons=buttons,
        tables=tables,
        version_name=version_name,
        version_number=version_number,
    )
    with open("index.html", "wt") as html_writer:
        html_writer.write(html)


def generate_all_sorted_tables(songs: List[SongMetadata]) -> Dict[Tuple[str, str], str]:
    tables_and_sort_methods: Dict[Tuple[str, str], Callable] = {
        (
            "alphanumeric",
            "By Title",
        ): SongMetadata.sort_by_alphanumeric,
        (
            "version",
            "By Version",
        ): SongMetadata.sort_by_version,
        (
            "spn",
            "By SP Normal",
        ): SongMetadata.sort_by_spn,
        (
            "sph",
            "By SP Hyper",
        ): SongMetadata.sort_by_sph,
        (
            "spa",
            "By SP Another",
        ): SongMetadata.sort_by_spa,
        (
            "spl",
            "By SP Leggendaria",
        ): SongMetadata.sort_by_spl,
        (
            "dpn",
            "By DP Normal",
        ): SongMetadata.sort_by_dpn,
        (
            "dph",
            "By DP Hyper",
        ): SongMetadata.sort_by_dph,
        (
            "dpa",
            "By DP Another",
        ): SongMetadata.sort_by_dpa,
        (
            "dpl",
            "By DP Leggendaria",
        ): SongMetadata.sort_by_dpl,
    }
    sorted_tables: Dict[Tuple[str, str], str] = {}
    for table_id, sort_method in tables_and_sort_methods.items():
        sorted_tables[table_id] = build_table(table_id, sorted(songs, key=sort_method))
    return sorted_tables


def main():
    logging.basicConfig(level=logging.INFO)
    songs = [value for key, value in get_em().items()]
    sorted_tables = generate_all_sorted_tables(songs)
    write_html(sorted_tables)


if __name__ == "__main__":
    main()
