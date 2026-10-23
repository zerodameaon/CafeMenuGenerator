"""Holiday sign designs, and which upcoming holiday (if any) to remind about.

Pure date logic, no UI — app.py shows the reminder banner and the Holidays
menu from what's here.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Callable

# How far ahead the launch reminder looks. Two weeks covers both "this
# week's menu" and "next week's menu, prepped early".
REMINDER_DAYS = 14


@dataclass(frozen=True)
class Holiday:
    variant: str  # template.py THEMES key
    flavor_name: str  # what the app calls the design
    name: str  # the holiday itself
    # year → that year's holiday date, or None for a year it doesn't know
    # (the moon-calendar holidays only have a table of dates).
    date_in: Callable[[int], date | None]
    # The office is shut on the day itself (Thanksgiving, and the Friday
    # after), so the sign goes on the last weekday before it instead.
    office_closed: bool = False


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """The nth (1-based) Monday=0…Sunday=6 of the month; n=-1 for the last."""
    if n > 0:
        first = date(year, month, 1)
        return first + timedelta(days=(weekday - first.weekday()) % 7 + 7 * (n - 1))
    last = date(year + month // 12, month % 12 + 1, 1) - timedelta(days=1)
    return last - timedelta(days=(last.weekday() - weekday) % 7)


def _easter(year: int) -> date:
    """Western Easter Sunday (the anonymous Gregorian algorithm)."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    g = (8 * b + 13) // 25
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 19 * l) // 433
    month = (h + l - 7 * m + 90) // 25
    return date(year, month, (h + l - 7 * m + 33 * month + 19) % 32)


# Moon-calendar dates can't be worked out with simple rules, so these are
# looked up. Extend them before they run out.
_LUNAR_NEW_YEAR = {
    2027: date(2027, 2, 6), 2028: date(2028, 1, 26), 2029: date(2029, 2, 13),
    2030: date(2030, 2, 3),
}
# The first night's candle-lighting (it starts at sundown).
_HANUKKAH_FIRST_NIGHT = {
    2026: date(2026, 12, 4), 2027: date(2027, 12, 24), 2028: date(2028, 12, 12),
    2029: date(2029, 12, 1), 2030: date(2030, 12, 20),
}


# In calendar order, which is also the Holidays menu's order. Each one only
# shows up under the Flavor row once it's ticked in the Holidays menu, so it
# can't be picked by accident the rest of the year. It's then applied per
# day: the days ticked on its row get the holiday design, the rest keep the
# Flavor. The solemn days (MLK, Memorial Day, Juneteenth, Veterans Day) skip
# the food pun in their names.
HOLIDAYS = [
    Holiday("newyear", "Toast of the Town (New Year's)", "New Year's Day",
            lambda year: date(year, 1, 1), office_closed=True),
    Holiday("mlk", "Dream (MLK Day)", "Martin Luther King Jr. Day",
            lambda year: _nth_weekday(year, 1, 0, 3)),
    Holiday("lunarnewyear", "Lucky Noodles (Lunar New Year)", "Lunar New Year", _LUNAR_NEW_YEAR.get),
    Holiday("mardigras", "Let the Good Times Roll (Mardi Gras)", "Mardi Gras",
            lambda year: _easter(year) - timedelta(days=47)),
    Holiday("valentines", "Sweetheart Specials (Valentine's Day)", "Valentine's Day",
            lambda year: date(year, 2, 14)),
    Holiday("presidents", "Commander in Cheese (Presidents' Day)", "Presidents' Day",
            lambda year: _nth_weekday(year, 2, 0, 3)),
    Holiday("stpatricks", "Pot of Gold (St. Patrick's Day)", "St. Patrick's Day",
            lambda year: date(year, 3, 17)),
    Holiday("easter", "Egg-cellent Eats (Easter)", "Easter", _easter),
    Holiday("cincodemayo", "Fiesta Fare (Cinco de Mayo)", "Cinco de Mayo", lambda year: date(year, 5, 5)),
    Holiday("mothers", "Brunch for Mom (Mother's Day)", "Mother's Day",
            lambda year: _nth_weekday(year, 5, 6, 2)),
    Holiday("memorial", "We Remember (Memorial Day)", "Memorial Day",
            lambda year: _nth_weekday(year, 5, 0, -1), office_closed=True),
    Holiday("fathers", "Grill Master (Father's Day)", "Father's Day",
            lambda year: _nth_weekday(year, 6, 6, 3)),
    Holiday("juneteenth", "Freedom Day (Juneteenth)", "Juneteenth", lambda year: date(year, 6, 19)),
    Holiday("july4", "Red, White & Brunch (Fourth of July)", "the Fourth of July",
            lambda year: date(year, 7, 4), office_closed=True),
    Holiday("labor", "Labor of Loaf (Labor Day)", "Labor Day",
            lambda year: _nth_weekday(year, 9, 0, 1), office_closed=True),
    Holiday("halloween", "Fright Bites (Halloween)", "Halloween", lambda year: date(year, 10, 31)),
    Holiday("veterans", "Stars & Stripes (Veterans Day)", "Veterans Day", lambda year: date(year, 11, 11)),
    Holiday("thanksgiving", "Gobble Goodies (Thanksgiving)", "Thanksgiving",
            lambda year: _nth_weekday(year, 11, 3, 4), office_closed=True),
    Holiday("hanukkah", "Latke Love (Hanukkah)", "Hanukkah", _HANUKKAH_FIRST_NIGHT.get),
    Holiday("christmas", "Sleigh Bites (Christmas)", "Christmas",
            lambda year: date(year, 12, 25), office_closed=True),
]


def sign_day(holiday_date: date, office_closed: bool = False) -> date:
    """The cafe day to put the holiday design on: the holiday itself on a
    weekday, otherwise the Friday before. (A Sunday holiday's nearest
    weekday is the Monday after, but by then it's over, so it's the Friday
    before too.) If the office is closed for it, the weekday before."""
    if office_closed:
        holiday_date -= timedelta(days=1)
    weekday = holiday_date.weekday()
    if weekday < 5:
        return holiday_date
    return holiday_date - timedelta(days=weekday - 4)


@dataclass(frozen=True)
class Reminder:
    holiday: Holiday
    holiday_date: date
    sign_day: date


def upcoming_reminder(today: date) -> Reminder | None:
    """The soonest holiday whose sign day falls within the next
    REMINDER_DAYS days (today included), or None."""
    found = []
    for holiday in HOLIDAYS:
        # Next year's too, so a holiday early in January is seen in late December.
        for year in (today.year, today.year + 1):
            holiday_date = holiday.date_in(year)
            if holiday_date is None:
                continue
            day = sign_day(holiday_date, holiday.office_closed)
            if today <= day <= today + timedelta(days=REMINDER_DAYS):
                found.append(Reminder(holiday, holiday_date, day))
    return min(found, key=lambda r: r.sign_day, default=None)
