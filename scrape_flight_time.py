#!/usr/bin/env python3
"""
Envoy Rainmaker Flight Time Converter
--------------------------------------
Scrapes pilot monthly Envoy Rainmaker flight schedule PDFs, extracts actual flight details,
decodes crew roles and times, traps month overflow/underflow, and exports to a CSV format ready for LogTen Pro import.
Supports both digital PDFs and scanned/image-based PDFs via macOS Vision OCR.
"""

import os
import re
import sys
import shutil
import logging
import calendar
import argparse
import tempfile
import pandas as pd

from airport_timezones import convert_leg_local_to_utc, hhmm_to_minutes

# PDF text layer libraries
try:
    import pdfplumber
    logging.getLogger("pdfminer").setLevel(logging.ERROR)
except ImportError:
    pdfplumber = None

try:
    import pypdfium2
except ImportError:
    pypdfium2 = None

# macOS Vision OCR libraries
try:
    import Vision
    import Quartz
    from Foundation import NSURL
    HAS_VISION_OCR = True
except ImportError:
    HAS_VISION_OCR = False


class MonthDateTracker:
    """
    Traps month boundaries (overflow & underflow) when processing pilot monthly schedule days.
    
    - Underflow: Document starts with day >= 25 from previous month (e.g. Sept schedule starting Aug 31).
    - In-month: Day numbers belong to base month.
    - Overflow: Day resets from >= 25 to <= 7 near end of document (e.g. sequence crossing Nov 30 -> Dec 1).
    """
    def __init__(self, base_year, base_month):
        self.base_year = base_year
        self.base_month = base_month
        self.state = None  # "BEFORE", "IN", "AFTER"
        self.last_day = None

    def update_day(self, day):
        if not (1 <= day <= 31):
            return

        if self.last_day is None:
            if day >= 25:
                self.state = "BEFORE"
            else:
                self.state = "IN"
        else:
            if self.state == "BEFORE":
                if day <= 15:
                    self.state = "IN"
            elif self.state == "IN":
                if self.last_day >= 25 and day <= 7:
                    self.state = "AFTER"

        self.last_day = day

    def get_current_date_str(self):
        if self.last_day is None:
            return f"{self.base_year:04d}-{self.base_month:02d}-01"

        day = self.last_day
        if self.state == "BEFORE":
            m = self.base_month - 1 if self.base_month > 1 else 12
            y = self.base_year if self.base_month > 1 else self.base_year - 1
        elif self.state == "AFTER":
            m = self.base_month + 1 if self.base_month < 12 else 1
            y = self.base_year if self.base_month < 12 else self.base_year + 1
        else:
            m = self.base_month
            y = self.base_year

        max_days = calendar.monthrange(y, m)[1]
        valid_day = min(day, max_days)
        return f"{y:04d}-{m:02d}-{valid_day:02d}"


def parse_month_year_from_filename(filename):
    """
    Extracts year and month from filenames such as:
    'April 2025.pdf', '2024-11.pdf', 'Nov_2024.pdf', '2024_11_schedule.pdf'
    """
    basename = os.path.basename(filename)
    
    # Check for YYYY-MM or YYYY_MM
    match = re.search(r'(\b20\d{2})[-_/\.](0[1-9]|1[0-2])\b', basename)
    if match:
        return int(match.group(1)), int(match.group(2))
    
    # Check for MM-YYYY or MM_YYYY
    match = re.search(r'\b(0[1-9]|1[0-2])[-_/\.](20\d{2})\b', basename)
    if match:
        return int(match.group(2)), int(match.group(1))

    # Check for Month Name + Year (e.g. Nov_2024 or April 2025)
    months = {
        'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
        'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
        'january': 1, 'february': 2, 'march': 3, 'april': 4, 'june': 6,
        'july': 7, 'august': 8, 'september': 9, 'october': 10, 'november': 11, 'december': 12
    }
    
    for month_name, month_num in months.items():
        if month_name in basename.lower():
            year_match = re.search(r'\b(20\d{2})\b', basename)
            if year_match:
                return int(year_match.group(1)), month_num

    return 2025, 1


