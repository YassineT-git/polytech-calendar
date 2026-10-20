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
        self.assertEqual([e["kind"] for e in events if e["start"].date() == date(2026, 10, 19)], ["school"])

    def test_school_takes_priority_over_forced_enterprise(self):
        with patch.object(g, "FORCED_ENTERPRISE_DATES", {date(2026, 10, 21)}):
            events, count = g.build_profile_events([(self.week, [self.course])], "INFO", "GrB")
        self.assertEqual([e["kind"] for e in events if e["start"].date() == date(2026, 10, 19)], ["school"])

    def test_unconfirmed_empty_week_is_not_enterprise_or_a_holiday_guess(self):
        with patch.object(g, "FORCED_ENTERPRISE_DATES", set()):
            self.assertEqual(g.build_profile_events([(self.week, [])], "PHOT", "GrB"), ([], 0))

    def test_confirmed_empty_enterprise_week_and_forced_school_override(self):
        with patch.object(g, "FORCED_ENTERPRISE_DATES", {date(2026, 10, 21)}):
            events, count = g.build_profile_events([(self.week, [])], "PHOT", "GrB")
            self.assertEqual(len(events), 5)
            self.assertEqual(count, 1)
            with patch.object(g, "FORCED_SCHOOL_DATES", {date(2026, 10, 19)}):
                self.assertEqual(g.build_profile_events([(self.week, [])], "PHOT", "GrB"), ([], 0))

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
        repaired, stats = repair_calendar(old, "INFO", "GrB")
        self.assertEqual(stats["school_removed"], 1)
        self.assertEqual(stats["enterprise_removed"], 5)
        self.assertIn(g.stable_uid(school, "INFO", "GrB"), repaired)
        self.assertNotIn(g.stable_uid(wrong, "INFO", "GrB"), repaired)
        self.assertEqual(repair_calendar(repaired, "INFO", "GrB")[0], repaired)

    def test_repair_retains_confirmed_enterprise_when_no_courses(self):
        old = g.build_calendar(g.enterprise_events_for_week(10, self.start, "PHOT", "GrB"), "PHOT", "GrB")
        with patch.object(g, "FORCED_ENTERPRISE_DATES", {date(2026, 10, 21)}):
            self.assertEqual(repair_calendar(old, "PHOT", "GrB")[0], old)
        with patch.object(g, "FORCED_ENTERPRISE_DATES", set()):
            repaired, stats = repair_calendar(old, "PHOT", "GrB")
            self.assertNotIn("BEGIN:VEVENT", repaired)
            self.assertEqual(stats["enterprise_removed"], 5)

    def test_incomplete_ics_rejected(self):
        with self.assertRaises(ValueError):
            repair_calendar("BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nEND:VCALENDAR\r\n", "INFO", "GrB")


class OfficialCalendarTests(unittest.TestCase):
    def test_pdf_colors_override_incorrect_transcription(self):
        school = set(g.OFFICIAL_SCHEDULE["school_days"])
        enterprise = set(g.OFFICIAL_SCHEDULE["enterprise_days"])
        for value in ["2026-09-14", "2026-10-12", "2026-10-19", "2027-01-04"]:
            self.assertIn(value, school)
            self.assertNotIn(value, enterprise)
        self.assertIn("2026-11-02", enterprise)
        self.assertIn("2027-06-14", school)  # Note des soutenances prioritaire.
        self.assertNotIn("2027-06-14", enterprise)

    def test_no_weekends_holidays_or_school_in_official_enterprise_days(self):
        enterprise = set(g.OFFICIAL_SCHEDULE["enterprise_days"])
        self.assertFalse(enterprise & set(g.OFFICIAL_SCHEDULE["school_days"]))
        self.assertFalse(enterprise & set(g.OFFICIAL_SCHEDULE["holidays"]))
        self.assertTrue(all(date.fromisoformat(day).weekday() < 5 for day in enterprise))

    def test_meeting_splits_only_the_enterprise_interval_without_overlap(self):
        start = datetime(2026, 10, 1, 13, 30, tzinfo=g.PARIS)
        end = datetime(2026, 10, 1, 17, 30, tzinfo=g.PARIS)
        events = g.official_enterprise_events("INFO", "GrB", [{"start": start, "end": end}])
        day = [e for e in events if e["start"].date() == start.date()]
        self.assertEqual(len(day), 1)
        self.assertEqual(day[0]["start"].hour, 9)
        self.assertEqual(day[0]["end"], start)
        self.assertTrue(all(e["end"] <= start or e["start"] >= end for e in day))

    def test_all_day_course_removes_enterprise_for_that_day_only(self):
        day = date(2026, 11, 2)
        events = g.official_enterprise_events("INFO", "GrB", [{
            "start": datetime(2026, 11, 2, 8, tzinfo=g.PARIS),
            "end": datetime(2026, 11, 2, 19, tzinfo=g.PARIS)}])
        self.assertFalse(any(e["start"].date() == day for e in events))
        self.assertTrue(any(e["start"].date() == date(2026, 11, 3) for e in events))

    def test_iim_calendar_does_not_apply_to_other_specialties(self):
        for specialty in ["ELEC", "MATE", "PHOT"]:
            self.assertEqual(g.official_enterprise_events(specialty, "GrB", []), [])

    def test_official_enterprise_can_be_added_to_a_valid_empty_calendar(self):
        text = g.build_calendar([], "INFO", "GrB")
        repaired, stats = repair_calendar(text, "INFO", "GrB")
        self.assertGreater(stats["official_enterprise_added"], 0)
        self.assertIn("SUMMARY:🏢 Entreprise", repaired)
        self.assertEqual(repair_calendar(repaired, "INFO", "GrB")[0], repaired)
