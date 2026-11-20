# Agent Instructions — Envoy Rainmaker Flight Time Converter

This repository converts monthly Envoy Air Rainmaker schedule PDFs into a CSV ready to import into **LogTen Pro**.

## First-Time Setup (when the user asks to "set this up" or before the first run)
1. Check that Python 3 is installed (`python3 --version` on Mac/Linux, `python --version` on Windows). If missing, help the user install Python 3.10+.
2. Run the setup script once to create the local virtual environment and install dependencies:
   - **Mac / Linux:** `./setup.sh`
   - **Windows:** `setup.bat`
3. Confirm the starter folders exist: `new/`, `scraped/`, and `logten pro format/`.

## Running the Converter (when the user says "go", "run", or asks to convert PDFs)
1. Check `new/` for `.pdf` files. If `new/` is empty, tell the user to drop their monthly Rainmaker PDFs into `new/` (with month and year in each filename, e.g., `2025-04.pdf` or `April 2025.pdf`).
2. Run the converter:
   - **Mac / Linux:** `./run.sh`
   - **Windows:** `run.bat`
3. Report back to the user:
   - How many operating flight legs were extracted.
   - How many deadhead legs (`DHD-A\OA_DHD`, `DHD`, `DHX`, etc.) were skipped (deadheads are excluded so they are never counted as flight time).
   - The path to the updated CSV: `logten pro format/logten_pro_import.csv`.
   - That processed PDFs were moved to `scraped/`.

## Rules
- Never commit personal PDFs (`new/`, `scraped/`) or logbook CSVs (`logten pro format/`) to git.
- Deadhead legs (`DHD-A\OA_DHD` and variants) are passenger travel, not FAR flight time — never count them as `Total Time`, `PIC`, or `SIC`.
- Run unit tests after any parser change: `./venv/bin/python3 -m unittest discover -s tests -v` (Windows: `venv\Scripts\python.exe -m unittest discover -s tests -v`).
