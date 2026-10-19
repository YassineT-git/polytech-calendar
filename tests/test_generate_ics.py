import contextlib
import io
import os
import tempfile
import unittest
import urllib.error
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import generate_ics as g


WEEK = {"id": 1, "startMs": 1791763200000}
COURSE = {"id": "test", "name": "Informatique éè,;", "groups": "APP3 INFO GrB",
          "dayIndex": 1, "start": "09:00", "end": "11:00"}


class GeneratorTests(unittest.TestCase):
    def test_transient_502_retried_then_success(self):
        response = io.BytesIO(b'{"courses": []}')
        error = urllib.error.HTTPError("https://example.test", 502, "Bad Gateway", {}, None)
        with patch.object(g.urllib.request, "urlopen", side_effect=[error, response]) as call, \
                patch.object(g.time_module, "sleep") as sleep:
            self.assertEqual(g.get_json("https://example.test"), {"courses": []})
        self.assertEqual(call.call_count, 2)
        sleep.assert_called_once_with(2)

    def test_persistent_502_is_bounded(self):
        error = urllib.error.HTTPError("https://example.test", 502, "Bad Gateway", {}, None)
        with patch.object(g.urllib.request, "urlopen", side_effect=error) as call, \
                patch.object(g.time_module, "sleep"):
            with self.assertRaisesRegex(RuntimeError, "3 tentative"):
                g.get_json("https://example.test")
        self.assertEqual(call.call_count, 3)

    def test_404_not_retried(self):
        error = urllib.error.HTTPError("https://example.test", 404, "Not Found", {}, None)
        with patch.object(g.urllib.request, "urlopen", side_effect=error) as call:
            with self.assertRaises(RuntimeError):
                g.get_json("https://example.test")
        self.assertEqual(call.call_count, 1)

    def test_one_failed_week_preserves_every_existing_file(self):
        weeks = [dict(WEEK, id=i) for i in range(1, 5)]
        with tempfile.TemporaryDirectory() as directory:
            previous = os.getcwd()
            try:
                os.chdir(directory)
                Path("docs/calendars").mkdir(parents=True)
                Path("docs/edt.ics").write_bytes(b"legacy")
                Path("docs/calendars/info-grb.ics").write_bytes(b"profile")
                with patch.object(g, "get_json", side_effect=[{"weeks": weeks},
                        {"courses": [COURSE]}, RuntimeError("HTTP 502"),
                        {"courses": []}, {"courses": []}]):
                    with self.assertRaisesRegex(RuntimeError, "Collecte incomplète"):
                        g.main()
                self.assertEqual(Path("docs/edt.ics").read_bytes(), b"legacy")
                self.assertEqual(Path("docs/calendars/info-grb.ics").read_bytes(), b"profile")
                self.assertEqual(len(list(Path("docs/calendars").glob("*.ics"))), 1)
            finally:
                os.chdir(previous)

    def test_outage_stops_after_three_weeks(self):
        weeks = [dict(WEEK, id=i) for i in range(1, 105)]
        with patch.object(g, "get_json", side_effect=[{"weeks": weeks}] +
                [RuntimeError("502")] * 3) as call:
            with self.assertRaisesRegex(RuntimeError, "trois semaines"):
                g.fetch_all_weeks()
        self.assertEqual(call.call_count, 4)

    def test_invalid_payloads_cannot_become_enterprise_weeks(self):
        for payload in ({}, {"courses": None}, {"courses": [None]},
                        {"courses": [], "error": "ADE unavailable"}, []):
            with self.subTest(payload=payload), patch.object(g, "get_json",
                    side_effect=[{"weeks": [WEEK]}, payload]):
                with self.assertRaises(RuntimeError):
                    g.fetch_all_weeks()

    def test_invalid_week_is_not_silently_omitted(self):
        with patch.object(g, "get_json", return_value={"weeks": [{"id": 1}]}):
            with self.assertRaises(RuntimeError):
                g.fetch_all_weeks()

    def test_valid_empty_week_allowed(self):
        with patch.object(g, "get_json", side_effect=[{"weeks": [WEEK]}, {"courses": []}]):
            self.assertEqual(g.fetch_all_weeks(), [(WEEK, [])])

    def test_all_profiles_alias_and_deterministic_utf8_ics(self):
        with tempfile.TemporaryDirectory() as directory:
            previous = os.getcwd()
            try:
                os.chdir(directory)
                with patch.object(g, "fetch_all_weeks", return_value=[(WEEK, [COURSE])]):
                    g.main()
                    files = sorted(Path("docs/calendars").glob("*.ics"))
                    self.assertEqual(len(files), 12)
                    first = {p: p.read_bytes() for p in files}
                    self.assertEqual(Path("docs/edt.ics").read_bytes(),
                                     Path("docs/calendars/info-grb.ics").read_bytes())
                    self.assertIn(b"SUMMARY:Informatique", first[Path("docs/calendars/info-grb.ics")])
                    self.assertNotIn(b"SUMMARY:Informatique", first[Path("docs/calendars/elec-gra.ics")])
                    for data in first.values():
                        self.assertTrue(data.endswith(b"END:VCALENDAR\r\n"))
                        self.assertNotIn(b"\n", data.replace(b"\r\n", b""))
                        self.assertTrue(all(len(line) <= 75 for line in data.split(b"\r\n")))
                        data.decode("utf-8")
                    g.main()
                    self.assertEqual(first, {p: p.read_bytes() for p in files})
            finally:
                os.chdir(previous)

    def test_paris_dst_and_utf8_folding(self):
        self.assertEqual(g.format_utc(datetime(2026, 10, 19, 9, tzinfo=g.PARIS)),
                         "20261019T070000Z")
        self.assertEqual(g.format_utc(datetime(2026, 10, 26, 9, tzinfo=g.PARIS)),
                         "20261026T080000Z")
        line = "SUMMARY:" + "é🏢" * 40
        folded = g.fold_ics_line(line)
        self.assertEqual(folded[0] + "".join(s[1:] for s in folded[1:]), line)
        self.assertTrue(all(len(s.encode()) <= 75 for s in folded))

    def test_profile_error_occurs_before_any_write(self):
        with tempfile.TemporaryDirectory() as directory:
            previous = os.getcwd()
            try:
                os.chdir(directory)
                with patch.object(g, "fetch_all_weeks", return_value=[(WEEK, [COURSE])]), \
                        patch.object(g, "build_calendar", side_effect=["content", ValueError("invalid")]):
                    with self.assertRaises(ValueError):
                        g.main()
                self.assertFalse(Path("docs").exists())
            finally:
                os.chdir(previous)


if __name__ == "__main__":
    unittest.main()
