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

    def test_local_times_converted_to_utc_across_timezones_and_midnight(self):
        token_lines = [
            _line("Period: 202610 - Oct 01/Oct 31 Search"),
            _line("Show time as UTC"),
            _line("23 S 12396\\RA E70,E75 04:04 -00:13 24:00 48.00"),
            _line("LEG 4160 -1 E70 GSP ORD CA 11:38 12:54 11:52 13:08 Sched Sched 02:16 02:16 02:16"),
            _line("30 S 13007\\CH E75 07:18 24:00 48.00"),
            _line("CH 3367 -1 E75 CLT XNA CA 22:30 23:59 22:27 23:33 Sched Sched 02:29 02:06 02:29"),
        ]
        records = sft.parse_schedule_token_lines(token_lines, year=2026, month=10)
        self.assertEqual(len(records), 2)
        # GSP (EDT, UTC-4) 11:52 -> 15:52Z; ORD (CDT, UTC-5) 13:08 -> 18:08Z (diff = 02:16)
        self.assertEqual(records[0]["Date"], "2026-10-23")
        self.assertEqual(records[0]["Out"], "15:52")
        self.assertEqual(records[0]["In"], "18:08")
        self.assertEqual(records[0]["Total Time"], "02:16")
        # CLT (EDT, UTC-4) Oct 30 22:27 -> Oct 31 02:27Z; XNA (CDT, UTC-5) 23:33 -> Oct 31 04:33Z (diff = 02:06)
        self.assertEqual(records[1]["Date"], "2026-10-31")
        self.assertEqual(records[1]["Out"], "02:27")
        self.assertEqual(records[1]["In"], "04:33")
        self.assertEqual(records[1]["Total Time"], "02:06")

    def test_already_utc_pdf_is_not_double_converted(self):
        token_lines = [
            _line("Period: 202610 - Oct 01/Oct 31 Search"),
            _line("Show time as Local"),
            _line("23 S 12396\\RA E70,E75 04:04"),
            _line("LEG 4160 -1 E70 GSP ORD CA 15:38 17:54 15:52 18:08 Sched Sched 02:16 02:16 02:16"),
        ]
        records = sft.parse_schedule_token_lines(token_lines, year=2026, month=10)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["Date"], "2026-10-23")
        self.assertEqual(records[0]["Out"], "15:52")
        self.assertEqual(records[0]["In"], "18:08")

    def test_detects_collapsed_flying_days(self):
        token_lines = [
            _line("Period: 202608 - Aug 01/Aug 30 Search"),
            _line("3 S 6639\\RF E70 05:38 22:35 45.17"),
            _line("4 S 6500\\RF E75 03:39 05:13 10.43"),
            _line("17 S 6625\\RF E75 01:31 09:15 18.50"),
            _line("Details Flt Seq Eqp DHD DD ORG DST POS STD STA ATD ATA SkdFlt ActFlt SkdDur ActDur Time"),
            _line("LEG 3635 -1 E75 MIA TLH CA 15:30 17:01 15:19 16:39 Sched Sched 01:31 01:20 01:31"),
            _line("20 M 12105\\OT E75 0.00"),
        ]
        collapsed = sft.detect_collapsed_days(token_lines, year=2026, month=8)
        self.assertEqual(collapsed, [("2026-08-03", "05:38"), ("2026-08-04", "03:39")])

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


