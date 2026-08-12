#!/usr/bin/env python3
"""
Envoy Rainmaker Flight Time Converter
--------------------------------------
Scrapes pilot monthly Envoy Rainmaker flight schedule PDFs, extracts actual flight details,
decodes crew roles and times, and exports to a CSV format ready for LogTen Pro import.
Supports both digital PDFs and scanned/image-based PDFs via macOS Vision OCR.
"""

import os
import re
import glob
import sys
import shutil
import argparse
from datetime import datetime
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


def parse_month_year_from_filename(filename):
    """
    Extracts year and month from filenames such as:
    '2024-11.pdf', 'Nov_2024.pdf', '2024_11_schedule.pdf', '11-2024.pdf'
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

    # Check for Month Name + Year (e.g. Nov_2024 or 2024_Nov)
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

    # Default fallback for testing if no month/year in UUID filename
    return 2024, 11


def run_vision_ocr_on_pdf_page(pdf_path, page_idx=0):
    """
    Renders PDF page to image and runs macOS Vision OCR to return spatially ordered lines.
    """
    if not HAS_VISION_OCR or not pypdfium2:
        return ""

    pdf = pypdfium2.PdfDocument(pdf_path)
    page = pdf[page_idx]
    image = page.render(scale=3).to_pil()
    
    temp_img_path = f"/tmp/ocr_page_{page_idx}.png"
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

    # Cluster text observations into horizontal lines
    current_y = None
    lines = []
    current_line = []

    for item in sorted(obs_list, key=lambda i: i['y']):
        if current_y is None or abs(item['y'] - current_y) > 0.012:
            if current_line:
                current_line.sort(key=lambda i: i['x'])
                lines.append(' '.join([i['text'] for i in current_line]))
            current_line = [item]
            current_y = item['y']
        else:
            current_line.append(item)
            current_y = (current_y + item['y']) / 2.0

    if current_line:
        current_line.sort(key=lambda i: i['x'])
        lines.append(' '.join([i['text'] for i in current_line]))

    if os.path.exists(temp_img_path):
        os.remove(temp_img_path)

    return '\n'.join(lines)


def extract_pdf_lines(pdf_path):
    """
    Attempts text extraction via pdfplumber first. If empty, runs macOS Vision OCR.
    """
    text_content = ""
    if pdfplumber:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                extracted = page.extract_text() or ""
                if extracted.strip():
                    text_content += extracted + "\n"

    if not text_content.strip() and HAS_VISION_OCR:
        print("  -> Digital text layer empty; running macOS Vision OCR...")
        text_content = run_vision_ocr_on_pdf_page(pdf_path)

    return text_content


def parse_schedule_text(text, year=2024, month=11):
    """
    Parses schedule text lines into flight leg dictionaries.
    """
    records = []
    lines = text.splitlines()
    current_day = None

    day_header_pattern = re.compile(r'^\s*(?P<day>\d{1,2})\s+[S|O]')

    for line in lines:
        line_str = line.strip()
        if not line_str:
            continue

        # Day tracking (e.g., "21 S ...")
        day_match = day_header_pattern.match(line_str)
        if day_match:
            current_day = int(day_match.group("day"))

        # Look for flight legs (e.g. "RF 3554 0 E75 ... MIA CVG FO 15:01 17:44 21:09 23:39 ...")
        # Match flight numbers (3-5 digits), origin/dest airports (3 caps excluding keywords)
        non_airports = {'DHD', 'DD', 'SI', 'RF', 'R1', 'R2', 'TRNG', 'POS', 'STD', 'STA', 'ATD', 'ATA', 'EQP', 'FLT', 'SEQ', 'DUTY', 'E75', 'E70', 'E145'}
        
        # Find 3-letter uppercase sequences
        three_letter_words = re.findall(r'\b([A-Z]{3})\b', line_str)
        airports = [w for w in three_letter_words if w not in non_airports]

        flt_match = re.search(r'\b(\d{3,4})\b', line_str)
        
        # Check if line contains a flight leg (has flight number and at least 2 valid airport codes)
        if len(airports) >= 2 and flt_match and current_day:
            flt_num = flt_match.group(1)
            org = airports[0]
            dst = airports[1]


            # Extract aircraft type (e.g. E75, E175, B738, A320)
            eqp_match = re.search(r'\b(E75|E175|E145|CRJ\d|B73\d|A32\d)\b', line_str)
            eqp = eqp_match.group(1) if eqp_match else "E75"

            # Extract Position (FO / CA)
            pos_match = re.search(r'\b(FO|CA|CP)\b', line_str)
            pos = pos_match.group(1).upper() if pos_match else "FO"

            # Extract times (HH:MM patterns)
            times = re.findall(r'\b(\d{2}:\d{2})\b', line_str)
            
            # Times in layout: [STD, STA, ATD, ATA, SkdDur, ActDur, Time]
            # Standard order when available:
            std = times[0] if len(times) > 0 else ""
            sta = times[1] if len(times) > 1 else ""
            atd = times[2] if len(times) > 2 else std
            ata = times[3] if len(times) > 3 else sta
            
            # Duration logic
            act_dur = ""
            if len(times) >= 6:
                act_dur = times[5]  # ActDur
            elif len(times) >= 5:
                act_dur = times[4]  # SkdDur / Dur
            elif len(times) >= 1:
                act_dur = times[-1]
            else:
                act_dur = "00:00"

            is_deadhead = (" D " in f" {line_str} " or "DHD" in line_str) and "TRNG" not in line_str

            date_str = f"{year:04d}-{month:02d}-{current_day:02d}"

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
                "Registration": eqp,  # Tail registration / equipment
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
    text_content = extract_pdf_lines(pdf_path)
    return parse_schedule_text(text_content, year=year, month=month)


def main():
    parser = argparse.ArgumentParser(description="Scrape pilot flight time PDFs into LogTen Pro CSV format.")
    parser.add_argument("--input", "-i", default="/Users/sudohatter/Jons_flight_time/new", help="Directory containing PDF files or path to single PDF.")
    parser.add_argument("--output", "-o", default="/Users/sudohatter/Jons_flight_time/logten pro format/logten_pro_import.csv", help="Output CSV file path.")
    parser.add_argument("--archive", "-a", default="/Users/sudohatter/Jons_flight_time/scraped", help="Directory to move processed PDFs to.")
    
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
