"""Calendar integration (Module 25): iCalendar (.ics) export plus 'Add to Google Calendar' links.

No OAuth is needed: the .ics file imports into Google/Outlook/Apple Calendar, and the generated
links open Google Calendar's own event-creation page pre-filled.
"""
from datetime import date, datetime, timedelta, timezone
from typing import Iterable, List
from urllib.parse import urlencode


def _ics_escape(text: str) -> str:
    return (
        text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\r", "").replace("\n", "\\n")
    )


def google_calendar_url(title: str, day: date, details: str = "") -> str:
    params = {
        "action": "TEMPLATE",
        "text": title,
        "dates": f"{day:%Y%m%d}/{day + timedelta(days=1):%Y%m%d}",
        "details": details,
    }
    return "https://calendar.google.com/calendar/render?" + urlencode(params)


def build_ics(events: Iterable[dict]) -> bytes:
    """events: dicts with uid, title, date, kind."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines: List[str] = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//WorkSphere HRMS//Phase 4//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]
    for ev in events:
        day: date = ev["date"]
        lines += [
            "BEGIN:VEVENT",
            f"UID:{_ics_escape(ev['uid'])}@worksphere",
            f"DTSTAMP:{stamp}",
            f"DTSTART;VALUE=DATE:{day:%Y%m%d}",
            f"DTEND;VALUE=DATE:{day + timedelta(days=1):%Y%m%d}",
            f"SUMMARY:{_ics_escape(ev['title'])}",
            f"CATEGORIES:{_ics_escape(ev['kind'])}",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return ("\r\n".join(lines) + "\r\n").encode("utf-8")
