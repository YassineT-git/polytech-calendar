import hashlib
import json
import re
import shutil
import sys
import time as time_module
import urllib.error
import urllib.request
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


BASE_URL = "https://popsedt.minireda.com"
CATEGORY = "app3"
PARIS = ZoneInfo("Europe/Paris")
HTTP_ATTEMPTS = 3
HTTP_TIMEOUT = 30
MAX_CONSECUTIVE_FAILURES = 3

# -----------------------------------------------------------------------------
# Profils APP3 générés
# -----------------------------------------------------------------------------

SPECIALTIES = {
    "ELEC": "Électronique",
    "INFO": "Informatique",
    "MATE": "Matériaux",
    "PHOT": "Photonique",
}

TD_GROUPS = {
    "GrA": "Groupe A",
    "GrB": "Groupe B",
    "GrC": "Groupe C",
}

# Une absence de cours ne prouve pas une semaine entreprise (vacances, EDT
# non publié). Seules les semaines explicitement confirmées sont utilisées.
ENTERPRISE_START = time(9, 0)
ENTERPRISE_END = time(17, 30)

# Ajouter une date d'une semaine entreprise confirmée par le calendrier
# d'alternance. Les cours gardent la priorité, même pour ces semaines.
FORCED_ENTERPRISE_DATES = set()

# Permet de corriger exceptionnellement une détection automatique dans l'autre
# sens. Ajoute simplement une date appartenant à la semaine à forcer en école.
FORCED_SCHOOL_DATES = set()

COMMON_LABELS = {
    "APP3 & FC1 Promo",
    "APP3 concernés",
}


def normalize(text):
    return " ".join(str(text).strip().split()).lower()


COMMON_LABELS_N = {normalize(value) for value in COMMON_LABELS}


# -----------------------------------------------------------------------------
# HTTP / données PoPsEDT
# -----------------------------------------------------------------------------