DEADHEAD_PATTERN = re.compile(
    r'(?:'
    r'DHD[-_/\\\s]*A[-_/\\\s]*OA[-_]?DHD'
    r'|OA[-_]?DHD'
    r'|DHD[-_/\\]?A\b'
    r'|\bDHD\b'
    r'|\bDHX\b'
    r'|(?<=\s)D(?=\s)'
    r')',
    re.IGNORECASE,
)


def is_deadhead_line(line_str):
    """Return True if a schedule line represents a deadhead leg (not flight time)."""
    return bool(DEADHEAD_PATTERN.search(f" {line_str} "))


def find_pdf_files(input_path):
    """Return sorted, deduplicated PDF paths from a single file or directory."""
    if os.path.isfile(input_path):
        return [input_path]
    if not os.path.isdir(input_path):
        return []

    seen = set()
    pdf_files = []
    for entry in sorted(os.listdir(input_path)):
        if entry.lower().endswith(".pdf"):
            full_path = os.path.join(input_path, entry)
            norm = os.path.normcase(os.path.abspath(full_path))
            if os.path.isfile(full_path) and norm not in seen:
                seen.add(norm)
                pdf_files.append(full_path)
    return pdf_files


def run_vision_ocr_token_lines(pdf_path, page_idx=0):
    """
    Renders PDF page to image, runs macOS Vision OCR, and returns lines composed of spatial token objects.
    Each token contains: 'text', 'x' (0..1), 'y' (0..1), 'w', 'h'.
    """
    if not HAS_VISION_OCR or not pypdfium2:
        return []

    pdf = pypdfium2.PdfDocument(pdf_path)
    page = pdf[page_idx]
    image = page.render(scale=3).to_pil()

    tmp_fd, temp_img_path = tempfile.mkstemp(prefix=f"ocr_page_{page_idx}_", suffix=".png")
    os.close(tmp_fd)
    try:
        image.save(temp_img_path)

        file_url = NSURL.fileURLWithPath_(temp_img_path)
        request_handler = Vision.VNImageRequestHandler.alloc().initWithURL_options_(file_url, None)

        request = Vision.VNRecognizeTextRequest.alloc().init()
        request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
        request_handler.performRequests_error_([request], None)

        obs_list = []
        for obs in (request.results() or []):
            bbox = obs.boundingBox()
            text = obs.topCandidates_(1)[0].string()
            obs_list.append({
                'text': text,
                'x': bbox.origin.x,
                'y': 1.0 - bbox.origin.y,  # Convert to top-down Y
                'w': bbox.size.width,
                'h': bbox.size.height
            })
    finally:
        if os.path.exists(temp_img_path):
            os.remove(temp_img_path)

    obs_list.sort(key=lambda i: i['y'])

    current_y = None
    lines = []
    current_line = []

    for item in obs_list:
        if current_y is None or abs(item['y'] - current_y) > 0.012:
            if current_line:
                current_line.sort(key=lambda i: i['x'])
                lines.append(current_line)
            current_line = [item]
            current_y = item['y']
        else:
            current_line.append(item)
            current_y = (current_y + item['y']) / 2.0

    if current_line:
        current_line.sort(key=lambda i: i['x'])
        lines.append(current_line)

    return lines


def parse_month_year_from_tokens(token_lines):
    """
    Extracts (year, month) from Rainmaker PDF headers such as 'Period: 202611' or 'Period:202608'.
    Returns None if no Period header is present.
    """
    for line_tokens in token_lines[:40]:
        line_str = " ".join(t['text'] for t in line_tokens)
        match = re.search(r'Period:\s*(20\d{2})(0[1-9]|1[0-2])\b', line_str, re.IGNORECASE)
        if match:
            return int(match.group(1)), int(match.group(2))
    return None


