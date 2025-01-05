# inf_score_analyzer

## Description

A python script that reads in score data from screenshots or video data of beatmania IIDX INFINITAS sessions.

## Intent

See my blog post [Making it Easier to Work Towards Mastery](https://cohost.org/strikeitup/post/374525-making-it-easier-to),
specifically the `Prior Work and Tech Constraints` section.

## Prerequisites

- a raw, HDMI-based feed of a beatmania IIDX INFINTAS session, 
either via capture card or software

OR 

- raw screenshots provided by beatmania IIDX infinitas.

You can pres F12 during a beatmania IIDX session and it will
dump the screen to the game's Screenshots directory where it is installed.

## Setup

- `python3 -m venv .venv`
- `source .venv/bin/activate`
- `python3 -m pip install .` or `python3 -m pip install -r requirements.txt`

## Usage 

```
python3 -m inf_score_analyzer <paths to screenshots, can take wildcard paths>
```

## What This Does

- download external song metadata from textage.cc
- set up/refresh any locally configured sqlite3 databases for the app
- load in configuration metadata from `data/`
- if using a video feed:
    - open the first available video input device on the computer
    - loop over frames received from the input device, providing metadata every 300 seconds
- if using screenshots:
    - attempts to figure out if the screenshot is a score result or song select frame
    - reads score data from the screenshot
- writes score data to a local sqlite3 database
- on exit from video or finishing reading all screenshots, attempts to export the current session's scores to [kamaitachi](https://kamai.tachi.ac/)

## Caveats

This was written for Linux/Mac, as I used them as secondary/stream computers for my windows gaming sessions.

This is functionally complete for myself, but I wanted to put it out there as proof.

This assumes that one is using the default window arrangement. 
The HD update and my general lack of not playing
2P or DP has delayed setting the needed screen pixel constants for that in some 
parts of code, but will be handled in future work.

## Contributions

If you want to contribute, please run any code through:

- `black` 
- `mypy` 
- `flake8 --ignore=E501,W503`

Make sure that `python3 -m pytest` succeeds after any changes, and add/update any tests for any 
new functionality.

## TODO

These features are things I want but really don't need and will
get to sooner or later.

- windows and linux support
- alternative window arrangements
- have community difficulty tables imported and mapped to textage data
- collect time series data per song to see where one can improve specifically
- generate useful reports regarding scores/history
- implement a step-up-like song recommender
- plugin for obs based on this project's work
