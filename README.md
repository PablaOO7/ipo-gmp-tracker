# IPO GMP Tracker — Milestone 2

A personal IPO research dashboard with automated source checks,
JSON storage, historical snapshots, and pipeline status reporting.

## Data source

https://ipowatch.in/

The initial collector inspects the source page but does not publish
GMP records until the source-specific data mapping has been verified.

## Requirements

- Python 3.12 or later
- Git
- GitHub repository with GitHub Actions enabled

## Run locally

Create and activate a virtual environment:

Windows:
    py -m venv .venv
    .venv\Scripts\activate

macOS/Linux:
    python3 -m venv .venv
    source .venv/bin/activate

Install dependencies:

    python -m pip install -r requirements.txt

Run tests:

    python -m unittest discover -s tests -v

Inspect the source:

    python -m collector.collect

Review:
- data/status.json
- data/source-inspection.json

## GitHub Actions

The pipeline runs daily at 03:30 UTC (09:00 IST)
and can also be triggered manually from Actions.

The workflow requires repository contents write permission
to commit status updates.

## Disclaimer

This is a personal research project, not investment advice.
Grey market premiums are unofficial, can change rapidly, and
do not guarantee listing prices or returns. Verify IPO details
against official exchange filings and offer documents.

Source: IPO Watch — https://ipowatch.in/

Automated collection and reuse should follow the source's
applicable terms and any permission or access conditions.
