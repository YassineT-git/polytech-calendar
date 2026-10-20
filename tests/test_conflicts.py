import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

import generate_ics as g
from repair_calendars import properties, repair_calendar


class ConflictTests(unittest.TestCase):
    def setUp(self):
        self.start = datetime(2026, 10, 19, tzinfo=g.PARIS)
        self.week = {"id": 10, "startMs": self.start.timestamp() * 1000}
        self.course = {"id": "lesson", "name": "Bases de données", "groups": "APP3 INFO",
                       "dayIndex": 1, "start": "09:00", "end": "11:00"}

    def test_short_school_week_does_not_create_enterprise(self):
        with patch.object(g, "FORCED_ENTERPRISE_DATES", set()):
            events, count = g.build_profile_events([(self.week, [self.course])], "INFO", "GrB")
        self.assertEqual([e["kind"] for e in events], ["school"])
        self.assertEqual(count, 0)

    def test_school_takes_priority_over_forced_enterprise(self):
        with patch.object(g, "FORCED_ENTERPRISE_DATES", {date(2026, 10, 21)}):
            events, count = g.build_profile_events([(self.week, [self.course])], "INFO", "GrB")
        self.assertEqual(len(events), 1)
        self.assertEqual(count, 0)

    def test_unconfirmed_empty_week_is_not_enterprise_or_a_holiday_guess(self):
        with patch.object(g, "FORCED_ENTERPRISE_DATES", set()):
            self.assertEqual(g.build_profile_events([(self.week, [])], "INFO", "GrB"), ([], 0))

    def test_confirmed_empty_enterprise_week_and_forced_school_override(self):
        with patch.object(g, "FORCED_ENTERPRISE_DATES", {date(2026, 10, 21)}):
            events, count = g.build_profile_events([(self.week, [])], "INFO", "GrB")
            self.assertEqual(len(events), 5)
            self.assertEqual(count, 1)
            with patch.object(g, "FORCED_SCHOOL_DATES", {date(2026, 10, 19)}):
                self.assertEqual(g.build_profile_events([(self.week, [])], "INFO", "GrB"), ([], 0))

    def test_photonics_tp_never_leaks_into_info(self):
        course = dict(self.course, groups="APP3 PHOT TP")
        self.assertFalse(g.is_course_for_profile(course, "INFO", "GrB"))
        self.assertTrue(g.is_course_for_profile(course, "PHOT", "GrB"))

    def test_specialty_group_pairs_cannot_be_crossed(self):
        course = dict(self.course, groups="APP3 INFO GrA, APP3 ELEC GrB")
        self.assertTrue(g.is_course_for_profile(course, "INFO", "GrA"))
        self.assertTrue(g.is_course_for_profile(course, "ELEC", "GrB"))
        self.assertFalse(g.is_course_for_profile(course, "INFO", "GrB"))
        self.assertFalse(g.is_course_for_profile(course, "ELEC", "GrA"))

    def test_separate_specialty_and_group_constraints(self):
        course = dict(self.course, groups="APP3 & FC1 INFO, APP3 GrB")
        self.assertTrue(g.is_course_for_profile(course, "INFO", "GrB"))
        self.assertFalse(g.is_course_for_profile(course, "PHOT", "GrB"))
        self.assertFalse(g.is_course_for_profile(course, "INFO", "GrA"))

    def test_shared_promotion_group_and_fc1(self):
        for label in ["APP3 & FC1 Promo", "APP3 concernés, ET3 Promo"]:
            self.assertTrue(g.is_course_for_profile({"groups": label}, "INFO", "GrB"))
        self.assertTrue(g.is_course_for_profile({"groups": "APP3 GrA, FC1"}, "INFO", "GrA"))
        self.assertFalse(g.is_course_for_profile({"groups": "APP3 GrA, FC1"}, "INFO", "GrB"))

    def test_cloudflare_530_is_retried(self):
        import io
        import urllib.error
        error = urllib.error.HTTPError("https://example.test", 530, "1033", {}, None)
        with patch.object(g.urllib.request, "urlopen", side_effect=[error, io.BytesIO(b'{}')]) as call, \
                patch.object(g.time_module, "sleep"):
            self.assertEqual(g.get_json("https://example.test"), {})
        self.assertEqual(call.call_count, 2)

    def test_repair_retains_course_uid_and_removes_false_enterprise_and_tp(self):
        school = g.course_to_event(10, self.start, self.course)
        wrong = g.course_to_event(10, self.start, dict(self.course, id="wrong", groups="APP3 PHOT TP"))
        old = g.build_calendar([school, wrong] + g.enterprise_events_for_week(10, self.start, "INFO", "GrB"), "INFO", "GrB")
        with patch.object(g, "FORCED_ENTERPRISE_DATES", {date(2026, 10, 21)}):
            repaired, stats = repair_calendar(old, "INFO", "GrB")
        self.assertEqual(stats, {"school_removed": 1, "enterprise_removed": 5})
        self.assertEqual(repaired, g.build_calendar([school], "INFO", "GrB"))
        self.assertIn(g.stable_uid(school, "INFO", "GrB"), repaired)
        self.assertEqual(repair_calendar(repaired, "INFO", "GrB")[0], repaired)

    def test_repair_retains_confirmed_enterprise_when_no_courses(self):
        old = g.build_calendar(g.enterprise_events_for_week(10, self.start, "INFO", "GrB"), "INFO", "GrB")
        with patch.object(g, "FORCED_ENTERPRISE_DATES", {date(2026, 10, 21)}):
            self.assertEqual(repair_calendar(old, "INFO", "GrB")[0], old)
        with patch.object(g, "FORCED_ENTERPRISE_DATES", set()):
            repaired, stats = repair_calendar(old, "INFO", "GrB")
            self.assertNotIn("BEGIN:VEVENT", repaired)
            self.assertEqual(stats["enterprise_removed"], 5)

    def test_incomplete_ics_rejected(self):
        with self.assertRaises(ValueError):
            repair_calendar("BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nEND:VCALENDAR\r\n", "INFO", "GrB")
