"""Corrige les ICS déjà publiés sans inventer de nouvelles données PoPsEDT.

Conserve les cours utiles et leurs UID. Retire les événements d'une autre
spécialité et les semaines entreprise non confirmées ou contenant des cours.
"""
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from generate_ics import PARIS, is_course_for_profile, is_enterprise_week


def properties(block):
    unfolded = re.sub(r"\r?\n[ \t]", "", block)
    return {line.split(":", 1)[0]: line.split(":", 1)[1]
            for line in unfolded.splitlines() if ":" in line}


def unescape(value):
    # Une seule passe : un antislash littéral suivi de n reste littéral.
    return re.sub(r"\\([nN,;\\])", lambda m: "\n" if m[1] in "nN" else m[1], value)


def repair_calendar(text, specialty, td_group):
    if not text.startswith("BEGIN:VCALENDAR") or not text.rstrip().endswith("END:VCALENDAR"):
        raise ValueError("Fichier ICS incomplet ; réparation annulée.")
    records = []
    position = 0
    for match in re.finditer(r"BEGIN:VEVENT\r?\n.*?END:VEVENT\r?\n", text, re.S):
        if position and match.start() != position:
            raise ValueError("Structure ICS inattendue entre deux événements.")
        records.append((match.group(), properties(match.group())))
        position = match.end()
    if not records:
        # Un calendrier explicitement vide est valide.
        if "BEGIN:VEVENT" in text:
            raise ValueError("Événement ICS incomplet.")
        return text, {"school_removed": 0, "enterprise_removed": 0}
    header = text[:text.index("BEGIN:VEVENT")]
    footer = text[position:]
    if footer.strip() != "END:VCALENDAR":
        raise ValueError("Fin de calendrier inattendue ; réparation annulée.")

    school = []
    enterprise = []
    stats = {"school_removed": 0, "enterprise_removed": 0}
    for block, fields in records:
        start = datetime.strptime(fields["DTSTART"], "%Y%m%dT%H%M%SZ").replace(
            tzinfo=timezone.utc).astimezone(PARIS)
        monday = start.date() - timedelta(days=start.weekday())
        if unescape(fields.get("SUMMARY", "")) == "🏢 Entreprise":
            enterprise.append((block, start, monday))
            continue
        description = unescape(fields.get("DESCRIPTION", ""))
        groups = next((line[len("Groupe : "):] for line in description.splitlines()
                       if line.startswith("Groupe : ")), "")
        if is_course_for_profile({"groups": groups}, specialty, td_group):
            school.append((block, monday))
        else:
            stats["school_removed"] += 1

    school_weeks = {monday for _, monday in school}
    kept = {block for block, _ in school}
    for block, start, monday in enterprise:
        if monday not in school_weeks and is_enterprise_week(start, []):
            kept.add(block)
        else:
            stats["enterprise_removed"] += 1
    return header + "".join(block for block, _ in records if block in kept) + footer, stats


def repair_existing(root=Path("docs")):
    planned = {}
    for path in sorted((root / "calendars").glob("*.ics")):
        specialty, group = path.stem.split("-")
        content, stats = repair_calendar(path.read_bytes().decode("utf-8"),
                                         specialty.upper(), "Gr" + group[-1].upper())
        planned[path] = content.encode("utf-8")
        print(path.name, stats)
    alias = root / "calendars" / "info-grb.ics"
    if alias not in planned:
        raise ValueError("INFO Groupe B absent ; aucun fichier modifié.")
    planned[root / "edt.ics"] = planned[alias]
    for path, data in planned.items():
        temporary = path.with_suffix(".ics.tmp")
        temporary.write_bytes(data)
        temporary.replace(path)
    print("Correction des fichiers existants terminée. Les cours ne sont pas actualisés depuis PoPsEDT.")


if __name__ == "__main__":
    repair_existing()
