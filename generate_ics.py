import json
import urllib.request
import hashlib
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path


BASE_URL = "https://popsedt.minireda.com"

CATEGORY = "app3"

# Ton profil
SPECIALTY = "INFO"
TD_GROUP = "GrB"

PARIS = ZoneInfo("Europe/Paris")


# ---------------------------------------------------------
# Requête HTTP
# ---------------------------------------------------------

def get_json(url):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "PolytechCalendar/1.0"
        }
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


# ---------------------------------------------------------
# Outils de filtrage
# ---------------------------------------------------------

def normalize(text):
    return " ".join(str(text).strip().split()).lower()


COMMON_LABELS = {
    normalize("APP3 & FC1 Promo"),
    normalize("APP3 concernés"),
}


INFO_LABELS = {
    normalize(x)
    for x in [
        "APP3 INFO",
        "APP3 & FC1 INFO",
        "FC1 INFO",

        "APP3 INFO GrA",
        "APP3 INFO GrB",
        "APP3 INFO GrC",

        "APP3 & FC1 INFO GrA",
        "APP3 & FC1 INFO GrB",
        "APP3 & FC1 INFO GrC",
    ]
}


OTHER_SPECIALTIES = {
    "elec",
    "mate",
    "phot",
}


GROUP_B_LABELS = {
    normalize(x)
    for x in [
        "APP3 GrB",
        "APP3 & FC1 GrB",

        "APP3 ELEC GrB",
        "APP3 INFO GrB",
        "APP3 MATE GrB",
        "APP3 PHOT GrB",

        "APP3 & FC1 ELEC GrB",
        "APP3 & FC1 INFO GrB",
        "APP3 & FC1 MATE GrB",
        "APP3 & FC1 PHOT GrB",
    ]
}


def split_groups(groups):
    if not groups:
        return []

    return [
        normalize(group)
        for group in str(groups).split(",")
        if group.strip()
    ]


def is_course_for_me(course):
    groups = split_groups(course.get("groups", ""))

    # Aucun groupe indiqué :
    # PoPsEDT conserve ce type de cours.
    if not groups:
        return True

    # Cours commun à toute la promotion APP3/FC1
    if any(group in COMMON_LABELS for group in groups):
        return True

    # On ne garde que les données APP3 / FC1 / anglais pertinentes.
    relevant = []

    for group in groups:
        if (
            group.startswith("app3 ")
            or group == "app3"
            or group.startswith("fc1 ")
            or group == "fc1"
            or group.startswith("anglais :")
        ):
            relevant.append(group)

    if not relevant:
        return False

    # -----------------------------------------------------
    # Filtre spécialité INFO
    # -----------------------------------------------------

    speciality_labels = []

    for group in relevant:
        if any(
            word in group.split()
            for word in ["info", "elec", "mate", "phot"]
        ):
            speciality_labels.append(group)

    if speciality_labels:
        if not any("info" in group.split() for group in speciality_labels):
            return False

    # -----------------------------------------------------
    # Filtre groupe B
    # -----------------------------------------------------

    explicit_groups = []

    for group in relevant:
        if (
            " gra" in f" {group}"
            or " grb" in f" {group}"
            or " grc" in f" {group}"
            or group == "fc1"
        ):
            explicit_groups.append(group)

    if explicit_groups:
        if not any(
            group in GROUP_B_LABELS
            or " grb" in f" {group}"
            for group in explicit_groups
        ):
            return False

    return True


# ---------------------------------------------------------
# ICS
# ---------------------------------------------------------

def escape_ics(value):
    if value is None:
        return ""

    return (
        str(value)
        .replace("\\", "\\\\")
        .replace("\n", "\\n")
        .replace("\r", "")
        .replace(";", "\\;")
        .replace(",", "\\,")
    )


def format_utc(dt):
    return (
        dt.astimezone(timezone.utc)
        .strftime("%Y%m%dT%H%M%SZ")
    )


