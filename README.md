# ✈️ Envoy Rainmaker Flight Time Converter

Convert your monthly **Envoy Air Rainmaker Crew Pay Details** PDFs into a clean CSV ready to import into **LogTen Pro**.

Built to run inside **Claude Code** (or **Antigravity**, **VS Code**, **Cursor**, or **Codex**) on **Mac** or **Windows** — no ZIP downloads and no macOS Gatekeeper security blocks.

---

## What It Does Automatically

- **Reads digital Rainmaker PDFs directly** (and falls back to multi-page macOS Vision OCR for scanned PDFs).
- **Detects the month and year from the PDF itself** (`Period: YYYYMM` header, with filename fallback) and handles month-end rollovers cleanly.
- **Auto-converts Local airport times to UTC (Zulu)** — even if **Show time as UTC** wasn't clicked in Rainmaker before printing, `Date`, `Out`, and `In` are converted to true UTC using airport IANA timezones so `(In − Out) == ActDur` in LogTen Pro.
- **Warns if any flying day was left collapsed** when printed from Rainmaker so no legs ever go missing silently.
- **Excludes deadheads from flight time** — legs marked `DHD-A\OA_DHD`, `DHD,OA_DHD`, `DHD`, `DHX`, or `D` are skipped so deadheads never inflate `Total Time`, `PIC`, or `SIC`.
- **Logs actual block time (`ActDur`), not pay/credit time**, and skips future unflown scheduled legs that do not yet have actual `ATD`/`ATA` times.
- **Deduplicates across runs** so you can drop in new monthly PDFs later without creating duplicate rows.

---

## Brand New to Coding AI Tools? Start Here (3-Minute Claude Code Setup)

If you have never used a coding LLM or Git before, the easiest way to run this converter is **Claude Code** (requires a Claude Pro, Max, Team, or Console account):

### Option A — Claude Desktop App (No Terminal Required)
1. Download and install the **Claude Desktop** app for **Mac** or **Windows**: [https://claude.ai/download](https://claude.ai/download)
2. Open the app, sign in, and click the **Code** tab in the left sidebar.
3. Paste this single message into the chat:

> **"Clone https://github.com/sudomadhatter/Envoy-Rainmaker-Flight-Time-Converter.git into my Documents folder, set it up using AGENTS.md, and show me the `new` folder where I drop my Rainmaker PDFs."**

Claude will download the repo, check/install Python, set up the virtual environment automatically, and tell you the exact folder to drop your PDFs into. Whenever you drop PDFs into `new/`, just type **`"go"`**.

### Option B — Claude Code in Terminal (or VS Code)
1. Install Claude Code with one command:
   - **Mac:** Press `Cmd + Space`, type **Terminal**, press Enter, and paste:
     ```bash
     curl -fsSL https://claude.ai/install.sh | bash
     ```
   - **Windows:** Open the Start menu, type **PowerShell**, press Enter, and paste:
     ```powershell
     irm https://claude.ai/install.ps1 | iex
     ```
2. **Close and reopen** Terminal / PowerShell, then type `claude` and follow the browser sign-in prompt (or install the official **Claude Code** extension inside [VS Code](https://code.visualstudio.com/)).
3. Follow the **Quick Start** below.

---

## Quick Start (If You Already Have Claude Code, VS Code, Antigravity, or Cursor)

### Step 1: Clone the Repo
Open a terminal (or your IDE's **Clone Repository** menu) and run:

```bash
git clone https://github.com/sudomadhatter/Envoy-Rainmaker-Flight-Time-Converter.git
cd Envoy-Rainmaker-Flight-Time-Converter
```

### Step 2: Open the Folder in Your Coding Platform
Open the cloned `Envoy-Rainmaker-Flight-Time-Converter` folder in **Claude Code**, **Antigravity**, **VS Code**, **Cursor**, or **Codex**.

This repo includes `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, and `.github/copilot-instructions.md` so your coding agent already knows how to set up and run it.

### Step 3: Let Your Agent Set It Up
In your IDE's chat, tell your agent:

> **"Set up this repo using AGENTS.md so it's ready to convert my Rainmaker PDFs."**

Your agent will check Python 3, run `./setup.sh` (Mac/Linux) or `setup.bat` (Windows) to build the local virtual environment (`venv`), and verify the folders are ready.

### Step 4: Export From Rainmaker, Drop Your PDFs & Run
1. In Envoy Rainmaker (**Crew Pay Details**), click **`More → Details`** so **all flying days are expanded** (collapsed days do not print individual legs into the PDF), and optionally click **`Show time as UTC`** (if left in Local time, the converter automatically converts `Date`/`Out`/`In` to UTC). Print / Save as PDF.
2. Drop one or more PDFs into the **`new/`** folder.
3. Tell your agent **`"go"`** (or **`"convert my PDFs"`**) — or run directly in the terminal:
   - **Mac / Linux:** `./run.sh`
   - **Windows:** `run.bat`

Your finished CSV will be saved to:
- **`logten pro format/logten_pro_import.csv`**

Processed PDFs are automatically moved to **`scraped/`** for safekeeping. All personal PDFs and CSVs are gitignored so they stay strictly on your machine.

---

## Optional Command-Line Flags

If you want to point at custom folders or keep original PDFs in place without moving them:

```bash
# Mac / Linux
./run.sh --input "path/to/pdfs" --output "path/to/logten_pro_import.csv" --archive ""

# Windows
run.bat --input "path\to\pdfs" --output "path\to\logten_pro_import.csv" --archive ""
```

- `--archive ""` leaves your original PDFs untouched instead of moving them into `scraped/`.
- `--include-scheduled` includes future scheduled legs that do not yet have actual departure/arrival times.

---

## How to Import Into LogTen Pro

1. Open **LogTen Pro** on your Mac (ensure **Settings → General → Dates and Times are UTC** is enabled).
2. In the menu bar, click **File → Import from File → Flights...**
3. Select **`logten pro format/logten_pro_import.csv`**.
4. Review the preview and click **Import**.

---

## Agent Setup Notes (For Coding Assistants)

If a user opens this repository and asks you to set it up or convert PDFs, follow `AGENTS.md`:
1. Ensure Python 3.10+ is available.
2. Run `./setup.sh` (Mac/Linux) or `setup.bat` (Windows) to create `venv` and install `requirements.txt`.
3. Verify tests pass: `./venv/bin/python3 -m unittest discover -s tests -v` (Windows: `venv\Scripts\python.exe -m unittest discover -s tests -v`).
4. Run `./run.sh` (Mac/Linux) or `run.bat` (Windows) to process PDFs in `new/` and report extracted flights, any collapsed-day warnings, skipped deadheads, and skipped unflown legs.

---

## License

MIT License — free to use and share.
