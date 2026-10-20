"""Synchronisation de l'EDT personnel Polyflex, sans dépendance Python externe."""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time as clock
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlencode, urlsplit, urljoin, urlunsplit

import generate_ics as ics

BASE = 'https://polyflex.polytech.universite-paris-saclay.fr'
LOGIN = '/auth/users/signin?redirect=%2Fedt%2Fme%2F'
START = date(2026, 8, 31)
END = date(2027, 8, 30)  # borne exclusive, avant la rentrée suivante
DAYS = ['lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi', 'dimanche']
MONTHS = ['janvier', 'février', 'mars', 'avril', 'mai', 'juin', 'juillet',
          'août', 'septembre', 'octobre', 'novembre', 'décembre']
VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta',
        'param', 'source', 'track', 'wbr'}


@dataclass
class Node:
    tag: str
    attrs: dict = field(default_factory=dict)
    parent: object = None
    children: list = field(default_factory=list)

    @property
    def text(self):
        return ' '.join(' '.join(c if isinstance(c, str) else c.text
                                for c in self.children).split())

    def has_class(self, name):
        return name in self.attrs.get('class', '').split()

    def all(self, predicate):
        result = []
        for child in self.children:
            if isinstance(child, Node):
                if predicate(child):
                    result.append(child)
                result.extend(child.all(predicate))
        return result