def get_json(url):
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "PolytechCalendar/2.0"},
    )
    for attempt in range(1, HTTP_ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
            retryable = not isinstance(error, urllib.error.HTTPError) or (
                error.code in {408, 429} or 500 <= error.code <= 599
            )
            if not retryable or attempt == HTTP_ATTEMPTS:
                raise RuntimeError(
                    f"PoPsEDT indisponible : {url} : {error} "
                    f"(après {attempt} tentative(s))."
                ) from error
            delay = 2 ** attempt
            print(f"Nouvelle tentative {attempt + 1}/{HTTP_ATTEMPTS} "
                  f"dans {delay} s : {error}", flush=True)
            time_module.sleep(delay)


def split_groups(groups):
    if not groups:
        return []
    return [
        normalize(group)
        for group in str(groups).split(",")
        if group.strip()
    ]


def is_relevant_app3_label(label):
    return (
        label == "app3"
        or label.startswith("app3 ")
        or label == "fc1"
        or label.startswith("fc1 ")
        or label.startswith("anglais :")
    )


def is_course_for_profile(course, specialty, td_group):
    """Filtre aussi les suffixes ADE (TP, TD...) sans croiser les profils."""
    labels = split_groups(course.get("groups", ""))

    # PoPsEDT conserve les événements sans étiquette de groupe.
    if not labels:
        return True

    # Un événement composé uniquement d'étiquettes communes appartient à tous.
    if all(label in COMMON_LABELS_N for label in labels):
        return True

    relevant = [label for label in labels if is_relevant_app3_label(label)]
    has_common = any(label in COMMON_LABELS_N for label in labels)

    # Évite de récupérer des événements appartenant clairement à une autre promo.
    if not relevant and not has_common:
        return False

    def specialties(label):
        return set(re.findall(r"\b(elec|info|mate|phot)\b", label))

    def groups(label):
        return set(re.findall(r"\bgr\s*([abc])\b", label))

    specialty_labels = [label for label in relevant if specialties(label)]
    matching = [label for label in specialty_labels
                if specialty.lower() in specialties(label)]
    if specialty_labels and not matching:
        return False

    # Les groupes d'une autre spécialité ne doivent pas rendre le cours
    # compatible (APP3 INFO GrA + APP3 ELEC GrB n'est pas INFO GrB).
    group_labels = matching + [label for label in relevant if not specialties(label)]
    specified_groups = set().union(*(groups(label) for label in group_labels))
    if specified_groups and td_group[-1].lower() not in specified_groups:
        return False

    # Les groupes d'anglais restent inclus tant qu'un futur filtre anglais
    # n'est pas sélectionné, comme sur PoPsEDT.
    return True


# -----------------------------------------------------------------------------
# Dates / événements
# -----------------------------------------------------------------------------


def week_monday(week_start):
    return week_start.date() - timedelta(days=week_start.weekday())


def week_contains_any(monday, dates):
    sunday = monday + timedelta(days=6)
    return any(monday <= value <= sunday for value in dates)


def course_to_event(week_id, week_start, course):
    day_index = course.get("dayIndex", 0)
    start = course.get("start")
    end = course.get("end")

    if (isinstance(day_index, bool) or not isinstance(day_index, int)
            or not 1 <= day_index <= 7 or not start or not end):
        return None

    try:
        start_hour, start_minute = map(int, start.split(":"))
        end_hour, end_minute = map(int, end.split(":"))
    except (AttributeError, TypeError, ValueError):
        return None

    if not (0 <= start_hour <= 23 and 0 <= end_hour <= 23
            and 0 <= start_minute <= 59 and 0 <= end_minute <= 59):
        return None

    event_date = week_start + timedelta(days=int(day_index) - 1)
    start_dt = event_date.replace(
        hour=start_hour,
        minute=start_minute,
        second=0,
        microsecond=0,
    )
    end_dt = event_date.replace(
        hour=end_hour,
        minute=end_minute,
        second=0,
        microsecond=0,
    )

    if end_dt <= start_dt:
        return None

    return {
        "kind": "school",
        "week_id": week_id,
        "course": course,
        "start": start_dt,
        "end": end_dt,
    }


def union_duration_hours(events):
    """Calcule les heures sans compter deux fois des événements qui se chevauchent."""
    intervals = sorted(
        (event["start"], event["end"])
        for event in events
        if event["kind"] == "school" and event["start"].weekday() < 5
    )
    if not intervals:
        return 0.0

    total = timedelta(0)
    current_start, current_end = intervals[0]

    for start, end in intervals[1:]:
        if start <= current_end:
            current_end = max(current_end, end)
        else:
            total += current_end - current_start
            current_start, current_end = start, end

    total += current_end - current_start
    return total.total_seconds() / 3600


def is_enterprise_week(week_start, school_events):
    monday = week_monday(week_start)

    if week_contains_any(monday, FORCED_SCHOOL_DATES):
        return False
    # Une semaine école, même partielle, ne devient jamais une semaine
    # entreprise. Ne pas effacer les cours pour faire disparaître un conflit.
    if school_events:
        return False
    return week_contains_any(monday, FORCED_ENTERPRISE_DATES)


def enterprise_events_for_week(week_id, week_start, specialty, td_group):
    monday = week_monday(week_start)
    events = []

    for offset in range(5):
        current_date = monday + timedelta(days=offset)
        start_dt = datetime.combine(current_date, ENTERPRISE_START, tzinfo=PARIS)
        end_dt = datetime.combine(current_date, ENTERPRISE_END, tzinfo=PARIS)
        events.append(
            {
                "kind": "enterprise",
                "week_id": week_id,
                "course": {
                    "id": f"enterprise-{current_date.isoformat()}-{specialty}-{td_group}",
                    "name": "🏢 Entreprise",
                    "type": "Alternance",
                    "room": "",
                    "teacher": "",
                    "groups": f"APP3 {specialty} {td_group}",
                },
                "start": start_dt,
                "end": end_dt,
            }
        )

    return events


# -----------------------------------------------------------------------------
# ICS
# -----------------------------------------------------------------------------


def escape_ics(value):
    if value is None:
        return ""
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace("\r", "")
        .replace("\n", "\\n")
        .replace(";", "\\;")
        .replace(",", "\\,")
    )


