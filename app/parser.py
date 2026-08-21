"""Parse the weekly cafe menu .docx into structured day data."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

import docx

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]

LABEL_MAP = {
    "breakfast": "Breakfast",
    "vegetarian soup du jour": "Veg Soup Du Jour",
    "non-vegetarian soup du jour": "Soup Du Jour",
    "main entrée": "Main Entrée",
    "main entree": "Main Entrée",
    "veggie entrée": "Veggie Entrée",
    "veggie entree": "Veggie Entrée",
}


@dataclass
class MenuRow:
    label: str
    item: str
    emphasis: bool = False
    muted: bool = False


@dataclass
class DayMenu:
    day_name: str
    menu_date: date
    rows: list[MenuRow] = field(default_factory=list)


class MenuParseError(Exception):
    pass


def _iter_paragraph_lines(doc: docx.Document) -> list[str]:
    lines = []
    for p in doc.paragraphs:
        text = p.text.strip()
        if text:
            lines.append(text)
    return lines


def _split_label_item(line: str) -> tuple[str, str] | None:
    if ":" not in line:
        return None
    label, _, item = line.partition(":")
    label = label.strip().rstrip(":").strip()
    item = item.strip()
    if not label or not item:
        return None
    return label, item


def parse_menu_docx(path: str, start_monday: date) -> list[DayMenu]:
    """Parse the .docx into one DayMenu per weekday (Mon-Fri).

    start_monday is the user-confirmed date of Monday; Tue-Fri are
    start_monday + 1..4 days.
    """
    doc = docx.Document(path)
    lines = _iter_paragraph_lines(doc)

    # Split lines into per-day blocks using day-name lines as delimiters.
    day_blocks: dict[str, list[str]] = {}
    current_day = None
    for line in lines:
        stripped = line.strip()
        matched_day = next((d for d in DAY_NAMES if stripped.lower() == d.lower()), None)
        if matched_day:
            current_day = matched_day
            day_blocks[current_day] = []
            continue
        if current_day:
            day_blocks[current_day].append(line)

    missing = [d for d in DAY_NAMES if d not in day_blocks]
    if missing:
        raise MenuParseError(
            f"Could not find day sections for: {', '.join(missing)}. "
            "Check that the document has a line reading exactly e.g. 'Monday' "
            "before each day's items."
        )

    days: list[DayMenu] = []
    for i, day_name in enumerate(DAY_NAMES):
        menu_date = start_monday + timedelta(days=i)
        rows = _parse_day_block(day_name, day_blocks[day_name])
        days.append(DayMenu(day_name=day_name, menu_date=menu_date, rows=rows))

    return days


def _parse_day_block(day_name: str, block_lines: list[str]) -> list[MenuRow]:
    parsed: dict[str, str] = {}
    has_sushi = False

    for line in block_lines:
        if line.strip().lower() == "assorted sushi":
            has_sushi = True
            continue
        split = _split_label_item(line)
        if not split:
            continue
        raw_label, item = split
        key = raw_label.lower()
        if key in LABEL_MAP:
            parsed[LABEL_MAP[key]] = item

    rows: list[MenuRow] = []

    breakfast = parsed.get("Breakfast")
    if breakfast is None:
        raise MenuParseError(f"{day_name}: missing 'Breakfast' line.")
    rows.append(MenuRow(label="Breakfast", item=breakfast))

    if day_name == "Friday":
        veg = parsed.get("Veg Soup Du Jour")
        nonveg = parsed.get("Soup Du Jour")
        if veg and nonveg:
            raise MenuParseError(
                "Friday: found both veg and non-veg soup lines; expected only one."
            )
        if veg:
            rows.append(MenuRow(label="Veg Soup Du Jour", item=veg))
        elif nonveg:
            rows.append(MenuRow(label="Soup Du Jour", item=nonveg))
        else:
            raise MenuParseError("Friday: no soup line found (expected exactly one).")
    else:
        veg = parsed.get("Veg Soup Du Jour")
        nonveg = parsed.get("Soup Du Jour")
        if not veg:
            raise MenuParseError(f"{day_name}: missing 'Vegetarian Soup Du Jour' line.")
        if not nonveg:
            raise MenuParseError(f"{day_name}: missing 'Non-Vegetarian Soup Du Jour' line.")
        rows.append(MenuRow(label="Veg Soup Du Jour", item=veg))
        rows.append(MenuRow(label="Soup Du Jour", item=nonveg))

    main_entree = parsed.get("Main Entrée")
    if main_entree is None:
        raise MenuParseError(f"{day_name}: missing 'Main Entrée' line.")
    rows.append(MenuRow(label="Main Entrée", item=main_entree, emphasis=True))

    veggie_entree = parsed.get("Veggie Entrée")
    if veggie_entree is None:
        raise MenuParseError(f"{day_name}: missing 'Veggie Entrée' line.")
    rows.append(MenuRow(label="Veggie Entrée", item=veggie_entree, emphasis=True))

    if day_name == "Wednesday":
        if not has_sushi:
            raise MenuParseError(
                "Wednesday: missing standalone 'Assorted Sushi' line after Veggie Entrée."
            )
        rows.append(MenuRow(label="Assorted Sushi", item="Assorted Sushi", muted=True))

    return rows