def extract_pdfplumber_token_lines(pdf_path):
    """Extract text lines via pdfplumber for digital PDFs."""
    token_lines = []
    if not pdfplumber:
        return token_lines

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            extracted = page.extract_text() or ""
            for line in extracted.splitlines():
                stripped = line.strip()
                if stripped:
                    token_lines.append([{'text': stripped, 'x': 0.05, 'y': 0.5}])
    return token_lines


def extract_pdf_token_lines(pdf_path):
    """
    Extracts text lines across all pages.
    Uses pdfplumber first for digital PDFs, falling back to multi-page macOS Vision OCR
    when no embedded text layer is present (scanned/image PDFs).
    """
    token_lines = extract_pdfplumber_token_lines(pdf_path)
    if token_lines:
        return token_lines

    if HAS_VISION_OCR and pypdfium2:
        pdf = pypdfium2.PdfDocument(pdf_path)
        all_lines = []
        for page_idx in range(len(pdf)):
            all_lines.extend(run_vision_ocr_token_lines(pdf_path, page_idx=page_idx))
        return all_lines

    return []


def detect_collapsed_days(token_lines, year=2025, month=1):
    """
    Detect flying day summary rows (e.g. '3 S 6639\\RF E70 05:38 ...') whose leg detail
    sub-table was left collapsed when the Rainmaker page was printed to PDF.
    Returns a list of (date_str, base_hhmm) tuples.
    """
    tracker = MonthDateTracker(year, month)
    collapsed = []
    pending_day = None  # (date_str, base_hhmm, has_details)

    for line_tokens in token_lines:
        if not line_tokens:
            continue
        line_str = " ".join(t['text'] for t in line_tokens)

        if (
            re.match(r'^\d{1,2}/\d{1,2}/\d{2,4}\b', line_str)
            or line_str.startswith(("http://", "https://"))
            or "Rainmaker - CrewPayDetails" in line_str
        ):
            continue

        if "Details" in line_str and "Flt" in line_str and "Seq" in line_str:
            if pending_day is not None:
                pending_day = (pending_day[0], pending_day[1], True)
            continue

        first_token = line_tokens[0]
        if first_token['x'] < 0.16:
            m_day = re.match(r'^(?P<day>[0-3]?\d)(?!\s*[:/\.\-])(?:\s|$)', first_token['text'])
            if m_day:
                day_val = int(m_day.group("day"))
                if 1 <= day_val <= 31:
                    if pending_day is not None and not pending_day[2]:
                        collapsed.append((pending_day[0], pending_day[1]))
                    pending_day = None

                    tracker.update_day(day_val)
                    date_str = tracker.get_current_date_str()
                    has_seq = bool(re.search(r'\b\d{3,6}\\[A-Za-z]+', line_str))
                    pos_times = re.findall(r'(?<!-)(\b\d{2}:\d{2}\b)', line_str)
                    nonzero_times = [t for t in pos_times if t != "00:00"]
                    if has_seq and nonzero_times:
                        pending_day = (date_str, nonzero_times[0], False)

    if pending_day is not None and not pending_day[2]:
        collapsed.append((pending_day[0], pending_day[1]))

    return collapsed


def detect_pdf_uses_local_time(token_lines, raw_records):
    """
    Determine whether the PDF's Out/In times are in airport local time rather than UTC.
    1. In Rainmaker, when local time is displayed, the toggle button reads 'Show time as UTC'.
       When UTC is displayed, the toggle button reads 'Show time as Local'.
    2. If neither header is present, inspect any cross-timezone legs: if converting local->UTC
       makes (In - Out) match ActDur where raw (In - Out) did not, the PDF is in local time.
    """
    for line_tokens in token_lines[:60]:
        line_str = " ".join(t['text'] for t in line_tokens).lower()
        if "show time as local" in line_str or "show local time" in line_str:
            return False
        if "show time as utc" in line_str:
            return True

    for rec in raw_records:
        raw_diff = (hhmm_to_minutes(rec["In"]) - hhmm_to_minutes(rec["Out"])) % 1440
        act_mins = hhmm_to_minutes(rec["Total Time"])
        if raw_diff != act_mins:
            _, utc_out, utc_in = convert_leg_local_to_utc(
                rec["Date"], rec["From"], rec["To"], rec["Out"], rec["In"], rec["Total Time"]
            )
            utc_diff = (hhmm_to_minutes(utc_in) - hhmm_to_minutes(utc_out)) % 1440
            if utc_diff == act_mins:
                return True

    return False


