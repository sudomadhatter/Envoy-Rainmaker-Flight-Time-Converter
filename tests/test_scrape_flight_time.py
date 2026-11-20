import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import scrape_flight_time as sft


def _line(*texts, first_x=0.05):
    tokens = []
    for idx, text in enumerate(texts):
        tokens.append({"text": text, "x": first_x if idx == 0 else 0.2 + idx * 0.05, "y": 0.5})
    return tokens


class TestDeadheadExclusion(unittest.TestCase):
    def test_dhd_a_oa_dhd_leg_is_omitted_from_flight_time(self):
        token_lines = [
            _line("12", "3456", "E75", "FO", "DFW", "ORD", "14:00", "16:15", "14:02", "16:10", "02:15", "02:08", "DHD-A\\OA_DHD"),
        ]
        records = sft.parse_schedule_token_lines(token_lines, year=2025, month=4)
        self.assertEqual(records, [])

    def test_real_rainmaker_deadhead_formats_are_omitted(self):
        real_lines = [
            "RF 3184 0 D DHD,OA_DHD CLT MIA CA 09:0511:1309:0511:13SchedSched 02:08 02:08 02:08",
            "DHO 4099 -1 E75 D DHD MIA CVG CA 08:35 11:32 08:27 11:13 Sched Sched 02:57 02:46 02:57",
            "RA 656 0 D DHD,OA_DHDDFW MIA CA 10:2014:1410:2014:14SchedSched 02:54 02:54 02:54",
            "CH 2356 0 D DHD,OA_DHD MIA CLT CA 11:4513:5011:4513:50 Sched Sched 02:05 02:05 02:05",
            "RA 3767 -1 E75 D DHD TLH MIA CA 09:5611:2510:1011:33 Sched Sched 01:29 01:23 03:22",
        ]
        for raw in real_lines:
            with self.subTest(raw=raw):
                token_lines = [
                    _line("14 S 13168\\RA E75 03:22"),
                    _line(raw),
                ]
                records, skipped_dhd, _ = sft.parse_schedule_token_lines_with_stats(token_lines, year=2026, month=10)
                self.assertEqual(records, [])
                self.assertEqual(skipped_dhd, 1)

    def test_deadhead_ocr_and_code_variants_are_omitted(self):
        variants = [
            "DHD-A/OA_DHD",
            "DHD-A OA_DHD",
            "OA_DHD",
            "DHD-A",
            "DHD",
            "DHX",
            "D",
        ]
        for code in variants:
            with self.subTest(code=code):
                token_lines = [
                    _line("14", "4102", "E75", "FO", "ORD", "MIA", "12:00", "15:00", "12:00", "15:00", "03:00", "03:00", code),
                ]
                records = sft.parse_schedule_token_lines(token_lines, year=2025, month=4)
                self.assertEqual(records, [], f"Expected deadhead code {code!r} to be omitted")

    def test_deadhead_with_trng_on_same_line_is_still_omitted(self):
        token_lines = [
            _line("15", "3891", "E75", "FO", "DFW", "CLT", "08:00", "10:30", "08:00", "10:30", "02:30", "02:30", "TRNG", "DHD-A\\OA_DHD"),
        ]
        records = sft.parse_schedule_token_lines(token_lines, year=2025, month=4)
        self.assertEqual(records, [])