def format_utc(dt):
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def stable_uid(event, specialty, td_group):
    course = event["course"]
    source = "|".join(
        [
            specialty,
            td_group,
            str(event["week_id"]),
            str(course.get("id", "")),
            str(course.get("name", "")),
            event["start"].isoformat(),
        ]
    )
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()[:28]
    return f"{digest}@polytech-calendar"


def fold_ics_line(line, limit=73):
    """Plie une ligne ICS sans couper un caractère UTF-8."""
    if len(line.encode("utf-8")) <= limit:
        return [line]

    chunks = []
    current = ""
    current_bytes = 0

    for char in line:
        size = len(char.encode("utf-8"))
        effective_limit = limit if not chunks else limit - 1
        if current and current_bytes + size > effective_limit:
            chunks.append(current)
            current = char
            current_bytes = size
        else:
            current += char
            current_bytes += size

    if current:
        chunks.append(current)

    return [chunks[0]] + [" " + chunk for chunk in chunks[1:]]


def add_ics_line(lines, line):
    lines.extend(fold_ics_line(line))


def build_calendar(profile_events, specialty, td_group):
    specialty_label = SPECIALTIES[specialty]
    group_label = TD_GROUPS[td_group]
    calendar_name = f"Polytech APP3 {specialty} - {group_label}"

    lines = []
    for line in [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:-//Polytech Calendar//APP3 {specialty} {td_group}//FR",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{escape_ics(calendar_name)}",
        "X-WR-TIMEZONE:Europe/Paris",
        "REFRESH-INTERVAL;VALUE=DURATION:PT1H",
        "X-PUBLISHED-TTL:PT1H",
    ]:
        add_ics_line(lines, line)

    for event in sorted(profile_events, key=lambda item: (item["start"], item["end"])):
        course = event["course"]
        name = course.get("name", "Cours Polytech")
        room = course.get("room", "")
        course_type = course.get("type", "")
        teacher = course.get("teacher", "")
        groups = course.get("groups", "")

        description_parts = []
        if event["kind"] == "enterprise":
            description_parts.append("Semaine d'alternance en entreprise")
        else:
            if course_type:
                description_parts.append(str(course_type))
            if teacher:
                description_parts.append(f"Enseignant : {teacher}")
            if groups:
                description_parts.append(f"Groupe : {groups}")

        description = "\n".join(description_parts)

        # DTSTAMP stable : le fichier ne change pas toutes les 30 minutes si
        # l'emploi du temps n'a lui-même pas changé.
        dtstamp = event["start"]

        for line in [
            "BEGIN:VEVENT",
            f"UID:{stable_uid(event, specialty, td_group)}",
            f"DTSTAMP:{format_utc(dtstamp)}",
            f"DTSTART:{format_utc(event['start'])}",
            f"DTEND:{format_utc(event['end'])}",
            f"SUMMARY:{escape_ics(name)}",
            f"LOCATION:{escape_ics(room)}",
            f"DESCRIPTION:{escape_ics(description)}",
            "STATUS:CONFIRMED",
            "TRANSP:OPAQUE",
            "END:VEVENT",
        ]:
            add_ics_line(lines, line)

    add_ics_line(lines, "END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


# -----------------------------------------------------------------------------
# Génération de tous les calendriers
# -----------------------------------------------------------------------------


def fetch_all_weeks():
    weeks_data = get_json(f"{BASE_URL}/api/weeks?category={CATEGORY}")
    weeks = weeks_data.get("weeks") if isinstance(weeks_data, dict) else None
    if not isinstance(weeks, list) or not weeks:
        raise RuntimeError("PoPsEDT n'a renvoyé aucune semaine APP3.")

    week_payloads = []
    failures = []
    consecutive_failures = 0
    seen_ids = set()

    for week in weeks:
        if not isinstance(week, dict):
            raise RuntimeError("PoPsEDT : métadonnées de semaine invalides.")
        week_id = week.get("id")
        start_ms = week.get("startMs")
        if (not isinstance(week_id, int) or isinstance(week_id, bool)
                or not isinstance(start_ms, (int, float))
                or isinstance(start_ms, bool) or week_id in seen_ids):
            raise RuntimeError("PoPsEDT : identifiant ou date de semaine invalide.")
        # Vérifier les dates avant toute écriture de calendrier.
        datetime.fromtimestamp(start_ms / 1000, tz=PARIS)
        seen_ids.add(week_id)

        url = f"{BASE_URL}/api/timetable?category={CATEGORY}&week={week_id}"
        try:
            timetable = get_json(url)
            courses = timetable.get("courses") if isinstance(timetable, dict) else None
            if (timetable.get("error") if isinstance(timetable, dict) else True):
                raise ValueError("PoPsEDT a renvoyé une erreur applicative.")
            if not isinstance(courses, list) or not all(
                isinstance(course, dict) for course in courses
            ):
                raise ValueError("PoPsEDT : liste courses absente ou invalide.")
            week_payloads.append((week, courses))
            consecutive_failures = 0
            print(f"Semaine {week_id}: {len(courses)} événements source")
        except Exception as error:
            failures.append((week_id, str(error)))
            consecutive_failures += 1
            print(f"ERREUR semaine {week_id}: {error}")
            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                raise RuntimeError(
                    "PoPsEDT indisponible : trois semaines consécutives en erreur. "
                    "Arrêt anticipé ; calendriers existants conservés."
                ) from error

    # Protection : une panne ADE/PoPsEDT ne doit pas remplacer le calendrier
    # par des semaines entreprise artificielles.
    if not week_payloads:
        raise RuntimeError("Impossible de récupérer le moindre emploi du temps.")
    if failures:
        raise RuntimeError(
            f"Collecte incomplète ({len(failures)}/{len(weeks)} semaines en erreur). "
            "Génération annulée pour conserver les calendriers existants."
        )

    return week_payloads


def build_profile_events(week_payloads, specialty, td_group):
    result = []
    enterprise_weeks = 0

    for week, courses in week_payloads:
        week_id = week["id"]
        week_start = datetime.fromtimestamp(week["startMs"] / 1000, tz=PARIS)

        selected_courses = [
            course
            for course in courses
            if is_course_for_profile(course, specialty, td_group)
        ]

        school_events = []
        for course in selected_courses:
            event = course_to_event(week_id, week_start, course)
            if event is not None:
                school_events.append(event)

        result.extend(school_events)

        if is_enterprise_week(week_start, school_events):
            enterprise_weeks += 1
            result.extend(
                enterprise_events_for_week(
                    week_id,
                    week_start,
                    specialty,
                    td_group,
                )
            )

    return result, enterprise_weeks


def main():
    print("Récupération de l'EDT APP3 depuis PoPsEDT...")
    week_payloads = fetch_all_weeks()

    output_dir = Path("docs/calendars")
    generated = []
    contents = {}

    for specialty in SPECIALTIES:
        for td_group in TD_GROUPS:
            events, enterprise_weeks = build_profile_events(
                week_payloads,
                specialty,
                td_group,
            )
            content = build_calendar(events, specialty, td_group)
            filename = f"{specialty.lower()}-{td_group.lower()}.ics"
            output = output_dir / filename
            contents[output] = content
            generated.append(output)
            print(
                f"{specialty} {td_group}: {len(events)} événements "
                f"({enterprise_weeks} semaines entreprise) -> {output}"
            )

    # Calculer tous les profils avant de modifier le moindre fichier.
    output_dir.mkdir(parents=True, exist_ok=True)
    for output, content in contents.items():
        temporary = output.with_suffix(".ics.tmp")
        temporary.write_text(content, encoding="utf-8", newline="")
        temporary.replace(output)

    # Compatibilité avec l'ancien lien déjà utilisé : docs/edt.ics continue à
    # fournir INFO Groupe B afin de ne casser aucun abonnement existant.
    legacy_source = output_dir / "info-grb.ics"
    legacy_output = Path("docs/edt.ics")
    shutil.copyfile(legacy_source, legacy_output)

    print(f"\n{len(generated)} calendriers générés.")
    print(f"Lien historique conservé : {legacy_output}")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Échec de la génération : {error}", file=sys.stderr)
        sys.exit(1)