def stable_uid(week_id, course):
    source = "|".join([
        str(week_id),
        str(course.get("id", "")),
        str(course.get("name", "")),
        str(course.get("dayIndex", "")),
    ])

    digest = hashlib.sha256(
        source.encode("utf-8")
    ).hexdigest()[:24]

    return f"{digest}@polytech-calendar"


# ---------------------------------------------------------
# Génération
# ---------------------------------------------------------

def main():

    print("Récupération des semaines...")

    weeks_data = get_json(
        f"{BASE_URL}/api/weeks?category={CATEGORY}"
    )

    weeks = weeks_data.get("weeks", [])

    print(f"{len(weeks)} semaines trouvées.")

    events = []

    for week in weeks:

        week_id = week["id"]

        print(f"Semaine {week_id}...")

        url = (
            f"{BASE_URL}/api/timetable"
            f"?category={CATEGORY}"
            f"&week={week_id}"
        )

        try:
            timetable = get_json(url)
        except Exception as error:
            print(
                f"Impossible de récupérer "
                f"la semaine {week_id}: {error}"
            )
            continue

        courses = timetable.get("courses", [])

        selected = [
            course
            for course in courses
            if is_course_for_me(course)
        ]

        print(
            f"  {len(courses)} cours → "
            f"{len(selected)} conservés"
        )

        start_ms = week.get("startMs")

        if start_ms is None:
            continue

        week_start = datetime.fromtimestamp(
            start_ms / 1000,
            tz=PARIS
        )

        for course in selected:

            day_index = course.get("dayIndex", 0)
            start = course.get("start")
            end = course.get("end")

            if not day_index or not start or not end:
                continue

            try:
                start_hour, start_minute = map(
                    int,
                    start.split(":")
                )

                end_hour, end_minute = map(
                    int,
                    end.split(":")
                )

            except ValueError:
                continue

            event_date = (
                week_start
                + timedelta(days=day_index - 1)
            )

            start_dt = event_date.replace(
                hour=start_hour,
                minute=start_minute,
                second=0,
                microsecond=0
            )

            end_dt = event_date.replace(
                hour=end_hour,
                minute=end_minute,
                second=0,
                microsecond=0
            )

            if end_dt <= start_dt:
                continue

            events.append(
                (
                    week_id,
                    course,
                    start_dt,
                    end_dt
                )
            )

    print(f"{len(events)} événements au total.")

    now = datetime.now(timezone.utc)

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Polytech Paris-Saclay//APP3 INFO Groupe B//FR",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:Polytech APP3 INFO - Groupe B",
        "X-WR-TIMEZONE:Europe/Paris",
    ]

    for week_id, course, start_dt, end_dt in events:

        name = course.get(
            "name",
            "Cours Polytech"
        )

        room = course.get(
            "room",
            ""
        )

        course_type = course.get(
            "type",
            ""
        )

        teacher = course.get(
            "teacher",
            ""
        )

        groups = course.get(
            "groups",
            ""
        )

        description_parts = []

        if course_type:
            description_parts.append(
                course_type
            )

        if teacher:
            description_parts.append(
                f"Enseignant : {teacher}"
            )

        if groups:
            description_parts.append(
                f"Groupe : {groups}"
            )

        description = "\n".join(
            description_parts
        )

        lines.extend([
            "BEGIN:VEVENT",

            f"UID:{stable_uid(week_id, course)}",

            f"DTSTAMP:{format_utc(now)}",

            f"DTSTART:{format_utc(start_dt)}",

            f"DTEND:{format_utc(end_dt)}",

            f"SUMMARY:{escape_ics(name)}",

            f"LOCATION:{escape_ics(room)}",

            f"DESCRIPTION:{escape_ics(description)}",

            "STATUS:CONFIRMED",

            "END:VEVENT",
        ])

    lines.append(
        "END:VCALENDAR"
    )

    output = Path("docs/edt.ics")

    output.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    output.write_text(
        "\r\n".join(lines) + "\r\n",
        encoding="utf-8"
    )

    print(
        f"Calendrier généré : {output}"
    )


if __name__ == "__main__":
    main()