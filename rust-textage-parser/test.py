#!/usr/bin/env python3
import re
import json
from subprocess import run


_ = run(["cargo", "build"])

with open("../../routing/bpi.json") as json_reader:
    data = json.load(json_reader)
    song_titles = set([entry["title"] for entry in data["body"]])

failed_titles = {}
with open("./test_output.txt", "wt") as results_writer:
    for index, title in enumerate(song_titles):
        result = run(
            ["./target/debug/rust-textage-parser", f"{title} NORMAL"],
            capture_output=True,
        )
        result_data = result.stdout.decode("utf8")
        if re.match(".*Could\s+not.*", result_data):
            failed_titles[f"{index}"] = title
        output = "\t".join([title, result_data])
        results_writer.write(output)

with open("./normalizer_to_rewrite.json", "wt") as json_writer, open(
    "failed.txt", "wt"
) as failed_writer:
    json.dump(failed_titles, json_writer, ensure_ascii=False, indent=2)
    for i, title in failed_titles.items():
        output = "\t".join([i, title])
        failed_writer.write(f"{output}\n")
