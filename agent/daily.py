"""Daily briefing: one tool that gathers the day's useful bits."""
import datetime as dt

from . import google, info, memory, study


def part(title, action):
    try:
        return f"## {title}\n{action()}"
    except Exception as err:
        return f"## {title}\n(not available: {str(err)[:120]})"


def daily_briefing():
    """Today's date, weather, calendar, unread email, study cards due, recent notes and news."""
    parts = [f"Now: {dt.datetime.now():%A %d %B %Y, %I:%M %p}",
             part("Weather", info.weather)]
    if google.ready():
        parts.append(part("Calendar today", lambda: google.calendar_events(1)))
        parts.append(part("Unread email", lambda: google.unread_emails(5)))
    due = len(study.due_cards())
    if due:
        parts.append(f"## Study\n{due} flashcards due today")
    parts.append(part("Recent notes", lambda: memory.read_notes()[-600:]))
    parts.append(part("News headlines", lambda: info.news(count=5)))
    return "\n\n".join(parts)
