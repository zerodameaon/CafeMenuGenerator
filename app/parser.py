"""Parse the weekly cafe menu .docx into structured day data."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, timedelta

import docx
from docx.table import Table, _Cell

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
    closed: bool = False
    closed_reason: str = ""


class MenuParseError(Exception):
    pass


def format_month_day(d: date) -> str:
    """Formats a date as e.g. "August 17, 2026" without a leading zero on
    the day. strftime's "%-d" (no leading zero) is a Unix-only extension —
    Windows' C runtime raises ValueError on it — so the day number is
    built manually here instead, to keep this working cross-platform."""
    return f"{d.strftime('%B')} {d.day}, {d.year}"


# Word's AutoFormat quietly swaps in look-alike characters (non-breaking
# hyphens/spaces, en/em dashes), and text can arrive in decomposed Unicode
# (e + combining accent for "é"). Any of those would make a label like
# "Non‑Vegetarian Soup Du Jour" silently fail to match LABEL_MAP, and that
# row would just vanish from the sign. _key() is used only for matching —
# item text shown on the sign is left exactly as typed.
_DASHES = re.compile(r"[\u2010-\u2015\u2212]")
_SPACES = re.compile(r"\s+")


def _key(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    text = _DASHES.sub("-", text)
    text = _SPACES.sub(" ", text)  # \s covers NBSP and other Unicode spaces
    return text.strip().lower()


def _iter_paragraph_lines(doc: docx.Document) -> list[str]:
    """Every non-empty line of text in document order, including text inside
    tables (a menu laid out in a Word table would otherwise be invisible).
    Soft line breaks (Shift+Enter) within one paragraph are split into
    separate lines too, since each is visually its own menu line."""
    lines: list[str] = []

    def walk(container) -> None:
        for block in container.iter_inner_content():
            if isinstance(block, Table):
                # tr.tc_lst yields each physical cell once; row.cells would
                # repeat a horizontally merged cell once per grid column.
                for tr in block._tbl.tr_lst:
                    for tc in tr.tc_lst:
                        walk(_Cell(tc, block))
            else:
                for part in block.text.split("\n"):
                    part = part.strip()
                    if part:
                        lines.append(part)

    walk(doc)
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
        matched_day = next((d for d in DAY_NAMES if _key(line) == d.lower()), None)
        if matched_day:
            if matched_day in day_blocks:
                raise MenuParseError(
                    f"Found more than one '{matched_day}' heading. Each day should "
                    "appear exactly once — check for a duplicated or mislabeled day."
                )
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
        closed_reason = _closed_reason(day_blocks[day_name])
        if closed_reason is not None:
            days.append(DayMenu(
                day_name=day_name, menu_date=menu_date,
                closed=True, closed_reason=closed_reason,
            ))
            continue
        rows = _parse_day_block(day_name, day_blocks[day_name])
        days.append(DayMenu(day_name=day_name, menu_date=menu_date, rows=rows))

    return days


def _is_menu_line(line: str) -> bool:
    if _key(line) == "assorted sushi":
        return True
    split = _split_label_item(line)
    return split is not None and _key(split[0]) in LABEL_MAP


def _closed_reason(block_lines: list[str]) -> str | None:
    """A day block with no recognized menu lines, but a line mentioning
    "closed", is the office announcing a closure (e.g. a holiday) rather than
    a malformed section. Returns the closure line's text (for display) if so,
    else None. A day that has real menu lines is never treated as closed,
    even if it also carries a note like "Cafe closed early at 1pm"."""
    if any(_is_menu_line(line) for line in block_lines):
        return None
    for line in block_lines:
        stripped = line.strip()
        if "closed" in stripped.lower() and _split_label_item(stripped) is None:
            return stripped
    return None


def _parse_day_block(day_name: str, block_lines: list[str]) -> list[MenuRow]:
    """Builds this day's rows from whatever's actually present in the
    document. Not every week has every item on every day (e.g. a day might
    skip its soup, or have no Veggie Entrée) — a missing line is simply
    left out of that day's sign rather than treated as an error. The
    template's CSS sizes rows by flex weight, not a fixed row count, so a
    shorter day's rows just take up the freed-up space; no layout changes
    needed for a variable number of rows.

    The only things still treated as real errors are ones that indicate
    the document itself is malformed rather than a day simply having fewer
    items: Friday listing both soups at once (ambiguous — should be
    exactly one or none), and a day ending up with zero rows at all
    (suggests a parsing problem, not an intentionally sparse day)."""
    parsed: dict[str, str] = {}
    has_sushi = False

    for line in block_lines:
        if _key(line) == "assorted sushi":
            has_sushi = True
            continue
        split = _split_label_item(line)
        if not split:
            continue
        raw_label, item = split
        key = _key(raw_label)
        if key in LABEL_MAP:
            parsed[LABEL_MAP[key]] = item

    rows: list[MenuRow] = []

    breakfast = parsed.get("Breakfast")
    if breakfast is not None:
        rows.append(MenuRow(label="Breakfast", item=breakfast))

    veg = parsed.get("Veg Soup Du Jour")
    nonveg = parsed.get("Soup Du Jour")
    if day_name == "Friday":
        if veg and nonveg:
            raise MenuParseError(
                "Friday: found both veg and non-veg soup lines; expected only one."
            )
        if veg:
            rows.append(MenuRow(label="Veg Soup Du Jour", item=veg))
        elif nonveg:
            rows.append(MenuRow(label="Soup Du Jour", item=nonveg))
    else:
        if veg:
            rows.append(MenuRow(label="Veg Soup Du Jour", item=veg))
        if nonveg:
            rows.append(MenuRow(label="Soup Du Jour", item=nonveg))

    main_entree = parsed.get("Main Entrée")
    if main_entree is not None:
        rows.append(MenuRow(label="Main Entrée", item=main_entree, emphasis=True))

    veggie_entree = parsed.get("Veggie Entrée")
    if veggie_entree is not None:
        rows.append(MenuRow(label="Veggie Entrée", item=veggie_entree, emphasis=True))

    if day_name == "Wednesday" and has_sushi:
        rows.append(MenuRow(label="Assorted Sushi", item="Assorted Sushi", muted=True))

    if not rows:
        raise MenuParseError(
            f"{day_name}: no recognized menu lines found at all — check the "
            "document's formatting for this day."
        )

    return rows
