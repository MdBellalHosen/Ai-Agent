"""Flashcards with spaced review (Leitner boxes), and the mood diary. Stored only on this PC."""
import datetime as dt
import json

from . import config

CARDS_FILE = config.DATA / "flashcards.json"
MOOD_FILE = config.DATA / "mood.json"
INTERVALS = [1, 2, 4, 8, 16, 32]  # days until the next review, per box


def today():
    return dt.date.today()


def load(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return data if isinstance(data, list) else []


def save(path, data):
    config.DATA.mkdir(exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


# ---------- flashcards ----------
def add_flashcards(deck, cards):
    """cards: [{"front": question, "back": answer}, ...]"""
    if isinstance(cards, str):
        cards = json.loads(cards)
    all_cards = load(CARDS_FILE)
    next_id = max((c["id"] for c in all_cards), default=0) + 1
    added = 0
    for card in cards[:50]:
        front, back = str(card.get("front", "")).strip(), str(card.get("back", "")).strip()
        if front and back:
            all_cards.append({"id": next_id, "deck": str(deck).strip()[:60] or "General",
                              "front": front[:500], "back": back[:1000], "box": 0,
                              "due": today().isoformat()})
            next_id += 1
            added += 1
    save(CARDS_FILE, all_cards)
    return f"Added {added} cards to deck '{deck}'"


def due_cards(deck=""):
    now = today().isoformat()
    return [c for c in load(CARDS_FILE)
            if c["due"] <= now and (not deck or c["deck"].lower() == str(deck).lower())]


def next_flashcards(deck="", count=5):
    """Cards due today. Ask the user the front, wait for the answer, then grade."""
    due = due_cards(deck)[:max(1, min(int(count or 5), 20))]
    if not due:
        return "No cards due today" + (f" in '{deck}'" if deck else "")
    return "\n".join(f"id {c['id']} [{c['deck']}] Q: {c['front']} | A: {c['back']}" for c in due)


def grade_flashcard(card_id, correct):
    cards = load(CARDS_FILE)
    for card in cards:
        if card["id"] == int(card_id):
            if correct:
                card["box"] = min(card["box"] + 1, len(INTERVALS) - 1)
                card["due"] = (today() + dt.timedelta(days=INTERVALS[card["box"]])).isoformat()
            else:  # wrong answers come back today
                card["box"] = 0
                card["due"] = today().isoformat()
            save(CARDS_FILE, cards)
            return f"Next review on {card['due']}"
    return "Card not found"


def list_decks():
    decks = {}
    for card in load(CARDS_FILE):
        total, due = decks.get(card["deck"], (0, 0))
        decks[card["deck"]] = (total + 1, due + (card["due"] <= today().isoformat()))
    if not decks:
        return "No flashcards yet"
    return "\n".join(f"{d}: {t} cards, {u} due today" for d, (t, u) in sorted(decks.items()))


# ---------- mood diary ----------
def log_mood(score, note=""):
    """score 1 (very bad) to 5 (very good). Only when the user wants it logged."""
    score = int(score)
    if not 1 <= score <= 5:
        return "score must be 1 to 5"
    entries = load(MOOD_FILE)
    entries.append({"time": f"{dt.datetime.now():%Y-%m-%d %H:%M}", "score": score, "note": str(note)[:500]})
    save(MOOD_FILE, entries[-1000:])
    return "Mood saved in the diary on this PC"


def mood_summary(days=7):
    days = max(1, min(int(days or 7), 90))
    since = (today() - dt.timedelta(days=days - 1)).isoformat()
    recent = [e for e in load(MOOD_FILE) if e["time"][:10] >= since]
    if not recent:
        return f"No mood entries in the last {days} days"
    average = sum(e["score"] for e in recent) / len(recent)
    lines = [f"Last {days} days: {len(recent)} entries, average {average:.1f} out of 5"]
    lines += [f"{e['time']}: {e['score']}/5 {e['note']}".rstrip() for e in recent[-10:]]
    return "\n".join(lines)