class TestAdversarialStressCases(unittest.TestCase):
    def test_diversion_and_return_to_gate_prefixes_do_not_corrupt_airports(self):
        token_lines = [
            _line("10 S 12001\\RA E75 03:00"),
            _line("DIV 3480 -1 E75 MIA GNV CA 07:49 09:14 07:46 09:03 Sched Div 01:25 01:17 01:25"),
            _line("RTD 3481 -1 E75 GNV MIA FO 10:00 11:20 10:05 10:25 Sched Rtd 01:20 00:20 01:20"),
        ]
        records = sft.parse_schedule_token_lines(token_lines, year=2025, month=6)
        self.assertEqual(len(records), 2)
        self.assertEqual((records[0]["From"], records[0]["To"]), ("MIA", "GNV"))
        self.assertEqual((records[1]["From"], records[1]["To"]), ("GNV", "MIA"))
        self.assertEqual((records[1]["PIC"], records[1]["SIC"]), ("", "00:20"))

    def test_port_of_spain_pos_iata_code_is_not_dropped_as_header(self):
        token_lines = [
            _line("12 S 12005\\REGL E75 03:50"),
            _line("LEG 3901 -1 E75 MIA POS CA 14:00 17:50 14:00 17:50 Sched Sched 03:50 03:50 03:50"),
        ]
        records = sft.parse_schedule_token_lines(token_lines, year=2025, month=7)
        self.assertEqual(len(records), 1)
        self.assertEqual((records[0]["From"], records[0]["To"]), ("MIA", "POS"))

    def test_legacy_envoy_aircraft_codes_er4_e45_e170_and_fo_sic(self):
        token_lines = [
            _line("5 S 6100\\REGL E45 04:00"),
            _line("LEG 3210 -1 ER4 DFW TYR FO 08:00 08:55 08:02 08:50 Sched Sched 00:55 00:48 00:55"),
            _line("LEG 3211 -1 E45 TYR DFW FO 09:30 10:25 09:28 10:20 Sched Sched 00:55 00:52 00:55"),
            _line("LEG 4012 -1 E170 ORD XNA FO 12:00 13:45 12:00 13:40 Sched Sched 01:45 01:40 01:45"),
        ]
        records = sft.parse_schedule_token_lines(token_lines, year=2022, month=3)
        self.assertEqual([r["Aircraft Type"] for r in records], ["ER4", "E45", "E170"])
        self.assertEqual([r["SIC"] for r in records], ["00:48", "00:52", "01:40"])
        self.assertEqual([r["PIC"] for r in records], ["", "", ""])

    def test_cancelled_leg_with_zero_actual_duration_is_skipped(self):
        token_lines = [
            _line("8 S 13001\\REGL E75 02:15"),
            _line("CXL 3500 -1 E75 MIA CLT CA 10:0012:1510:0010:00 Cxl Cxl 02:15 00:00 02:15"),
        ]
        records, skipped_dhd, skipped_unflown = sft.parse_schedule_token_lines_with_stats(
            token_lines, year=2025, month=5
        )
        self.assertEqual(records, [])
        self.assertEqual(skipped_dhd, 0)
        self.assertEqual(skipped_unflown, 1)

    def test_two_digit_flight_number_with_four_digit_sequence(self):
        token_lines = [
            _line("19 S 6625\\REGL E75 01:10"),
            _line("LEG 88 6625 E75 MIA EYW CA 11:00 12:10 11:00 12:05 Sched Sched 01:10 01:05 01:10"),
        ]
        records = sft.parse_schedule_token_lines(token_lines, year=2025, month=8)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["Flight"], "88")

    def test_february_three_month_span_and_leap_year_feb_29(self):
        # Non-leap year 2025: Jan 31 -> Feb 28 -> Mar 1
        token_lines_2025 = [
            _line("Period: 202502 - Jan 31/Mar 01"),
            _line("31 S 7001\\REGL E75 01:30"),
            _line("LEG 3101 -1 E75 MIA TLH CA 10:00 11:30 10:00 11:30 Sched Sched 01:30 01:30 01:30"),
            _line("1 S 7001\\REGL E75 01:30"),
            _line("LEG 3102 -1 E75 TLH MIA CA 13:00 14:30 13:00 14:30 Sched Sched 01:30 01:30 01:30"),
            _line("28 S 7099\\REGL E75 01:30"),
            _line("LEG 3103 -1 E75 MIA TLH CA 10:00 11:30 10:00 11:30 Sched Sched 01:30 01:30 01:30"),
            _line("1 S 7099\\REGL E75 01:30"),
            _line("LEG 3104 -1 E75 TLH MIA CA 13:00 14:30 13:00 14:30 Sched Sched 01:30 01:30 01:30"),
        ]
        recs_2025 = sft.parse_schedule_token_lines(token_lines_2025, year=2025, month=2)
        self.assertEqual(
            [r["Date"] for r in recs_2025],
            ["2025-01-31", "2025-02-01", "2025-02-28", "2025-03-01"],
        )

        # Leap year 2024: Feb 28 -> Feb 29 -> Mar 1
        token_lines_2024 = [
            _line("Period: 202402 - Feb 01/Mar 01"),
            _line("28 S 7050\\REGL E75 01:30"),
            _line("LEG 3201 -1 E75 MIA TLH CA 10:00 11:30 10:00 11:30 Sched Sched 01:30 01:30 01:30"),
            _line("29 S 7050\\REGL E75 01:30"),
            _line("LEG 3202 -1 E75 TLH MIA CA 13:00 14:30 13:00 14:30 Sched Sched 01:30 01:30 01:30"),
            _line("1 S 7050\\REGL E75 01:30"),
            _line("LEG 3203 -1 E75 MIA TLH CA 16:00 17:30 16:00 17:30 Sched Sched 01:30 01:30 01:30"),
        ]
        recs_2024 = sft.parse_schedule_token_lines(token_lines_2024, year=2024, month=2)
        self.assertEqual(
            [r["Date"] for r in recs_2024],
            ["2024-02-28", "2024-02-29", "2024-03-01"],
        )

    def test_westbound_arrive_before_depart_local_clock_and_dst_fallback_fold(self):
        # 1) MIA 23:30 EST -> PNS 23:15 CST (45 min flight landing "15 min earlier" on local clock!)
        # 2) DST fall-back night 2025-11-02: MIA 00:30 EDT (04:30Z) -> MIA 01:30 EST (fold=1, 06:30Z), ActDur=02:00
        token_lines = [
            _line("Show time as UTC"),
            _line("15 S 8001\\REGL E75 00:45"),
            _line("LEG 3700 -1 E75 MIA PNS CA 23:30 23:15 23:30 23:15 Sched Sched 00:45 00:45 00:45"),
        ]
        recs = sft.parse_schedule_token_lines(token_lines, year=2026, month=1)
        self.assertEqual(recs[0]["Date"], "2026-01-16")
        self.assertEqual((recs[0]["Out"], recs[0]["In"], recs[0]["Total Time"]), ("04:30", "05:15", "00:45"))

        token_lines_dst = [
            _line("Show time as UTC"),
            _line("2 S 8002\\REGL E75 02:00"),
            _line("LEG 3701 -1 E75 MIA JAX CA 00:30 01:30 00:30 01:30 Sched Sched 02:00 02:00 02:00"),
        ]
        recs_dst = sft.parse_schedule_token_lines(token_lines_dst, year=2025, month=11)
        self.assertEqual((recs_dst[0]["Out"], recs_dst[0]["In"], recs_dst[0]["Total Time"]), ("04:30", "06:30", "02:00"))

    def test_deduplicates_month_boundary_overlap_even_if_remarks_differ(self):
        # Same physical flight exported once in Local PDF and once in UTC PDF across month rollover
        local_lines = [
            _line("Period: 202608 - Aug 01/Sep 01"),
            _line("Show time as UTC"),
            _line("30 S 9001\\REGL E75 01:20"),
            _line("LEG 3635 -1 E75 MIA TLH CA 15:30 17:01 15:19 16:39 Sched Sched 01:31 01:20 01:31"),
            _line("1 S 9001\\REGL E75 01:26"),
            _line("LEG 3858 -1 E75 TLH MIA CA 06:05 07:31 05:57 07:23 Sched Sched 01:26 01:26 01:26"),
        ]
        utc_lines = [
            _line("Period: 202609 - Sep 01/Sep 30"),
            _line("Show time as Local"),
            _line("1 S 9001\\REGL E75 01:26"),
            _line("LEG 3858 -1 E75 TLH MIA CA 10:05 11:31 09:57 11:23 Sched Sched 01:26 01:26 01:26"),
        ]
        recs_a = sft.parse_schedule_token_lines(local_lines, year=2026, month=8)
        recs_b = sft.parse_schedule_token_lines(utc_lines, year=2026, month=9)
        combined = sft.combine_and_deduplicate_flights(recs_a + recs_b)
        self.assertEqual(len(combined), 2)

    def test_unknown_charter_airport_still_computes_exact_utc_from_known_hub(self):
        # ZZZ is not in AIRPORT_TZ, but MIA is known (EST UTC-5 in Jan) + ActDur=02:10
        token_lines = [
            _line("Period: 202601 - Jan 01/Jan 30"),
            _line("Show time as UTC"),
            _line("10 S 9500\\CH E75 02:10"),
            _line("CH 9100 -1 E75 MIA ZZZ CA 10:00 13:10 10:05 13:15 Sched Sched 02:10 02:10 02:10"),
        ]
        recs = sft.parse_schedule_token_lines(token_lines, year=2026, month=1)
        self.assertEqual(len(recs), 1)
        self.assertEqual((recs[0]["Out"], recs[0]["In"], recs[0]["Total Time"]), ("15:05", "17:15", "02:10"))

    def test_unsubmitted_period_dropdown_uses_actual_report_body_and_warns(self):
        token_lines = [
            _line("Period: 202508 - Aug 01/Aug 30 Search"),
            _line("Position:CA"),
            _line("Period:202611"),
        ]
        self.assertEqual(sft.parse_month_year_from_tokens(token_lines), (2026, 11))
        self.assertEqual(
            sft.detect_unsubmitted_period_dropdown(token_lines),
            ((2025, 8), (2026, 11)),
        )


if __name__ == "__main__":
    unittest.main()
