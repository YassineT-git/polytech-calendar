import copy
import json
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

import polyflex_sync as p

MONDAY = date(2026, 10, 19)


def page(monday=MONDAY, course=True):
    days = []
    for index, day in enumerate(p.DAYS[:5]):
        box = ''
        if index == 0 and course:
            box = '''<button class="appt-box" data-dropdown-toggle="cls1">
              <span class="appt-field">Bases de données &amp; outils</span>
              <span class="appt-field">08h15 - 10h15</span>
              <span class="appt-field">TD</span></button>'''
        days.append(f'<div class="inline-flex flex-col w-full"><span id="{day}">'
                    f'{day.capitalize()} {(monday + timedelta(days=index)).day}</span>{box}</div>')
    details = '''<div id="cls1"><span title="Salle: B009">B009</span>
       <span title="Enseignant(e): Prof É">Prof É</span>
       <span title="Groupe: APP3 &amp; FC1 INFO">INFO</span>
       <a href="/attendance-lists/for-appointment/2170">Liste de présence</a></div>'''
    return (f'<a href="/auth/users/logout">Déconnexion</a>'
            f'<div>Semaine du {monday.day} {p.MONTHS[monday.month-1].capitalize()}</div>'
            + details + ''.join(days))


class ParsingTests(unittest.TestCase):
    def test_exact_personal_course_and_metadata(self):
        [event] = p.read_week(page(), MONDAY)
        self.assertEqual(event['source_id'], '2170')
        self.assertEqual(event['course']['groups'], 'APP3 & FC1 INFO')
        self.assertEqual(event['course']['teacher'], 'Prof É')
        self.assertEqual(event['course']['name'], 'Bases de données & outils')
        self.assertEqual(p.ics.format_utc(event['start']), '20261019T061500Z')

    def test_empty_week_is_valid(self):
        self.assertEqual(p.read_week(page(course=False), MONDAY), [])

    def test_login_error_and_truncated_week_rejected(self):
        for html in ['<title>Connexion</title>', '<html>502 Bad Gateway</html>',
                     page().replace('id="vendredi"', 'id="missing"'),
                     page().replace('08h15 - 10h15', '18h15 - 10h15'),
                     page().replace('for-appointment/2170', 'not-an-id')]:
            with self.subTest(html=html[:50]), self.assertRaises(RuntimeError):
                p.read_week(html, MONDAY)

    def test_wrong_week_rejected_including_new_year(self):
        with self.assertRaises(RuntimeError):
            p.read_week(page(), MONDAY + timedelta(days=7))
        monday = date(2026, 12, 28)
        self.assertEqual(len(p.read_week(page(monday), monday)), 1)

    def test_unassigned_box_is_not_silently_dropped(self):
        with self.assertRaisesRegex(RuntimeError, 'rattachés'):
            p.read_week(page() + '<button class="appt-box"></button>', MONDAY)

    def test_collection_stops_on_one_invalid_week(self):
        class Client:
            def request(self, path):
                return '<html>Maintenance</html>'
        with self.assertRaises(RuntimeError):
            p.collect(Client(), page(), MONDAY)


class TransportTests(unittest.TestCase):
    def test_external_redirect_rejected_before_credentials_are_forwarded(self):
        with tempfile.TemporaryDirectory() as td:
            client = p.PolyflexClient(Path(td) / 'cookies')
            def response(command, **kwargs):
                Path(td, 'headers').write_text('HTTP/1.1 307\nLocation: https://example.org/steal\n')
                return CompletedProcess(command, 0, b'\n307', b'')
            with patch.object(p.subprocess, 'run', side_effect=response) as call:
                with self.assertRaisesRegex(RuntimeError, 'hors du service'):
                    client.request(p.LOGIN, b'pwd=secret')
                self.assertEqual(call.call_count, 1)
                self.assertNotIn('secret', ' '.join(call.call_args.args[0]))
                self.assertNotIn('--location', call.call_args.args[0])

    def test_same_host_http_redirect_is_upgraded_before_request(self):
        with tempfile.TemporaryDirectory() as td:
            client = p.PolyflexClient(Path(td) / 'cookies')
            commands = []
            def response(command, **kwargs):
                commands.append((command, kwargs.get('input')))
                if len(commands) == 1:
                    Path(td, 'headers').write_text('HTTP/1.1 302\nLocation: http://polyflex.polytech.universite-paris-saclay.fr/edt/me/\n')
                    return CompletedProcess(command, 0, b'\n302', b'')
                return CompletedProcess(command, 0, b'EDT\n200', b'')
            with patch.object(p.subprocess, 'run', side_effect=response):
                self.assertEqual(client.request(p.LOGIN, b'pwd=secret'), 'EDT')
            self.assertEqual(commands[1][0][-1], p.BASE + '/edt/me/')
            self.assertIsNone(commands[1][1])

    def test_network_outage_is_bounded_and_errors_do_not_echo_password(self):
        with tempfile.TemporaryDirectory() as td:
            client = p.PolyflexClient(Path(td) / 'cookies')
            failure = CompletedProcess([], 7, b'', b'network error secret')
            with patch.object(p.subprocess, 'run', return_value=failure) as call, \
                    patch.object(p.clock, 'sleep'):
                with self.assertRaisesRegex(RuntimeError, '^Polyflex indisponible'):
                    client.request(p.LOGIN, b'pwd=secret')
                self.assertEqual(call.call_count, 3)