def parse_schedule_token_lines_with_stats(token_lines, year=2025, month=1, include_scheduled=False):
    """
    Parses spatial token lines into operating flight leg dictionaries with month trapping.
    Deadhead legs (e.g. DHD-A\\OA_DHD, DHD,OA_DHD, DHD, DHX, standalone D) are excluded
    from flight time. Future unflown scheduled legs (missing ATD/ATA/ActDur) are skipped
    unless include_scheduled=True. Automatically converts local airport Out/In/Date to UTC
    when Rainmaker was exported without 'Show time as UTC' toggled.
    Returns (records, skipped_deadheads, skipped_unflown).
    """
    records = []
    skipped_deadheads = 0
    skipped_unflown = 0
    tracker = MonthDateTracker(year, month)

    non_airports = {
        'LEG', 'DHX', 'DHD', 'DD', 'SI', 'RF', 'R1', 'R2', 'TRNG', 'POS', 'STD', 'STA',
        'ATD', 'ATA', 'EQP', 'FLT', 'SEQ', 'DUTY', 'E75', 'E70', 'E145', 'E175', 'ORG',
        'DST', 'DHO', 'PREM', 'PAID', 'RPT', 'BASE', 'UNPAID', 'SCHED', 'ACTFLT',
        'SKDFLT', 'SKDDUR', 'ACTDUR', 'TIME', 'DETAILS', 'TOTAL', 'USD', 'PDM', 'SRC',
        'UTC', 'RSV', 'ADD', 'PAY', 'RESV', 'REGL'
    }

    for line_tokens in token_lines:
        if not line_tokens:
            continue

        line_str = " ".join([t['text'] for t in line_tokens])

        # Skip browser print headers and footer URLs so timestamps like 11/19/26 never corrupt day tracking
        if (
            re.match(r'^\d{1,2}/\d{1,2}/\d{2,4}\b', line_str)
            or line_str.startswith(("http://", "https://"))
            or "Rainmaker - CrewPayDetails" in line_str
        ):
            continue

        # Day tracking: check if first token on far left (x < 0.16) starts with a standalone day number 1..31
        first_token = line_tokens[0]
        if first_token['x'] < 0.16:
            m_day = re.match(r'^(?P<day>[0-3]?\d)(?!\s*[:/\.\-])(?:\s|$)', first_token['text'])
            if m_day:
                day_val = int(m_day.group("day"))
                if 1 <= day_val <= 31:
                    tracker.update_day(day_val)

        flt_match = re.search(r'\b(\d{3,4})\b', line_str)
        if flt_match and tracker.last_day is not None and is_deadhead_line(line_str):
            skipped_deadheads += 1
            continue

        # Look for operating flight legs
        three_letter_words = re.findall(r'\b([A-Z]{3})\b', line_str)
        airports = [w for w in three_letter_words if w not in non_airports]

        if len(airports) >= 2 and flt_match and tracker.last_day is not None:
            flt_num = flt_match.group(1)
            org = airports[0]
            dst = airports[1]

            eqp_match = re.search(r'\b(E75|E175|E145|E70|CRJ\d|B73\d|A32\d)\b', line_str)
            eqp = eqp_match.group(1) if eqp_match else "E75"

            pos_match = re.search(r'\b(FO|CA|CP)\b', line_str)
            pos = pos_match.group(1).upper() if pos_match else "FO"

            # No \b required so concatenated Rainmaker times like 07:4909:1407:4609:03 extract cleanly
            times = re.findall(r'(\d{2}:\d{2})', line_str)
            if len(times) < 6:
                if not include_scheduled:
                    skipped_unflown += 1
                    continue
                std = times[0] if len(times) > 0 else ""
                sta = times[1] if len(times) > 1 else ""
                atd = std
                ata = sta
                act_dur = times[2] if len(times) > 2 else "00:00"
            else:
                atd = times[2]
                ata = times[3]
                act_dur = times[5]

            date_str = tracker.get_current_date_str()

            pic_time = act_dur if pos in ("CA", "CP") else ""
            sic_time = "" if pos in ("CA", "CP") else act_dur

            record = {
                "Date": date_str,
                "Flight": flt_num,
                "Aircraft Type": eqp,
                "Registration": eqp,
                "From": org,
                "To": dst,
                "Out": atd,
                "In": ata,
                "Total Time": act_dur,
                "PIC": pic_time,
                "SIC": sic_time,
                "Deadhead": "",
                "Remarks": f"Position: {pos}, Out: {atd}Z, In: {ata}Z",
                "_pos": pos,
            }
            records.append(record)

    uses_local = detect_pdf_uses_local_time(token_lines, records)
    for rec in records:
        pos = rec.pop("_pos")
        if uses_local and rec["Out"] and rec["In"] and rec["Total Time"]:
            local_date = rec["Date"]
            local_out = rec["Out"]
            local_in = rec["In"]
            utc_date, utc_out, utc_in = convert_leg_local_to_utc(
                local_date, rec["From"], rec["To"], local_out, local_in, rec["Total Time"]
            )
            rec["Date"] = utc_date
            rec["Out"] = utc_out
            rec["In"] = utc_in
            rec["Remarks"] = (
                f"Position: {pos}, Local: {local_date} {local_out}-{local_in}, "
                f"Out: {utc_out}Z, In: {utc_in}Z"
            )

    return records, skipped_deadheads, skipped_unflown


