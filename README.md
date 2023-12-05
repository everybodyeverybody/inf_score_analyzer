# inf_score_analyzer

## Description

A python script/application that reads in video data of beatmania IIDX INFINITAS sessions.

## Intent

See my blog post [Making it Easier to Work Towards Mastery](https://cohost.org/strikeitup/post/374525-making-it-easier-to),
specifically the `Prior Work and Tech Constraints` section.

## Prerequisites

- a raw, HDMI-based feed of a beatmania IIDX INFINTAS session, 
either via capture card or software

## Setup

- `python3 -m venv .venv`
- `source .venv/bin/activate`
- `pip3 install -r requirements.txt`

## Usage 

```
python3 -m inf_score_analyzer
```

## What This Does

- download external song metadata from textage.cc
- set up/refresh any locally configured sqlite3 databases for the app
- load in configuration metadata from `data/`
- open the first available video input device on the computer
- loop over frames received from the input device, providing metadata every 300 seconds

During the video loop, if the application encouters frames that appear to be
a beatmania IIDX INFINITAS play session followed by a score screen, it will
capture data from the session and write this data to the sqlite3 database.

## Caveats

This was written on an Intel Mac, and so has only been really tested there.

This is functionally complete for myself, but I wanted to put it out there as proof.

This does support 1P, 2P and DP sessions, but assumes that one is using
the default window arrangement. The alternative window arrangements
will be handled in future work.

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
- refactor out very redundant code pieces (there are several)
- have community difficulty tables imported and mapped to textage data
- have this submit new scores to online score trackers
- collect time series data per song to see where one can improve specifically
- generate useful reports regarding scores/history
- implement a step-up-like song recommender
- plugin for obs based on this project's work
- break out textage code into its own module
