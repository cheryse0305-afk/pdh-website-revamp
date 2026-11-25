"""Build the verified-data layer (data/*.json) from the old PDH website (pdh.com.ph).

Usage:
    python tools/build_pdh_data.py

Outputs (committed; used by the Doctor Finder, inquiry forms and AI concierge):
    data/doctors.json        all doctors from the paginated /all-doctors/ directory
    data/services.json       services, facilities and rooms from /our-services/ (+ "Services Offered" lists)
    data/contacts.json       hotlines, email, address from /contact-2/
    data/hospital.json       profile, mission/vision, core values, leadership, barangay partners from /about-us/
    data/hmo-partners.json   HMO partner names + logos from the homepage marquee (index.html)

Review workflow:
    Every record has review_status ("pending" | "verified"), reviewed_by, reviewed_at and a content fingerprint.
    Re-running keeps a record's review fields while its content is unchanged; if the source changed, the
    record goes back to "pending" with changed_since_review = true. Nothing is ever auto-verified.
"""

import datetime
import hashlib
import html
import json
import os
import re
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

from export_pdh_content import BASE, ROOT, TextExtractor, get

DATA = os.path.join(ROOT, "data")
SITE = "https://pdh.com.ph/"
REVIEW_FIELDS = ("review_status", "reviewed_by", "reviewed_at", "review_notes")


class LinkAwareExtractor(TextExtractor):
    """TextExtractor that also records the target of "More Details" links."""

    def __init__(self):
        super().__init__()
        self.last_href = None

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.last_href = dict(attrs).get("href")
        super().handle_starttag(tag, attrs)

    def flush(self):
        text = re.sub(r"\s+", " ", "".join(self.buf)).strip()
        if text == "More Details" and self.last_href:
            self.buf = []
            self.lines.append(f"[[more:{self.last_href}]]")
            return
        super().flush()


def page_lines(slug):
    body, _ = get(f"{BASE}pages?slug={urllib.parse.quote(slug)}&_fields=content,link")
    page = json.loads(body)[0]
    p = LinkAwareExtractor()
    p.feed(page["content"]["rendered"])
    p.flush()
    return [l for l in p.lines if not l.startswith("![")], page["link"]


def heading(line):
    m = re.match(r"#{1,6} (.*)", line)
    return m.group(1).strip() if m else None


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower().replace("ñ", "n")).strip("-")


# ---------------------------------------------------------------- doctors

DOCTOR_WIDGETS = {"b757796": "name", "12f98c3": "department", "2847895": "specialty",
                  "a8a4da8": "schedule", "34fe994": "phone"}
DAY_TOKENS = [("SUNDAY", "Sun"), ("SATURDAY", "Sat"), ("SUN", "Sun"), ("SAT", "Sat"), ("SU", "Sun"),
              ("TH", "Thu"), ("M", "Mon"), ("T", "Tue"), ("W", "Wed"), ("F", "Fri"), ("S", "Sat")]
WEEK = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def parse_days(schedule):
    """Day codes from a free-text schedule ("TTHS 10:30am-12:30pm / Sat 8:00am"). None when unsure."""
    if not schedule or re.fullmatch(r"on[- ]?call", schedule.strip(), re.I):
        return None
    days = set()
    for segment in re.split(r"/|&|\band\b", schedule):
        m = re.match(r"\s*([A-Za-z]+)", segment)
        if not m:
            continue  # time-only segment, e.g. "10:00-12:00pm" after "/"
        code, i = m.group(1).upper(), 0
        while i < len(code):
            for token, day in DAY_TOKENS:
                if code.startswith(token, i):
                    days.add(day)
                    i += len(token)
                    break
            else:
                return None  # unknown letters: don't guess
    return [d for d in WEEK if d in days] or None


def doctor_cards(page_html):
    starts = [m.start() for m in re.finditer(r'<div[^>]*class="[^"]*\be-loop-item\b', page_html)] + [None]
    for a, b in zip(starts, starts[1:]):
        card = page_html[a:b]
        rec = {}
        for wid, key in DOCTOR_WIDGETS.items():
            m = re.search(r'data-id="%s".*?class="[^"]*elementor-heading-title[^"]*"[^>]*>(.*?)</' % wid, card, re.S)
            rec[key] = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", m.group(1)))).strip() if m else None
        post_id = re.search(r"\be-loop-item-(\d+)", card)
        link = re.search(r'<a[^>]+href="(https://pdh\.com\.ph/doctor/[^"]+)"', card)
        photo = re.search(r'<img[^>]+src="([^"]+)"', card)
        yield post_id.group(1) if post_id else None, link.group(1) if link else None, \
            photo.group(1) if photo else None, rec