def parse_schedule_token_lines(token_lines, year=2025, month=1, include_scheduled=False):
    """
    Parses spatial token lines into operating flight leg dictionaries with month trapping.
    """
    records, _, _ = parse_schedule_token_lines_with_stats(
        token_lines, year=year, month=month, include_scheduled=include_scheduled
    )
    return records


def process_pdf_file_with_report(pdf_path, include_scheduled=False):
    token_lines = extract_pdf_token_lines(pdf_path)
    header_ym = parse_month_year_from_tokens(token_lines)
    if header_ym is not None:
        year, month = header_ym
    else:
        year, month = parse_month_year_from_filename(pdf_path)
    collapsed_days = detect_collapsed_days(token_lines, year=year, month=month)
    records, skipped_deadheads, skipped_unflown = parse_schedule_token_lines_with_stats(
        token_lines, year=year, month=month, include_scheduled=include_scheduled
    )
    converted_local_to_utc = any("Local:" in r.get("Remarks", "") for r in records)
    return records, skipped_deadheads, skipped_unflown, collapsed_days, converted_local_to_utc


def process_pdf_file_with_stats(pdf_path, include_scheduled=False):
    records, skipped_deadheads, skipped_unflown, _, _ = process_pdf_file_with_report(
        pdf_path, include_scheduled=include_scheduled
    )
    return records, skipped_deadheads, skipped_unflown


def process_pdf_file(pdf_path, include_scheduled=False):
    records, _, _ = process_pdf_file_with_stats(pdf_path, include_scheduled=include_scheduled)
    return records


