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
import glob
import sys
import shutil
import calendar
import argparse
import tempfile
import pandas as pd

# PDF text layer libraries
try:
    import pdfplumber
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
    
    temp_img_path = os.path.join(tempfile.gettempdir(), f"ocr_page_{page_idx}.png")
    image.save(temp_img_path)

    file_url = NSURL.fileURLWithPath_(temp_img_path)
    request_handler = Vision.VNImageRequestHandler.alloc().initWithURL_options_(file_url, None)

    request = Vision.VNRecognizeTextRequest.alloc().init()
    request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    request_handler.performRequests_error_([request], None)

    obs_list = []
    for obs in request.results():
        bbox = obs.boundingBox()
        text = obs.topCandidates_(1)[0].string()
        obs_list.append({
            'text': text,
            'x': bbox.origin.x,
            'y': 1.0 - bbox.origin.y,  # Convert to top-down Y
            'w': bbox.size.width,
            'h': bbox.size.height
        })

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


def extract_pdf_token_lines(pdf_path):
    """
    Extracts text tokens with spatial coordinates. Falls back to pdfplumber lines if Vision OCR unavailable.
    """
    if HAS_VISION_OCR:
        return run_vision_ocr_token_lines(pdf_path)
    
    # Fallback to pdfplumber text line strings wrapped as mock token lists
    token_lines = []
    if pdfplumber:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                extracted = page.extract_text() or ""
                for line in extracted.splitlines():
                    if line.strip():
                        token_lines.append([{'text': line.strip(), 'x': 0.05, 'y': 0.5}])
    return token_lines


def parse_schedule_token_lines(token_lines, year=2025, month=1):
    """
    Parses spatial token lines into flight leg dictionaries with month trapping.
    """
    records = []
    tracker = MonthDateTracker(year, month)

    non_airports = {
        'LEG', 'DHX', 'DHD', 'DD', 'SI', 'RF', 'R1', 'R2', 'TRNG', 'POS', 'STD', 'STA',
        'ATD', 'ATA', 'EQP', 'FLT', 'SEQ', 'DUTY', 'E75', 'E70', 'E145', 'E175', 'ORG',
        'DST', 'DHO', 'PREM', 'PAID', 'RPT', 'BASE', 'UNPAID', 'SCHED', 'ACTFLT',
        'SKDFLT', 'SKDDUR', 'ACTDUR', 'TIME', 'DETAILS', 'TOTAL'
    }

    for line_tokens in token_lines:
        if not line_tokens:
            continue

        line_str = " ".join([t['text'] for t in line_tokens])

        # Day tracking: check if first token on far left (x < 0.16) is a day number 1..31
        first_token = line_tokens[0]
        if first_token['x'] < 0.16:
            m_day = re.match(r'^(?P<day>[0-3]?\d)\b(?!\s*:)', first_token['text'])
            if m_day:
                day_val = int(m_day.group("day"))
                if 1 <= day_val <= 31:
                    tracker.update_day(day_val)

        # Look for flight legs
        three_letter_words = re.findall(r'\b([A-Z]{3})\b', line_str)
        airports = [w for w in three_letter_words if w not in non_airports]
        flt_match = re.search(r'\b(\d{3,4})\b', line_str)

        if len(airports) >= 2 and flt_match and tracker.last_day is not None:
            flt_num = flt_match.group(1)
            org = airports[0]
            dst = airports[1]

            eqp_match = re.search(r'\b(E75|E175|E145|E70|CRJ\d|B73\d|A32\d)\b', line_str)
            eqp = eqp_match.group(1) if eqp_match else "E75"

            pos_match = re.search(r'\b(FO|CA|CP)\b', line_str)
            pos = pos_match.group(1).upper() if pos_match else "FO"

            times = re.findall(r'\b(\d{2}:\d{2})\b', line_str)
            std = times[0] if len(times) > 0 else ""
            sta = times[1] if len(times) > 1 else ""
            atd = times[2] if len(times) > 2 else std
            ata = times[3] if len(times) > 3 else sta

            act_dur = ""
            if len(times) >= 6:
                act_dur = times[5]
            elif len(times) >= 5:
                act_dur = times[4]
            elif len(times) >= 1:
                act_dur = times[-1]
            else:
                act_dur = "00:00"

            is_deadhead = (" D " in f" {line_str} " or "DHD" in line_str or "DHX" in line_str) and "TRNG" not in line_str

            date_str = tracker.get_current_date_str()

            pic_time = ""
            sic_time = ""
            dhd_time = ""

            if is_deadhead:
                dhd_time = act_dur
            elif pos in ("CA", "CP"):
                pic_time = act_dur
            else:
                sic_time = act_dur

            record = {
                "Date": date_str,
                "Flight": flt_num,
                "Aircraft Type": eqp,
                "Registration": eqp,
                "From": org,
                "To": dst,
                "Out": atd,
                "In": ata,
                "Total Time": act_dur if not is_deadhead else "00:00",
                "PIC": pic_time,
                "SIC": sic_time,
                "Deadhead": dhd_time,
                "Remarks": f"Position: {pos}, Out: {atd}Z, In: {ata}Z"
            }
            records.append(record)

    return records


def process_pdf_file(pdf_path):
    year, month = parse_month_year_from_filename(pdf_path)
    token_lines = extract_pdf_token_lines(pdf_path)
    return parse_schedule_token_lines(token_lines, year=year, month=month)


def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    default_input = os.path.join(base_dir, "new")
    default_output = os.path.join(base_dir, "logten pro format", "logten_pro_import.csv")
    default_archive = os.path.join(base_dir, "scraped")

    parser = argparse.ArgumentParser(description="Scrape pilot flight time PDFs into LogTen Pro CSV format.")
    parser.add_argument("--input", "-i", default=default_input, help="Directory containing PDF files or path to single PDF.")
    parser.add_argument("--output", "-o", default=default_output, help="Output CSV file path.")
    parser.add_argument("--archive", "-a", default=default_archive, help="Directory to move processed PDFs to.")

    args = parser.parse_args()

    pdf_files = []
    if os.path.isfile(args.input):
        pdf_files = [args.input]
    elif os.path.isdir(args.input):
        pdf_files = glob.glob(os.path.join(args.input, "*.pdf")) + glob.glob(os.path.join(args.input, "*.PDF"))

    if not pdf_files:
        print(f"No PDF files found in '{args.input}'.")
        sys.exit(0)

    print(f"Found {len(pdf_files)} PDF file(s) to process in '{args.input}'.")

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    if args.archive:
        os.makedirs(args.archive, exist_ok=True)

    all_flights = []
    processed_files = []

    for pdf in sorted(pdf_files):
        filename = os.path.basename(pdf)
        print(f"Processing '{filename}'...")
        flights = process_pdf_file(pdf)
        all_flights.extend(flights)
        processed_files.append(pdf)
        print(f"  -> Extracted {len(flights)} flight record(s).")

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

        df_combined.to_csv(args.output, index=False)
        print(f"\nSuccessfully updated '{args.output}' (Total records: {len(df_combined)}).")

        if args.archive:
            for pdf in processed_files:
                dest = os.path.join(args.archive, os.path.basename(pdf))
                shutil.move(pdf, dest)
                print(f"Moved '{os.path.basename(pdf)}' -> '{args.archive}'")
    else:
        print("No flight records were extracted from the PDF file(s).")


if __name__ == "__main__":
    main()
