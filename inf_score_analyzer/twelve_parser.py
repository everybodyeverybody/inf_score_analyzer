#!/usr/bin/env python3

import csv
import requests

response = requests.get("https://iidx-sp12.github.io/songs.json")
data = response.json()

with open("checklist.csv", "wt") as writer:
    csv_writer = csv.writer(writer)
    header = ["name", "difficulty", "normal", "n_value", "hard", "h_value"]
    csv_writer.writerow(header)
    for entry in data:
        row = [entry[key] for key in header]
        csv_writer.writerow(row)