def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    default_input = os.path.join(base_dir, "new")
    default_output = os.path.join(base_dir, "logten pro format", "logten_pro_import.csv")
    default_archive = os.path.join(base_dir, "scraped")

    parser = argparse.ArgumentParser(description="Scrape pilot flight time PDFs into LogTen Pro CSV format.")
    parser.add_argument("--input", "-i", default=default_input, help="Directory containing PDF files or path to single PDF.")
    parser.add_argument("--output", "-o", default=default_output, help="Output CSV file path.")
    parser.add_argument("--archive", "-a", default=default_archive, help="Directory to move processed PDFs to (empty string to keep originals in place).")
    parser.add_argument("--include-scheduled", action="store_true", help="Include future scheduled legs that do not yet have actual block times.")

    args = parser.parse_args()

    pdf_files = find_pdf_files(args.input)

    if not pdf_files:
        print(f"No PDF files found in '{args.input}'.")
        sys.exit(0)

    print(f"Found {len(pdf_files)} PDF file(s) to process in '{args.input}'.")

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    if args.archive:
        os.makedirs(args.archive, exist_ok=True)

    all_flights = []
    total_skipped_deadheads = 0
    total_skipped_unflown = 0
    processed_files = []

    for pdf in pdf_files:
        filename = os.path.basename(pdf)
        print(f"Processing '{filename}'...")
        (
            flights,
            skipped_deadheads,
            skipped_unflown,
            collapsed_days,
            converted_local_to_utc,
        ) = process_pdf_file_with_report(pdf, include_scheduled=args.include_scheduled)
        all_flights.extend(flights)
        total_skipped_deadheads += skipped_deadheads
        total_skipped_unflown += skipped_unflown
        processed_files.append(pdf)

        notes = []
        if converted_local_to_utc:
            notes.append("converted local times -> UTC")
        if skipped_deadheads:
            notes.append(f"skipped {skipped_deadheads} deadhead leg(s)")
        if skipped_unflown:
            notes.append(f"skipped {skipped_unflown} unflown scheduled leg(s)")
        note_str = f" ({', '.join(notes)})" if notes else ""
        print(f"  -> Extracted {len(flights)} flight record(s){note_str}.")
        if collapsed_days:
            day_summary = ", ".join(f"{d} ({hrs})" for d, hrs in collapsed_days)
            print(
                f"  ⚠️  WARNING: {len(collapsed_days)} flying day(s) in '{filename}' were collapsed when printed "
                f"and have NO leg details in the PDF: {day_summary}. "
                f"Click 'More -> Details' in Rainmaker and re-export to include them."
            )

    if all_flights:
        df_new = pd.DataFrame(all_flights)
        columns_order = [
            "Date", "Flight", "Aircraft Type", "Registration", "From", "To",
            "Out", "In", "Total Time", "PIC", "SIC", "Deadhead", "Remarks"
        ]
        for col in columns_order:
            if col not in df_new.columns:
                df_new[col] = ""

        df_new = df_new[columns_order]

        if os.path.exists(args.output):
            try:
                df_existing = pd.read_csv(args.output, dtype=str)
                df_combined = pd.concat([df_existing, df_new], ignore_index=True).drop_duplicates()
            except Exception:
                df_combined = df_new
        else:
            df_combined = df_new

        df_combined = df_combined.sort_values(by=["Date", "Out", "Flight"], kind="stable")
        df_combined.to_csv(args.output, index=False)

        summary_notes = []
        if total_skipped_deadheads:
            summary_notes.append(f"skipped {total_skipped_deadheads} deadhead leg(s)")
        if total_skipped_unflown:
            summary_notes.append(f"skipped {total_skipped_unflown} unflown scheduled leg(s)")
        summary_suffix = f", {', '.join(summary_notes)}" if summary_notes else ""
        print(f"\nSuccessfully updated '{args.output}' (Total records: {len(df_combined)}{summary_suffix}).")

        if args.archive:
            for pdf in processed_files:
                dest = os.path.join(args.archive, os.path.basename(pdf))
                shutil.move(pdf, dest)
                print(f"Moved '{os.path.basename(pdf)}' -> '{args.archive}'")
    else:
        print("No flight records were extracted from the PDF file(s).")


if __name__ == "__main__":
    main()
