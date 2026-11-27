"""Turn PDH's free-text clinic schedules into plain, consistent wording.

    "TTHS 10:30am-12;30NN"                -> Tuesday, Thursday & Saturday: 10:30 AM – 12:30 PM
    "M 1:00pm-3:00pm/F 10:30am-12:30pm"   -> Monday: 1:00 PM – 3:00 PM; Friday: 10:30 AM – 12:30 PM
    "MWF 1:00-3:00/6:00pm-8:00pm"         -> Monday, Wednesday & Friday: 1:00 PM – 3:00 PM and 6:00 PM – 8:00 PM

parse() returns sessions [{"days": ["Mon", ...], "times": ["1:00 PM – 3:00 PM", ...]}] or None when the text
can't be read safely (the original text is then shown unchanged rather than guessed). Day letters follow
PDH's convention: M Mon, T Tue, W Wed, TH Thu, F Fri, S Sat, SU/SUN Sunday.
"""
import re

WEEK = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
DAY_NAMES = dict(zip(WEEK, ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]))
DAY_TOKENS = [("SUNDAY", "Sun"), ("SATURDAY", "Sat"), ("SUN", "Sun"), ("SAT", "Sat"), ("SU", "Sun"),
              ("TH", "Thu"), ("M", "Mon"), ("T", "Tue"), ("W", "Wed"), ("F", "Fri"), ("S", "Sat")]
TIME = r"(\d{1,2})(?:[:;.](\d{2}))?\s*(am|pm|nn|noon|mn)?"
RANGE = re.compile(TIME + r"\s*(?:-|–|to)\s*" + TIME, re.I)


def _days(code):
    code, out, i = code.upper(), [], 0
    while i < len(code):
        for token, day in DAY_TOKENS:
            if code.startswith(token, i):
                if day not in out:
                    out.append(day)
                i += len(token)
                break
        else:
            return None
    return [d for d in WEEK if d in out]


def _clock(h, m, mer):
    """(hour, minute, meridiem or None) -> minutes after midnight, or None if meridiem unknown."""
    h, m = int(h), int(m or 0)
    if mer is None:
        return None
    mer = mer.lower()
    if mer in ("nn", "noon"):
        return 12 * 60 + m
    if mer == "mn":
        return m
    if h == 12:
        h = 0
    return (h + (12 if mer == "pm" else 0)) * 60 + m


def _range(m):
    h1, m1, a1, h2, m2, a2 = m.groups()
    h1i, h2i = int(h1), int(h2)
    if h1i > 12 or h2i > 12 or int(m1 or 0) > 59 or int(m2 or 0) > 59:
        return None
    if a2 is None and a1 is None:  # "1:00-3:00": clinic hours with no am/pm -> afternoon for 1-7, else morning
        a2 = "pm" if 1 <= h2i <= 7 or h2i == 12 else "am"
    if a2 is None:
        a2 = a1
    end = _clock(h2, m2, a2)
    if a1 is None:  # start inherits the end's half of the day unless that would put it after the end
        start = _clock(h1, m1, a2)
        if start >= end:
            start = _clock(h1, m1, "am")
    else:
        start = _clock(h1, m1, a1)
    if start is None or end is None or start >= end:
        return None
    return "%s – %s" % (_fmt(start), _fmt(end))


def _fmt(minutes):
    h, m = divmod(minutes, 60)
    mer = "AM" if h < 12 else "PM"
    h = h % 12 or 12
    return "%d:%02d %s" % (h, m, mer)


def parse(text):
    if not text or not text.strip():
        return None
    t = text.strip()
    if re.fullmatch(r"(?i)on[- ]?call|by appointment", t):
        return None
    sessions, current = [], None
    for part in re.split(r"\s*(?:/|&|,|\band\b)\s*", t):
        if not part:
            continue
        m = re.match(r"([A-Za-z]+)\s*(.*)$", part)
        if m and _days(m.group(1)) is not None and not re.fullmatch(r"(?i)am|pm|nn|noon", m.group(1)):
            current = {"days": _days(m.group(1)), "times": []}
            sessions.append(current)
            part = m.group(2)
        if current is None:
            return None
        if not part.strip():
            continue
        rm = RANGE.fullmatch(part.strip())
        if not rm:
            return None
        r = _range(rm)
        if r is None:
            return None
        current["times"].append(r)
    if not sessions or any(not s["days"] or not s["times"] for s in sessions):
        return None
    return sessions


def day_list(days, short=False):
    names = [d if short else DAY_NAMES[d] for d in days]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " & " + names[-1]


def readable(text, short=False):
    """One line for cards and the concierge; the original text when it can't be read safely."""
    s = parse(text)
    if not s:
        if text and re.fullmatch(r"(?i)on[- ]?call", text.strip()):
            return "On call"
        only_days = text and re.fullmatch(r"[A-Za-z]+", text.strip()) and _days(text.strip())
        if only_days:
            return "%s · clinic hours not published" % day_list(only_days, short)
        return (text or "").strip() or "Schedule not listed"
    return "; ".join("%s: %s" % (day_list(x["days"], short), " and ".join(x["times"])) for x in s)


def all_days(text):
    s = parse(text)
    return [d for d in WEEK if s and any(d in x["days"] for x in s)]