def build_doctors():
    first, _ = get(SITE + "all-doctors/")
    pages = int(re.search(rb'data-max-page="(\d+)"', first).group(1))
    urls = [SITE + "all-doctors/"] + [f"{SITE}all-doctors/page/{n}/" for n in range(2, pages + 1)]
    with ThreadPoolExecutor(max_workers=5) as pool:
        bodies = [first] + list(pool.map(lambda u: get(u)[0], urls[1:]))
    print(f"  doctor directory: {pages} pages")
    doctors = []
    for body in bodies:
        for post_id, link, photo, rec in doctor_cards(body.decode("utf-8")):
            schedule = rec["schedule"]
            doctors.append({
                "id": slugify(link.rstrip("/").rsplit("/", 1)[-1]) if link else slugify(rec["name"]),
                "wp_id": int(post_id) if post_id else None,
                "name": rec["name"],
                "department": (rec["department"] or "").rstrip(" -").strip() or None,
                "specialty": rec["specialty"],
                "schedule": schedule,
                "days": parse_days(schedule),
                "on_call": bool(schedule and re.fullmatch(r"on[- ]?call", schedule.strip(), re.I)),
                "phone": rec["phone"],
                "profile_url": link,
                "photo_url": photo,
            })
    return doctors, urls[:1]


# ---------------------------------------------------------------- services

FLOOR_WORDS = {"ground": 0, "basement": -1}


def parse_floors(location):
    if not location:
        return None
    nums = [int(n) for n in re.findall(r"(\d+)(?:st|nd|rd|th)", location)]
    words = [v for k, v in FLOOR_WORDS.items() if k in location.lower()]
    if " to " in location and len(nums) == 2:
        return list(range(nums[0], nums[1] + 1))
    return sorted(set(nums + words)) or None


def services_offered(detail_url):
    slug = detail_url.rstrip("/").rsplit("/", 1)[-1]
    try:
        lines, _ = page_lines(slug)
    except (IndexError, OSError):
        return None
    out, on = [], False
    for line in lines:
        h = heading(line)
        if h:
            if on:
                break
            on = h.lower().startswith("services offered")
        elif on:
            if re.match(r"(Location|Contact|Schedule):", line) or line.startswith("[[more:"):
                break
            out.append(line)
    return out or None


def service_pages():
    """Detail pages under /our-services/, keyed by slug (used when the list has no "More Details" link)."""
    body, _ = get(f"{BASE}pages?per_page=100&_fields=slug,link")
    return {p["slug"]: p["link"] for p in json.loads(body) if "/our-services/" in p["link"]}


def build_services():
    lines, url = page_lines("our-services")
    category, items, cur, field = None, [], None, None
    categories = {"Our Services": "service", "Our Facilities": "facility", "Our Rooms": "room"}
    for line in lines:
        h = heading(line)
        if h == "How Can We Help You?":  # contact call-to-action block after the room list
            break
        if h in categories or h == "Our Packages":
            category, cur = categories.get(h), None
            continue
        if h:
            cur = {"id": slugify(h), "name": h, "category": category, "description": None,
                   "location": None, "floors": None, "contact": None, "schedule": None,
                   "amenities": None, "detail_url": None, "services_offered": None}
            items.append(cur)
            field = None
            continue
        if cur is None:
            continue
        if line.startswith("[[more:"):
            cur["detail_url"] = line[7:-2]
            continue
        m = re.match(r"(Location|Contact|Schedule|Amenities):\s*(.*)", line)
        if m:
            field = m.group(1).lower()
            if field == "amenities":
                cur["amenities"] = []
            else:
                cur[field] = m.group(2) or ""
            continue
        if field == "amenities":
            cur["amenities"].append(line)
        elif field == "schedule":
            cur["schedule"] = (cur["schedule"] + "\n" + line).strip()
        elif cur["description"] is None:
            cur["description"] = line
        else:
            cur["description"] += " " + line
    unique = {}
    for i in items:
        if not i["description"]:
            continue  # heading with no published content ("coming soon" tiles)
        seen = unique.get(i["id"])
        # The room list is rendered twice on the page; keep the copy with more detail.
        if not seen or len(i["amenities"] or []) > len(seen["amenities"] or []):
            unique[i["id"]] = i
    items = list(unique.values())
    pages = service_pages()
    for i in items:
        i["floors"] = parse_floors(i["location"])
        if not i["detail_url"] and i["id"] in pages:
            i["detail_url"] = pages[i["id"]]
    with ThreadPoolExecutor(max_workers=5) as pool:
        offered = list(pool.map(lambda i: services_offered(i["detail_url"]) if i["detail_url"] else None, items))
    for i, o in zip(items, offered):
        i["services_offered"] = o
    return items, [url]


# ---------------------------------------------------------------- contacts / hospital / HMOs