class Document(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.root = Node('document')
        self.current = self.root
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        node = Node(tag, dict(attrs), self.current)
        self.current.children.append(node)
        if tag not in VOID:
            self.current = node

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        node = self.current
        while node.parent is not None:
            if node.tag == tag:
                self.current = node.parent
                return
            node = node.parent

    def handle_data(self, data):
        self.current.children.append(data)


def authenticated(doc):
    return bool(doc.all(lambda n: n.tag == 'a' and
                        n.attrs.get('href') == '/auth/users/logout'))


def read_week(html, monday):
    """Parse toutes les cartes desktop ; refuse une page tronquée ou inattendue."""
    doc = Document(html).root
    if not authenticated(doc):
        raise RuntimeError('Session Polyflex expirée ou connexion refusée.')
    expected = f'Semaine du {monday.day:02d} {MONTHS[monday.month - 1]}'
    # Le jour est parfois écrit sans zéro initial.
    text = doc.text.lower()
    if (expected.lower() not in text and
            f'Semaine du {monday.day} {MONTHS[monday.month - 1]}'.lower() not in text):
        raise RuntimeError(f'Polyflex ne présente pas la semaine attendue : {monday}.')
    by_id = {}
    for n in doc.all(lambda n: 'id' in n.attrs):
        by_id.setdefault(n.attrs['id'], []).append(n)
    events = []
    total_boxes = 0
    for day_index, day in enumerate(DAYS):
        headings = by_id.get(day, [])
        if not headings:
            if day_index < 5:
                raise RuntimeError(f'Page Polyflex incomplète : jour {day} absent.')
            continue
        if len(headings) != 1:
            raise RuntimeError(f'Jour Polyflex ambigu : {day}.')
        heading = headings[0]
        current = monday + timedelta(days=day_index)
        if heading.text.lower() != f'{day} {current.day:02d}' and heading.text.lower() != f'{day} {current.day}':
            raise RuntimeError(f'Date Polyflex incohérente : {day}.')
        section = heading.parent
        while section.parent and not (section.has_class('inline-flex') and
                                      section.has_class('w-full')):
            section = section.parent
        if section.parent is None:
            raise RuntimeError('Structure des jours Polyflex modifiée.')
        boxes = section.all(lambda n: n.tag == 'button' and n.has_class('appt-box'))
        total_boxes += len(boxes)
        for box in boxes:
            details = by_id.get(box.attrs.get('data-dropdown-toggle'), [])
            fields = box.all(lambda n: n.tag == 'span' and n.has_class('appt-field'))
            if len(details) != 1 or len(fields) < 3:
                raise RuntimeError('Carte de cours Polyflex incomplète.')
            details = details[0]
            ids = details.all(lambda n: n.tag == 'a' and re.fullmatch(
                r'/attendance-lists/for-appointment/\d+', n.attrs.get('href', '')))
            if len(ids) != 1:
                raise RuntimeError('Identifiant stable du cours Polyflex absent.')
            source_id = ids[0].attrs['href'].rsplit('/', 1)[1]
            match = re.fullmatch(r'(\d{2})h(\d{2}) - (\d{2})h(\d{2})', fields[1].text)
            if not match or not fields[0].text:
                raise RuntimeError('Horaire ou nom de cours Polyflex invalide.')
            sh, sm, eh, em = map(int, match.groups())
            start = datetime.combine(current, time(sh, sm), tzinfo=ics.PARIS)
            end = datetime.combine(current, time(eh, em), tzinfo=ics.PARIS)
            if end <= start:
                raise RuntimeError('Durée de cours Polyflex invalide.')
            metadata = [n.attrs['title'] for n in details.all(lambda n: 'title' in n.attrs)]
            def value(prefix):
                return ', '.join(t[len(prefix):].strip() for t in metadata if t.startswith(prefix))
            events.append({'kind': 'school', 'week_id': monday.isoformat(),
                           'start': start, 'end': end,
                           'source_id': source_id,
                           'course': {'id': source_id, 'name': fields[0].text,
                                      'type': fields[2].text, 'room': value('Salle:'),
                                      'teacher': value('Enseignant(e):'),
                                      'groups': value('Groupe:')}})
    all_boxes = doc.all(lambda n: n.tag == 'button' and n.has_class('appt-box'))
    if len(all_boxes) != total_boxes:
        raise RuntimeError('Des cours Polyflex ne sont rattachés à aucun jour.')
    # Ne jamais confondre un tableau valide et une page d'erreur vide.
    return events


class PolyflexClient:
    """curl utilise les certificats natifs macOS et ceux d'Ubuntu dans Actions.

    Aucun secret dans les arguments, logs ou fichiers persistants. Cookie éphémère
    dans un répertoire privé supprimé à la fin de la collecte.
    """
    def __init__(self, cookie_path):
        self.cookie_path = str(cookie_path)

    def request(self, path, data=None):
        if not path.startswith('/') or path.startswith('//'):
            raise ValueError('Destination Polyflex invalide.')
        url = BASE + path
        for redirect in range(4):
            # Les redirections sont contrôlées AVANT de suivre leur destination,
            # y compris les 307/308 qui pourraient retransmettre le formulaire.
            headers_path = str(Path(self.cookie_path).parent / 'headers')
            command = ['curl', '--silent', '--show-error', '--fail',
                       '--proto', '=https', '--connect-timeout', '15', '--max-time', '40',
                       '--cookie', self.cookie_path, '--cookie-jar', self.cookie_path,
                       '--dump-header', headers_path,
                       '--user-agent', 'PolytechCalendar/3.0', '--write-out', '\n%{http_code}']
            if data is not None:
                command += ['--data-binary', '@-', '--header',
                            'Content-Type: application/x-www-form-urlencoded',
                            '--referer', BASE + LOGIN]
            command += [url]
            for attempt in range(3):
                try:
                    result = subprocess.run(command, input=data, capture_output=True, timeout=45)
                except subprocess.TimeoutExpired:
                    result = None
                if result is not None and result.returncode == 0:
                    break
                message = result.stderr.decode('utf-8', errors='replace') if result else ''
                if attempt == 2 or re.search(r'error: 4\d\d', message):
                    raise RuntimeError('Polyflex indisponible : échec de la requête HTTPS.')
                clock.sleep(2 ** (attempt + 1))
            html, status = result.stdout.decode('utf-8').rsplit('\n', 1)
            if status in {'301', '302', '303', '307', '308'}:
                headers = Path(headers_path).read_text()
                locations = re.findall(r'^location:\s*(.+)$', headers, re.I | re.M)
                if len(locations) != 1:
                    raise RuntimeError('Redirection Polyflex invalide.')
                url = urljoin(url, locations[0].strip())
                parsed = urlsplit(url)
                # Polyflex renvoie actuellement une Location http sur son propre
                # hôte après connexion. Repasser en HTTPS AVANT toute requête.
                if parsed.scheme == 'http' and parsed.netloc == urlsplit(BASE).netloc:
                    url = urlunsplit(parsed._replace(scheme='https'))
                    parsed = urlsplit(url)
                if (parsed.scheme != 'https' or parsed.netloc != urlsplit(BASE).netloc
                        or parsed.username or parsed.password):
                    raise RuntimeError('Redirection hors du service Polyflex refusée.')
                if status in {'301', '302', '303'}:
                    data = None
                continue
            if status != '200':
                raise RuntimeError('Réponse Polyflex inattendue.')
            return html
        raise RuntimeError('Trop de redirections Polyflex.')

    def login(self, username, password):
        doc = Document(self.request(LOGIN)).root
        tokens = doc.all(lambda n: n.tag == 'input' and n.attrs.get('name') == '_csrfToken')
        if len(tokens) != 1 or not tokens[0].attrs.get('value'):
            raise RuntimeError('Formulaire de connexion Polyflex modifié.')
        data = urlencode({'username': username, 'pwd': password,
                          '_csrfToken': tokens[0].attrs['value']}).encode()
        html = self.request(LOGIN, data)
        if not authenticated(Document(html).root):
            raise RuntimeError('Connexion Polyflex refusée. Vérifier les secrets configurés.')
        return html


def collect(client, initial_html, today):
    anchor = today - timedelta(days=today.weekday())
    # Vérifie le lundi avant de calculer les offsets relatifs du site.
    initial_events = read_week(initial_html, anchor)
    result = []
    mondays = []
    current = START
    while current < END:
        offset = (current - anchor).days // 7
        events = initial_events if offset == 0 else read_week(
            client.request('/edt/me/?' + urlencode({'page': offset})), current)
        result.extend(e for e in events if START <= e['start'].date() < END)
        mondays.append(current.isoformat())
        print(f'Polyflex {current} : {len(events)} cours', flush=True)
        current += timedelta(days=7)
    # Un identifiant ne peut pas décrire deux séances contradictoires.
    unique = {}
    for event in result:
        key = event['source_id']
        if key in unique and unique[key] != event:
            raise RuntimeError('Identifiant Polyflex dupliqué avec des données différentes.')
        unique[key] = event
    if not unique:
        raise RuntimeError('Aucun cours sur toute l’année : publication annulée.')
    return list(unique.values()), mondays


def personal_events(school_events, account):
    result = []
    for event in school_events:
        result.append({**event, 'uid': f"polyflex-{account}-{event['source_id']}@polytech-calendar"})
    for event in ics.official_enterprise_events('INFO', 'GrB', school_events):
        if not START <= event['start'].date() < END:
            continue
        # Les plages entreprise peuvent être scindées par les cours. Leur UID
        # distingue les segments sans modifier l'identité des cours Polyflex.
        key = event['start'].isoformat()
        digest = hashlib.sha256(key.encode()).hexdigest()[:20]
        result.append({**event, 'uid': f'entreprise-{account}-{digest}@polytech-calendar'})
    return result


def render(events, previous, now):
    records = {}
    for event in events:
        uid = event['uid']
        fingerprint = hashlib.sha256(json.dumps({
            'start': event['start'].isoformat(), 'end': event['end'].isoformat(),
            'course': event['course'], 'kind': event['kind']
        }, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        old = previous.get(uid)
        if old and old['fingerprint'] == fingerprint:
            record = old
        else:
            record = {'fingerprint': fingerprint, 'created': old['created'] if old else now,
                      'modified': now, 'sequence': old['sequence'] + 1 if old else 0}
        records[uid] = record
        event['dtstamp'] = datetime.fromisoformat(record['created'])
        event['last_modified'] = datetime.fromisoformat(record['modified'])
        event['sequence'] = record['sequence']
    content = ics.build_calendar(events, 'INFO', 'GrB',
                                 calendar_name='Polytech — EDT personnel et entreprise')
    return content, records


def publish(school_events, mondays, username, root=Path('.'), now=None):
    now = now or datetime.now(timezone.utc).isoformat(timespec='seconds')
    account = hashlib.sha256(username.strip().lower().encode()).hexdigest()[:12]
    state_path = root / 'data/polyflex-state.json'
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    if state and state.get('account') != account:
        raise RuntimeError('Le compte Polyflex a changé. Migration explicite requise.')
    events = personal_events(school_events, account)
    content, records = render(events, state.get('events', {}), now)
    school = [e for e in events if e['kind'] == 'school']
    enterprise = [e for e in events if e['kind'] == 'enterprise']
    conflicts = [(a, b) for a in enterprise for b in school
                 if a['start'] < b['end'] and b['start'] < a['end']]
    if conflicts:
        raise RuntimeError('Chevauchement entreprise/cours détecté. Publication annulée.')
    # Les conflits présents dans Polyflex restent visibles, sans supprimer de cours.
    school_conflicts = sum(a['start'] < b['end'] and b['start'] < a['end']
                           for i, a in enumerate(school) for b in school[i+1:])
    status = {'source': 'Polyflex — Mon emploi du temps', 'last_success': now,
              'period_start': START.isoformat(), 'period_end_exclusive': END.isoformat(),
              'weeks_checked': len(mondays), 'courses': len(school),
              'enterprise_slots': len(enterprise), 'school_conflicts': school_conflicts,
              'enterprise_school_conflicts': 0,
              'last_course_date': max(e['start'].date().isoformat() for e in school),
              'feed': 'personal.ics'}
    files = {root / 'docs/personal.ics': content,
             root / 'docs/personal-status.json': json.dumps(status, ensure_ascii=False, indent=2) + '\n',
             state_path: json.dumps({'account': account, 'events': records}, indent=2) + '\n'}
    # Tout est validé en mémoire avant toute écriture. Le déploiement Pages
    # publie ensuite un seul artefact, jamais une collecte partielle.
    for path, value in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + '.tmp')
        temporary.write_text(value, encoding='utf-8', newline='')
        temporary.replace(path)
    print(f"Calendrier personnel : {len(school)} cours, {len(enterprise)} créneaux entreprise, "
          f"{school_conflicts} conflit(s) école dans la source.")
    return status


def main():
    parser = argparse.ArgumentParser(description='Collecter l’EDT personnel dans un dossier privé local.')
    parser.add_argument('--credentials-stdin', action='store_true')
    parser.add_argument('--output-root', type=Path, default=Path.home() / 'Library/Application Support/PolytechCalendarPrivate')
    args = parser.parse_args()
    credentials = json.load(sys.stdin) if args.credentials_stdin else {}
    username = credentials.get('username', os.environ.get('POLYFLEX_USERNAME', ''))
    password = credentials.get('password', os.environ.get('POLYFLEX_PASSWORD', ''))
    if not username or not password:
        raise RuntimeError('Fournir les identifiants Polyflex via l’application privée ou l’entrée standard.')
    today = datetime.now(ics.PARIS).date()
    if today >= END:
        raise RuntimeError('Le calendrier 2026–2027 est terminé. Une nouvelle plaquette est nécessaire pour l’année suivante.')
    with tempfile.TemporaryDirectory(prefix='polyflex-') as temporary:
        client = PolyflexClient(Path(temporary) / 'cookies')
        html = client.login(username, password)
        school_events, mondays = collect(client, html, today)
    args.output_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    publish(school_events, mondays, username, args.output_root)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(f'Synchronisation annulée : {error}', file=sys.stderr)
        sys.exit(1)
