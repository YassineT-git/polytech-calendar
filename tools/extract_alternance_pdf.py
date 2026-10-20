"""Extraction vérifiée des cellules de l'année 1, page 7 du catalogue IIM.

Outil de maintenance uniquement (dépendance pdfplumber). Les coordonnées sont
propres à l'édition 2026-2027 ; refuser toute couleur inconnue.
"""
import calendar
import hashlib
import json
import sys
from datetime import date
from pathlib import Path

import pdfplumber


# Centres des colonnes « 1 » relevés dans la page originale.
COLUMNS = [49.93, 111.01, 170.77, 232.12, 293.44, 354.78,
           416.10, 477.42, 538.77, 600.09, 661.41, 722.75, 784.07]


def rgb(value):
    return tuple(round(v, 2) for v in value) if isinstance(value, (list, tuple)) else (value,) * 3


def cell_color(page, x, y, allow_blank=False):
    matches = [r for r in page.rects if r.get("fill") and
               r["x0"] <= x <= r["x1"] and r["y0"] <= y <= r["y1"]]
    if not matches and allow_blank:
        return (1, 1, 1)
    if len(matches) != 1:
        raise ValueError(f"Cellule ambiguë à {x}, {y}: {len(matches)} rectangles")
    return rgb(matches[0]["non_stroking_color"])


def extract(path):
    result = {"profile": "INFO", "academic_year": "2026-2027", "training_year": 1,
              "source": {"file": path.name, "page": 7, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()},
              "enterprise_days": [], "school_days": [], "holidays": [], "school_closed_days": []}
    with pdfplumber.open(path) as pdf:
        page = pdf.pages[6]
        if "Spécialité IIM" not in page.extract_text():
            raise ValueError("Page calendrier IIM introuvable")
        for month_index, x in enumerate(COLUMNS):
            year = 2026 if month_index < 5 else 2027
            month = (7 + month_index) % 12 + 1
            for day in range(1, calendar.monthrange(year, month)[1] + 1):
                current = date(year, month, day)
                y = 446.0 - (day - 1) * 9.243
                color = cell_color(page, x, y, allow_blank=True)
                if current.weekday() >= 5:
                    continue
                key = None
                if color == (1.0, 1.0, 0.6):
                    key = "enterprise_days"
                elif color in {(1.0, 0.6, 0.8), (0.22, 0.67, 0.44), (0.2, 0.6, 0.4)}:
                    key = "school_days"
                elif color in {(1.0, 0.75, 0.0), (1.0, 0.77, 0.14)}:
                    key = "holidays"
                elif color in {(1, 1, 1), (0.95, 0.94, 0.93)}:
                    # Les soutenances sont précisées au pied de page.
                    if date(2027, 6, 14) <= current <= date(2027, 6, 18):
                        key = "school_days"
                elif color in {(0.0, 0.68, 0.94), (0.0, 0.69, 0.94)}:
                    key = "school_closed_days"
                else:
                    raise ValueError(f"Couleur inconnue {current}: {color}")
                # La note sous le tableau précise les soutenances de première
                # année à l'école, même si la cellule est jaune.
                if date(2027, 6, 14) <= current <= date(2027, 6, 18):
                    key = "school_days"
                if key:
                    result[key].append(current.isoformat())
                # La colonne des dates signale la fermeture de l'école.
                date_color = cell_color(page, x - 12, y, allow_blank=True)
                if date_color in {(0.0, 0.68, 0.94), (0.0, 0.69, 0.94)}:
                    if current.isoformat() not in result["school_closed_days"]:
                        result["school_closed_days"].append(current.isoformat())
    return result


if __name__ == "__main__":
    data = extract(Path(sys.argv[1]))
    Path(sys.argv[2]).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    print({k: len(data[k]) for k in ["enterprise_days", "school_days", "holidays", "school_closed_days"]})
