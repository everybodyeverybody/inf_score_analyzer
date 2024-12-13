#!/usr/bin/env python3
import re
import sys
import json
from pathlib import Path
from subprocess import run
from typing import Optional


def parse_args(args: list[str]) -> Optional[Path]:
    if len(args) != 2:
        print("usage: ./find_mismatching_titles.py <path to routing's bpi json file>")
        return None
    bpi_json = Path(args[1])
    if not bpi_json.exists():
        raise RuntimeError("file {bpi_json.absolute()} does not exist")
    return bpi_json


def read_routing_bpi_json(bpi_json_file: Path) -> set[str]:
    with open(bpi_json_file, "rt") as json_reader:
        data = json.load(json_reader)
    return set([entry["title"] for entry in data["body"]])


def main() -> None:
    """
    Read in the BPI JSON and compare against our textage class/app
    that we can locate all songs within it. If not, generate
    a log and a piece of normalization JSON to be manually added to
    textage_to_bpi_normalizer.json.
    """
    bpi_json_path = parse_args(sys.argv)
    if not bpi_json_path:
        return
    song_titles = read_routing_bpi_json(bpi_json_path)
    _ = run(["cargo", "build"])
    failed_titles = {}
    with open("./test_output.txt", "wt") as results_writer:
        for index, title in enumerate(song_titles):
            result = run(
                ["./target/debug/rust-textage-parser", f"{title} NORMAL"],
                capture_output=True,
            )
            result_data = result.stdout.decode("utf8")
            if re.match(r".*Could\s+not.*", result_data):
                failed_titles[f"{index}"] = title
            output = "\t".join([title, result_data])
            results_writer.write(output)

    # To find the textage ID, open textage-data/titletbl.js.parsed.json
    # and look for whatever matches against the song title in either
    # of these logs
    with open("./mismatching_titles.json", "wt") as json_writer:
        json.dump(failed_titles, json_writer, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