class PublishingTests(unittest.TestCase):
    def test_moved_and_renamed_course_keeps_uid_and_increments_sequence(self):
        events = p.personal_events(p.read_week(page(), MONDAY), 'account')[:1]
        first, state = p.render(copy.deepcopy(events), {}, '2026-10-20T10:00:00+00:00')
        second, unchanged = p.render(copy.deepcopy(events), state, '2026-10-20T11:00:00+00:00')
        self.assertEqual(first, second)
        self.assertEqual(state, unchanged)
        events[0]['start'] += timedelta(hours=1)
        events[0]['end'] += timedelta(hours=1)
        events[0]['course']['name'] = 'Nouveau nom'
        third, new_state = p.render(events, state, '2026-10-20T12:00:00+00:00')
        self.assertIn('SEQUENCE:1', third)
        self.assertIn('UID:' + events[0]['uid'], third)
        self.assertEqual(next(iter(state)), next(iter(new_state)))
        self.assertIn('LAST-MODIFIED:20261020T120000Z', third)

    def test_official_dates_no_school_enterprise_overlap_or_pre_enrolment(self):
        school = p.read_week(page(date(2026, 9, 28)), date(2026, 9, 28))
        events = p.personal_events(school, 'account')
        work = [e for e in events if e['kind'] == 'enterprise']
        self.assertTrue(work)
        for event in work:
            self.assertGreaterEqual(event['start'].date(), p.START)
            self.assertLess(event['end'].date(), p.END)
            self.assertLess(event['start'].weekday(), 5)
            self.assertNotIn(event['start'].date().isoformat(), p.ics.OFFICIAL_SCHEDULE['school_days'])
            self.assertFalse(any(event['start'] < c['end'] and c['start'] < event['end'] for c in school))

    def test_other_feeds_untouched_and_account_change_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / 'docs/calendars').mkdir(parents=True)
            legacy = root / 'docs/edt.ics'
            legacy.write_bytes(b'legacy')
            school = p.read_week(page(), MONDAY)
            status = p.publish(school, [str(MONDAY)], 'person@example.test', root)
            self.assertEqual(legacy.read_bytes(), b'legacy')
            self.assertEqual(status['enterprise_school_conflicts'], 0)
            self.assertEqual(status['courses'], 1)
            content = (root / 'docs/personal.ics').read_bytes()
            self.assertNotIn(b'person@example.test', content)
            self.assertTrue(all(len(line) <= 75 for line in content.split(b'\r\n')))
            self.assertNotIn(b'\n', content.replace(b'\r\n', b''))
            with self.assertRaisesRegex(RuntimeError, 'compte Polyflex a changé'):
                p.publish(school, [str(MONDAY)], 'other@example.test', root)
            self.assertEqual(content, (root / 'docs/personal.ics').read_bytes())

    def test_source_overlap_is_reported_without_erasing_courses(self):
        with tempfile.TemporaryDirectory() as td:
            school = p.read_week(page(), MONDAY)
            school.append({**school[0], 'source_id': 'second'})
            status = p.publish(school, [str(MONDAY)], 'a@example.test', Path(td))
            self.assertEqual(status['school_conflicts'], 1)
            self.assertEqual(status['courses'], 2)


if __name__ == '__main__':
    unittest.main()