def build_contacts():
    lines, url = page_lines("contact-2")
    hotlines, email, address = [], [], None
    for prev, line in zip(lines, lines[1:]):
        h = heading(prev)
        if h and re.search(r"\d{4}", line) and not heading(line):
            mobile = re.search(r"\b09\d{2} ?\d{3} ?\d{4}\b", line)
            hotlines.append({"id": slugify(h), "name": h, "numbers": line,
                             "mobile": mobile.group(0) if mobile else None})
    for line in lines:
        email += re.findall(r"[\w.+-]+@pdh\.com\.ph", line)
        if re.search(r"Parañaque.*Metro Manila", line) and not address:
            address = line
    return [{"id": "contacts", "hotlines": hotlines, "emails": sorted(set(email)), "address": address}], [url]


def section(lines, title):
    out, on = [], False
    for line in lines:
        h = heading(line)
        if h is not None and on and h != title:
            break
        if h == title:
            on = True
        elif on:
            out.append(line)
    return out


def build_hospital():
    lines, url = page_lines("about-us")
    intro = []
    for line in lines:
        if heading(line):
            break
        intro.append(line)
    after = lines[lines.index("## Core Values") + 1:]
    values, leaders, partners = [], [], {}
    for h_line, body in zip(after, after[1:]):
        h = heading(h_line)
        if h == "Our Leadership Team":
            break
        if h and not heading(body):
            values.append({"name": h, "description": body})
    lead = section(lines, "Our Leadership Team")
    start = lines.index("## Our Leadership Team")
    for h_line, body in zip(lines[start + 1:], lines[start + 2:]):
        h = heading(h_line)
        if h == "Our Barangay Partners":
            break
        if h and not heading(body):
            leaders.append({"name": h, "title": body})
    start = lines.index("## Our Barangay Partners")
    for h_line, body in zip(lines[start + 1:], lines[start + 2:]):
        h = heading(h_line)
        if h and h.startswith("Barangay") and not heading(body):
            partners.setdefault(h, body)  # the page repeats some partners
    return [{
        "id": "hospital",
        "name": "Parañaque Doctors Hospital",
        "short_name": "PDH",
        "intro": intro,
        "mission": " ".join(section(lines, "Our Mission")),
        "vision": " ".join(section(lines, "Our Vision")),
        "goal": " ".join(section(lines, "Our Goal")),
        "core_values": values,
        "leadership_intro": lead[:2],
        "leadership": leaders,
        "barangay_partners": [{"name": k, "description": v} for k, v in partners.items()],
    }], [url]


def build_hmo_partners():
    page = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
    block = re.search(r'<ul class="pdh-partners__list">(.*?)</ul>', page, re.S).group(1)
    items = [{"id": slugify(html.unescape(alt)), "name": html.unescape(alt), "logo": src,
              "name_source": "inferred from logo filename (old site has no names)"}
             for src, alt in re.findall(r'<img src="([^"]+)" alt="([^"]+)"', block)]
    return items, [SITE, "index.html (HMO partners marquee)"]


# ---------------------------------------------------------------- output with review preservation

def fingerprint(record):
    content = {k: v for k, v in record.items() if k not in REVIEW_FIELDS + ("fingerprint", "changed_since_review")}
    return hashlib.sha256(json.dumps(content, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


def write(name, items, sources):
    ids = [r["id"] for r in items]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        raise SystemExit(f"data/{name}.json not written: duplicate ids {dupes}")
    path = os.path.join(DATA, f"{name}.json")
    previous = {}
    if os.path.exists(path):
        previous = {r["id"]: r for r in json.load(open(path, encoding="utf-8"))["items"]}
    counts = {"pending": 0, "verified": 0, "changed": 0}
    for rec in items:
        rec["fingerprint"] = fingerprint(rec)
        old = previous.get(rec["id"])
        if old and old.get("review_status") == "verified" and old.get("fingerprint") != rec["fingerprint"]:
            rec.update(review_status="pending", reviewed_by=None, reviewed_at=None,
                       review_notes=old.get("review_notes"), changed_since_review=True)
            counts["changed"] += 1
        elif old:
            rec.update({k: old.get(k) for k in REVIEW_FIELDS})
        else:
            rec.update(review_status="pending", reviewed_by=None, reviewed_at=None, review_notes=None)
        counts["verified" if rec["review_status"] == "verified" else "pending"] += 1
    doc = {
        "meta": {
            "generated_by": "tools/build_pdh_data.py",
            "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
            "sources": sources,
            "records": len(items),
            "review_summary": counts,
        },
        "items": items,
    }
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"  data/{name}.json: {len(items)} records ({counts})")


def main():
    os.makedirs(DATA, exist_ok=True)
    for name, build in [("doctors", build_doctors), ("services", build_services), ("contacts", build_contacts),
                        ("hospital", build_hospital), ("hmo-partners", build_hmo_partners)]:
        print(f"Building {name}...")
        items, sources = build()
        write(name, items, sources)


if __name__ == "__main__":
    main()