class TestRealRainmakerParsing(unittest.TestCase):
    def test_concatenated_times_and_actual_duration_vs_pay_time(self):
        token_lines = [
            _line("13 S 13168\\RA E75 04:27"),
            _line("LEG 3480 -1 E75 MIA JAX CA 07:4909:1407:4609:03 Sched Sched 01:25 01:17 03:02"),
        ]
        records = sft.parse_schedule_token_lines(token_lines, year=2026, month=11)
        self.assertEqual(len(records), 1)
        rec = records[0]
        self.assertEqual(rec["Date"], "2026-11-13")
        self.assertEqual(rec["Flight"], "3480")
        self.assertEqual(rec["From"], "MIA")
        self.assertEqual(rec["To"], "JAX")
        self.assertEqual(rec["Out"], "07:46")
        self.assertEqual(rec["In"], "09:03")
        self.assertEqual(rec["Total Time"], "01:17")
        self.assertEqual(rec["PIC"], "01:17")
        self.assertEqual(rec["SIC"], "")

    def test_print_header_date_does_not_corrupt_tracked_day(self):
        token_lines = [
            _line("2 S 13125\\Add E75 06:57 09:30 19.00"),
            _line("11/19/26, 8:19 PM Rainmaker - CrewPayDetails"),
            _line("LEG 3780 -1 E75 MIA AXA CA 10:4814:5711:4215:37 Sched Sched 03:09 02:55 03:09"),
        ]
        records = sft.parse_schedule_token_lines(token_lines, year=2026, month=11)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["Date"], "2026-11-02")

    def test_future_unflown_scheduled_legs_are_skipped_by_default(self):
        token_lines = [
            _line("23 S 13264\\Add E75 04:53 06:05 12.17"),
            _line("LEG 3452 -1 E75 MIA TPA CA 18:40 19:50 Sched Sched 01:10 01:10"),
        ]
        records, skipped_dhd, skipped_unflown = sft.parse_schedule_token_lines_with_stats(
            token_lines, year=2026, month=11
        )
        self.assertEqual(records, [])
        self.assertEqual(skipped_dhd, 0)
        self.assertEqual(skipped_unflown, 1)

    def test_period_header_extracts_year_and_month_over_filename(self):
        token_lines = [
            _line("Period: 202611 - Nov 01/Dec 01 Search"),
            _line("Period:202611"),
        ]
        year, month = sft.parse_month_year_from_tokens(token_lines)
        self.assertEqual((year, month), (2026, 11))

    def test_operating_legs_preserved_alongside_skipped_deadhead(self):
        token_lines = [
            _line("16", "3501", "E75", "CA", "DFW", "AUS", "09:00", "10:00", "09:05", "10:02", "01:00", "00:57"),
            _line("16", "3502", "E75", "CA", "AUS", "DFW", "11:00", "12:00", "11:00", "12:00", "01:00", "01:00", "DHD-A\\OA_DHD"),
            _line("17", "3600", "E175", "FO", "DFW", "IAH", "13:00", "14:10", "13:01", "14:06", "01:10", "01:05"),
        ]
        records, skipped_dhd, skipped_unflown = sft.parse_schedule_token_lines_with_stats(
            token_lines, year=2025, month=4
        )
        self.assertEqual(skipped_dhd, 1)
        self.assertEqual(skipped_unflown, 0)
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["Flight"], "3501")
        self.assertEqual(records[0]["PIC"], "00:57")
        self.assertEqual(records[1]["Flight"], "3600")
        self.assertEqual(records[1]["SIC"], "01:05")


class TestPdfDiscoveryAndExtraction(unittest.TestCase):
    def test_find_pdf_files_deduplicates_case_insensitively(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            f1 = os.path.join(tmpdir, "April 2025.pdf")
            f2 = os.path.join(tmpdir, "May 2025.PDF")
            f3 = os.path.join(tmpdir, "notes.txt")
            for p in (f1, f2, f3):
                with open(p, "w", encoding="utf-8") as fh:
                    fh.write("")

            found = sft.find_pdf_files(tmpdir)
            self.assertEqual(len(found), 2)
            self.assertEqual(
                sorted(os.path.basename(p) for p in found),
                ["April 2025.pdf", "May 2025.PDF"],
            )

    def test_extract_pdf_token_lines_falls_back_to_multipage_vision_ocr_for_scanned_pdfs(self):
        fake_pdf = MagicMock()
        fake_pdf.__len__.return_value = 3
        fake_pypdfium2 = MagicMock()
        fake_pypdfium2.PdfDocument.return_value = fake_pdf

        page_tokens = {
            0: [[{"text": "page0", "x": 0.05, "y": 0.1}]],
            1: [[{"text": "page1", "x": 0.05, "y": 0.1}]],
            2: [[{"text": "page2", "x": 0.05, "y": 0.1}]],
        }

        with (
            patch.object(sft, "extract_pdfplumber_token_lines", return_value=[]),
            patch.object(sft, "HAS_VISION_OCR", True),
            patch.object(sft, "pypdfium2", fake_pypdfium2),
            patch.object(
                sft,
                "run_vision_ocr_token_lines",
                side_effect=lambda path, page_idx=0: page_tokens[page_idx],
            ) as mock_ocr,
        ):
            lines = sft.extract_pdf_token_lines("dummy.pdf")

        self.assertEqual(mock_ocr.call_count, 3)
        self.assertEqual([line[0]["text"] for line in lines], ["page0", "page1", "page2"])


class TestMonthDateTracker(unittest.TestCase):
    def test_underflow_and_overflow_rollover(self):
        tracker = sft.MonthDateTracker(2024, 12)
        tracker.update_day(30)
        self.assertEqual(tracker.get_current_date_str(), "2024-11-30")
        tracker.update_day(1)
        self.assertEqual(tracker.get_current_date_str(), "2024-12-01")
        tracker.update_day(31)
        self.assertEqual(tracker.get_current_date_str(), "2024-12-31")
        tracker.update_day(1)
        self.assertEqual(tracker.get_current_date_str(), "2025-01-01")


if __name__ == "__main__":
    unittest.main()
