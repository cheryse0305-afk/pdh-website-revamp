"""Generate the site's data-driven pages and the homepage search index.

Usage:
    python tools/build_pages.py

Outputs:
    doctors/index.html            Doctor Finder
    doctors/<id>/index.html       one profile page per doctor
    services/index.html           Services directory ("Where is it?")
    directory/index.html          "Find Your Way" interactive floor directory
    sitemap.xml, robots.txt, llms.txt   search-engine and AI-assistant discoverability
    index.html (marked block)     Hospital JSON-LD between <!-- pdh:hospital-jsonld --> markers
    data/search-index.json        compact index for the homepage search and tiles (assets/js/pdh-home.js)

Reads data/doctors.json, services.json, contacts.json and search-terms.json; every search-terms target is
validated against the data. The header, navigation and footer are taken from index.html on every run, so the
pages always match the homepage. Re-run after changing index.html's header/footer, after refreshing the data,
or after editing data/search-terms.json (see workflows/refresh_pdh_data.md).
"""

import html
import json
import os
import re
import shutil
import unicodedata
import urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "doctors")
SERVICES_OUT = os.path.join(ROOT, "services")
SITE_URL = "https://pdh-website-revamp.vercel.app"  # switch to the production domain at launch
# Pre-launch: keep this site out of search engines and AI assistants until PDH points pdh.com.ph at it, so patients
# land on the official domain and the old site keeps its rankings. At launch: set SITE_URL, set False, re-run.
PRE_LAUNCH = True
HOSPITAL = "Parañaque Doctors Hospital"
APPOINTMENT_LINE = ("8776-0644 to 46", "tel:+63287760644")
WEEK = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
DAY_NAMES = dict(zip(WEEK, ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]))
INITIAL_PAGE_SIZE = 24

e = lambda s: html.escape(s or "", quote=True)


def load(name):
    return json.load(open(os.path.join(ROOT, "data", f"{name}.json"), encoding="utf-8"))["items"]


def shell():
    """Split index.html into (head, body-open-to-main, footer-to-end) around <main>."""
    page = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
    head_end = page.index("</head>")
    main_start = page.index('<main class="main" id="main">')
    main_end = page.index("</main>") + len("</main>")
    return page[:head_end], page[head_end:main_start], page[main_end:]


def page(head, body_top, footer, *, title, description, path, extra_head="", main="", scripts=""):
    url = SITE_URL + path
    head = re.sub(re.escape(JSONLD_START) + r".*?" + re.escape(JSONLD_END) + r"\n?", "", head, flags=re.S)  # homepage-only schema
    head = re.sub(r"<title>.*?</title>", f"<title>{e(title)}</title>", head, flags=re.S)
    for attr, value in (("og:title", title), ("og:description", description), ("og:url", url)):
        head = re.sub(rf'(<meta property="{attr}" content=")[^"]*', lambda m: m.group(1) + e(value), head)
    for attr, value in (("twitter:title", title), ("twitter:description", description), ("twitter:url", url)):
        head = re.sub(rf'(<meta name="{attr}" content=")[^"]*', lambda m: m.group(1) + e(value), head)
    head = re.sub(r'(<meta name="description" content=")[^"]*', lambda m: m.group(1) + e(description), head)
    head = re.sub(r'(<link rel="canonical" href=")[^"]*', lambda m: m.group(1) + url, head)
    # homepage-only assets (hero, sections, quick search) aren't needed on generated pages
    head = re.sub(r'<link rel="stylesheet" href="/assets/css/pdh-(?:home|tgh-colors|sections)\.css">\n?', "", head)
    footer = re.sub(r'<script src="/assets/js/pdh-home\.js" defer></script>\n?', "", footer)
    head += '<link rel="stylesheet" href="/assets/css/pdh-pages.css">\n' + extra_head
    body_top = body_top.replace('<body id="body" data-theme="tgh">', '<body id="body" data-theme="tgh" class="u-no-hero">', 1)
    footer = footer.replace("</body>", scripts + "</body>", 1)
    return head + body_top + f'<main class="main" id="main">\n{main}\n    </main>' + footer


def initials(name):
    name = re.sub(r"^(dr|dra)\.?\s+", "", name or "", flags=re.I)
    if "," in name:
        last, first = [p.strip() for p in name.split(",", 1)]
        parts = [first, last]
    else:
        parts = name.split()
        parts = [parts[0], parts[-1]] if len(parts) > 1 else parts
    return "".join(p[0].upper() for p in parts if p)


def fold(text):
    """Lowercase, accent-free text for search matching (mirrors fold() in pdh-doctors.js)."""
    return "".join(c for c in unicodedata.normalize("NFD", (text or "").lower()) if unicodedata.category(c) != "Mn")


def words(text):
    """Folded text as space-separated words, punctuation removed (mirrors words() in pdh-doctors.js)."""
    return " ".join(re.sub(r"[^a-z0-9]+", " ", fold(text).replace("'", "").replace("’", "")).split())


def word_prefix_match(query, text):
    """Every query word starts some word of text: "santos" matches "Delos Santos", not "Yarisantos"."""
    haystack = " " + words(text)
    return all(" " + t in haystack for t in words(query).split())


def specialty_line(d):
    spec, dept = d["specialty"], d["department"]
    if not spec and not dept:
        return "Specialty not listed"
    if spec and dept and fold(spec) != fold(dept):
        return f"{spec} · {dept}"
    return spec or dept


def photo(d, size):
    src = d["photo_thumb"] if size == "thumb" else d["photo_medium"]
    if d["has_photo"] and src:
        return f'<img src="{e(src)}" alt="" loading="lazy" decoding="async">'
    return f'<span class="pdh-doc__initials" aria-hidden="true">{e(initials(d["name"]))}</span>'


def card(d):
    days = " ".join(d["days"] or [])
    return f"""            <li class="pdh-doc" data-search="{e(words(' '.join(filter(None, [d['name'], d['specialty'], d['department']]))))}"
                data-dept="{e(d['department'])}" data-spec="{e(d['specialty'])}" data-days="{days}" data-oncall="{'1' if d['on_call'] else ''}">
                <a class="pdh-doc__link" href="/doctors/{d['id']}/">
                    <span class="pdh-doc__photo">{photo(d, 'thumb')}</span>
                    <span class="pdh-doc__body">
                        <span class="pdh-doc__name">{e(d['name'])}</span>
                        <span class="pdh-doc__spec">{e(specialty_line(d))}</span>
                        <span class="pdh-doc__sched">{e(d['schedule'] or 'Schedule not listed')}</span>
                    </span>
                </a>
            </li>"""


def options(values, label):
    opts = "".join(f'<option value="{e(v)}">{e(v)}</option>' for v in values)
    return f'<option value="">{label}</option>{opts}'


def finder(doctors):
    depts = sorted({d["department"] for d in doctors if d["department"]})
    specs = sorted({d["specialty"] for d in doctors if d["specialty"]})
    days = "".join(f'<option value="{d}">{DAY_NAMES[d]}</option>' for d in WEEK)
    cards = "\n".join(card(d) for d in doctors)
    return f"""<section class="pdh-finder" aria-labelledby="pdh-finder-title">
        <div class="pdh-finder__inner">
            <nav class="pdh-breadcrumb" aria-label="Breadcrumb"><a href="/">Home</a> <span aria-hidden="true">/</span> <span aria-current="page">Find a Doctor</span></nav>
            <h1 class="pdh-finder__title" id="pdh-finder-title">Find a Doctor</h1>
            <p class="pdh-finder__lede">Search our {len(doctors)} doctors by name or specialty, or filter by department and clinic day.</p>

            <form class="pdh-finder__filters" role="search" data-pdh-finder>
                <div class="pdh-field pdh-field--search">
                    <label for="pdh-q">Doctor name or specialty</label>
                    <input id="pdh-q" name="q" type="search" autocomplete="off" placeholder="e.g. Cardiology, Santos">
                </div>
                <div class="pdh-field">
                    <label for="pdh-dept">Department</label>
                    <select id="pdh-dept" name="dept">{options(depts, 'All departments')}</select>
                </div>
                <div class="pdh-field">
                    <label for="pdh-spec">Specialty</label>
                    <select id="pdh-spec" name="spec">{options(specs, 'All specialties')}</select>
                </div>
                <div class="pdh-field">
                    <label for="pdh-day">Clinic day</label>
                    <select id="pdh-day" name="day"><option value="">Any day</option>{days}<option value="oncall">On call</option></select>
                </div>
                <button class="pdh-finder__reset" type="reset">Clear filters</button>
            </form>

            <p class="pdh-finder__count" aria-live="polite" data-pdh-count>{len(doctors)} doctors</p>
            <ul class="pdh-finder__results" data-pdh-results>
{cards}
            </ul>
            <p class="pdh-finder__empty" data-pdh-empty hidden>No doctors match your search. Try fewer filters, or call
                <a href="{APPOINTMENT_LINE[1]}">{APPOINTMENT_LINE[0]}</a> and we'll help you find the right specialist.</p>
            <button class="pdh-finder__more" type="button" data-pdh-more hidden>Show more doctors</button>

            <p class="pdh-note">Clinic schedules come from PDH's doctor directory and may change. Please call
                <a href="{APPOINTMENT_LINE[1]}">{APPOINTMENT_LINE[0]}</a> to confirm before your visit.</p>
        </div>
    </section>"""


def profile(d, contacts):
    info = next((h for h in contacts["hotlines"] if h["id"] == "information-services"), None)
    days = "".join(f'<li>{DAY_NAMES[x]}</li>' for x in (d["days"] or []))
    days_html = f'<ul class="pdh-days" aria-label="Clinic days">{days}</ul>' if days else ""
    on_call = '<p class="pdh-profile__oncall">Available on call. Please contact the hospital to arrange a consultation.</p>' if d["on_call"] else ""
    mobile = ""
    if info and info["mobile"]:
        digits = re.sub(r"\D", "", info["mobile"])
        mobile = f' or <a href="tel:+63{digits[1:]}">{e(info["mobile"])}</a>'
    return f"""<section class="pdh-profile" aria-labelledby="pdh-profile-name">
        <div class="pdh-finder__inner">
            <nav class="pdh-breadcrumb" aria-label="Breadcrumb"><a href="/">Home</a> <span aria-hidden="true">/</span> <a href="/doctors/">Find a Doctor</a> <span aria-hidden="true">/</span> <span aria-current="page">{e(d['name'])}</span></nav>
            <div class="pdh-profile__card">
                <div class="pdh-profile__photo pdh-doc__photo">{photo(d, 'medium')}</div>
                <div class="pdh-profile__body">
                    <h1 class="pdh-profile__name" id="pdh-profile-name">{e(d['name'])}</h1>
                    <p class="pdh-profile__spec">{e(specialty_line(d))}</p>

                    <h2 class="pdh-profile__heading">Clinic schedule</h2>
                    <p class="pdh-profile__sched">{e(d['schedule'] or 'Schedule not listed')}</p>
                    {days_html}
                    {on_call}

                    <h2 class="pdh-profile__heading">Book a consultation</h2>
                    <p>Call our appointments line at <a href="{APPOINTMENT_LINE[1]}">{APPOINTMENT_LINE[0]}</a>{mobile}.</p>
                    <a class="pdh-button" href="{APPOINTMENT_LINE[1]}">Call {APPOINTMENT_LINE[0].split(' ')[0]}</a>

                    <p class="pdh-note">Schedules come from PDH's doctor directory and may change. Please call to confirm before your visit.</p>
                    <p><a class="pdh-back" href="/doctors/">&larr; Back to Find a Doctor</a></p>
                </div>
            </div>
        </div>
    </section>"""


def physician_jsonld(d, contacts):
    data = {
        "@context": "https://schema.org",
        "@type": "Physician",
        "name": d["name"],
        "url": f"{SITE_URL}/doctors/{d['id']}/",
        "telephone": "+63287760644",
        "address": {"@type": "PostalAddress", "streetAddress": contacts.get("address") or "",
                    "addressLocality": "Parañaque", "addressRegion": "Metro Manila", "addressCountry": "PH"},
        "hospitalAffiliation": {"@type": "Hospital", "name": HOSPITAL, "url": SITE_URL + "/"},
    }
    if d["specialty"]:
        data["medicalSpecialty"] = d["specialty"]
    if d["has_photo"] and d["photo_medium"]:
        data["image"] = d["photo_medium"]
    return '<script type="application/ld+json">' + json.dumps(data, ensure_ascii=False) + "</script>\n"


# ---------------------------------------------------------------- search vocabulary

def target_matches(target, d):
    """Mirror of the Doctor Finder's filters for a search-terms target."""
    if "spec" in target:
        return d["specialty"] == target["spec"]
    if "dept" in target:
        return d["department"] == target["dept"]
    return word_prefix_match(target["q"], " ".join(filter(None, [d["name"], d["specialty"], d["department"]])))


def target_url(target):
    key, value = next(iter(target.items()))
    return "/doctors/?" + urllib.parse.urlencode({key: value})


def load_terms(doctors, services, contacts):
    raw = json.load(open(os.path.join(ROOT, "data", "search-terms.json"), encoding="utf-8"))
    service_ids = {s["id"] for s in services}
    errors, specialties = [], []
    for group in raw["specialties"]:
        count = sum(target_matches(group["target"], d) for d in doctors)
        if count == 0:
            errors.append(f"specialty target {group['target']} matches no doctors")
        specialties.append({"label": group["label"], "url": target_url(group["target"]), "count": count, "terms": group["terms"],
                            # positions in search-index "doctors" (same order as doctors.json), for the concierge
                            "ix": [i for i, d in enumerate(doctors) if target_matches(group["target"], d)]})
    service_terms = {}
    for group in raw["services"]:
        if group["service"] not in service_ids:
            errors.append(f"unknown service id {group['service']!r}")
        service_terms.setdefault(group["service"], []).extend(group["terms"])
    hotline = next((h for h in contacts["hotlines"] if h["id"] == raw["emergency"]["hotline_id"]), None)
    if not hotline:
        errors.append(f"unknown hotline id {raw['emergency']['hotline_id']!r}")
    if errors:
        raise SystemExit("data/search-terms.json has invalid targets:\n  " + "\n  ".join(errors))
    return raw, specialties, service_terms, hotline


def tel(number):
    digits = re.sub(r"\D", "", number)
    return "tel:+63" + digits[1:] if digits.startswith("0") else "tel:+632" + digits


# ---------------------------------------------------------------- services directory

CATEGORY_LABELS = {"service": "Medical service", "facility": "Facility", "room": "Room"}


def is_24_7(s):
    return (s["schedule"] or "").strip().lower() == "open 24/7"


def service_card(s, terms):
    search = fold(" ".join([s["name"], s["description"] or "", " ".join(s["services_offered"] or []), " ".join(terms)]))
    rows = []
    if s["location"]:
        loc = e(s["location"])
        if s["floors"]:
            loc = f'<a href="/directory/#floor-{floor_key(s["floors"][0])}">{loc}</a>'
        rows.append(("Location", loc))
    if s["schedule"]:
        rows.append(("Hours", "<br>".join(e(l) for l in s["schedule"].split("\n"))))
    if s["contact"]:
        rows.append(("Call", f'<a href="{APPOINTMENT_LINE[1]}">{e(s["contact"])}</a>'))
    facts = "".join(f"<dt>{k}</dt><dd>{v}</dd>" for k, v in rows)
    extra = ""
    if s["services_offered"]:
        items = "".join(f"<li>{e(x)}</li>" for x in s["services_offered"])
        extra += f'<details class="pdh-svc__more"><summary>Services offered ({len(s["services_offered"])})</summary><ul>{items}</ul></details>'
    if s["amenities"]:
        extra += '<p class="pdh-svc__amenities"><strong>Amenities:</strong> ' + ", ".join(e(x) for x in s["amenities"]) + "</p>"
    if s["detail_url"]:
        extra += f'<p><a href="{e(s["detail_url"])}">More details on the PDH website</a></p>'
    badge = '<span class="pdh-svc__badge">Open 24/7</span>' if is_24_7(s) else ""
    return f"""            <li class="pdh-svc" id="{s['id']}" data-search="{e(search)}" data-cat="{s['category']}" data-open="{'24-7' if is_24_7(s) else ''}">
                <p class="pdh-svc__cat">{CATEGORY_LABELS[s['category']]}{badge}</p>
                <h2 class="pdh-svc__name">{e(s['name'])}</h2>
                <p class="pdh-svc__desc">{e(s['description'])}</p>
                <dl class="pdh-svc__facts">{facts}</dl>
                {extra}
            </li>"""


def services_page(services, service_terms):
    medical_24_7 = sum(1 for s in services if s["category"] == "service" and is_24_7(s))
    cats = "".join(f'<option value="{k}">{v}s</option>' for k, v in CATEGORY_LABELS.items())
    cards = "\n".join(service_card(s, service_terms.get(s["id"], [])) for s in services)
    return f"""<section class="pdh-finder" aria-labelledby="pdh-services-title">
        <div class="pdh-finder__inner">
            <nav class="pdh-breadcrumb" aria-label="Breadcrumb"><a href="/">Home</a> <span aria-hidden="true">/</span> <span aria-current="page">Services</span></nav>
            <h1 class="pdh-finder__title" id="pdh-services-title">Services &amp; Facilities</h1>
            <p class="pdh-finder__lede">Where to find each service, when it's open and who to call. {medical_24_7} medical services are open 24/7.</p>

            <form class="pdh-finder__filters pdh-finder__filters--services" role="search" data-pdh-services>
                <div class="pdh-field pdh-field--search">
                    <label for="pdh-sq">Service, test or facility</label>
                    <input id="pdh-sq" name="q" type="search" autocomplete="off" placeholder="e.g. X-ray, dialysis, pharmacy">
                </div>
                <div class="pdh-field">
                    <label for="pdh-cat">Type</label>
                    <select id="pdh-cat" name="cat"><option value="">All types</option>{cats}</select>
                </div>
                <div class="pdh-field pdh-field--check">
                    <input id="pdh-open" name="open" type="checkbox" value="24-7">
                    <label for="pdh-open">Open 24/7 only</label>
                </div>
                <button class="pdh-finder__reset" type="reset">Clear filters</button>
            </form>

            <p class="pdh-finder__count" aria-live="polite" data-pdh-count>{len(services)} services and facilities</p>
            <ul class="pdh-services" data-pdh-results>
{cards}
            </ul>
            <p class="pdh-finder__empty" data-pdh-empty hidden>Nothing matches your search. Call
                <a href="{APPOINTMENT_LINE[1]}">{APPOINTMENT_LINE[0]}</a> and we'll point you to the right department.</p>

            <p class="pdh-note">Locations and hours come from PDH's published service list and may change. Please call to confirm before your visit.</p>
        </div>
    </section>"""


# ---------------------------------------------------------------- homepage search index

HMO_APPROVAL_URL = "https://docs.google.com/forms/d/e/1FAIpQLSfGbbyaFRjyniWhqtGDN7iIRPqERjcXCGzobQlQkLESc1JbFg/viewform"


def search_index(doctors, services, raw_terms, specialties, service_terms, hotline, hmos, contacts):
    hub = next((h for h in contacts["hotlines"] if h["id"] == "hmo-hub"), None)
    # Homepage avatar row: one doctor with a real photo from each of the largest departments.
    faces, seen = [], set()
    by_size = sorted({d["department"] for d in doctors if d["department"]},
                     key=lambda dept: -sum(d["department"] == dept for d in doctors))
    for dept in by_size:
        d = next((d for d in doctors if d["department"] == dept and d["has_photo"]), None)
        if d and d["id"] not in seen:
            faces.append({"name": d["name"], "photo": d["photo_thumb"], "url": f"/doctors/{d['id']}/"})
            seen.add(d["id"])
        if len(faces) == 5:
            break
    depts = {}
    for d in doctors:
        if d["department"]:
            depts[d["department"]] = depts.get(d["department"], 0) + 1
    return {
        "doctors": [{"id": d["id"], "n": d["name"], "s": d["specialty"], "d": d["department"], "days": d["days"] or [],
                     "oc": d["on_call"], "sch": d["schedule"]} for d in doctors],
        "departments": [{"name": k, "count": v, "url": target_url({"dept": k})} for k, v in sorted(depts.items(), key=lambda x: -x[1])],
        "faces": faces,
        "specialty_count": len({d["specialty"] for d in doctors if d["specialty"]}),
        "specialties": specialties,
        "services": [{"id": s["id"], "name": s["name"], "cat": s["category"], "loc": s["location"], "hours": s["schedule"],
                      "open247": is_24_7(s), "terms": service_terms.get(s["id"], []), "offered": s["services_offered"] or []}
                     for s in services],
        "emergency": {"phrases": raw_terms["emergency"]["phrases"], "message": raw_terms["emergency"]["message"],
                      "hotline": {"name": hotline["name"], "mobile": hotline["mobile"], "tel": tel(hotline["mobile"])}},
        "crisis": {k: raw_terms["crisis"][k] for k in ("phrases", "message", "hotlines")},
        "appointments": {"label": APPOINTMENT_LINE[0], "tel": APPOINTMENT_LINE[1]},
        "hmo": {"partners": sorted(h["name"] for h in hmos), "approval_url": HMO_APPROVAL_URL,
                "hub": {"mobile": hub["mobile"], "tel": tel(hub["mobile"])} if hub and hub["mobile"] else None},
    }


# ---------------------------------------------------------------- "Find Your Way" floor directory

def floor_key(n):
    return {-1: "b", 0: "g"}.get(n, str(n))


def floor_name(n):
    if n == -1:
        return "Basement"
    if n == 0:
        return "Ground Floor"
    return f"{n}{'nd' if n == 2 else 'rd' if n == 3 else 'th'} Floor"


def floor_short(n):
    return {-1: "B", 0: "G"}.get(n, f"{n}F")


def directory_card(s, terms):
    search = fold(" ".join([s["name"], s["description"] or "", " ".join(s["services_offered"] or []), " ".join(terms)]))
    hours = (s["schedule"] or "").split("\n")
    hours = "Hours vary by test" if len(hours) > 1 and hours[0].rstrip().endswith(":") else hours[0]
    multi = f' <span class="pdh-dir__span">({e(s["location"])})</span>' if s["floors"] and len(s["floors"]) > 1 else ""
    er = " pdh-dir__card--er" if s["id"] == "emergency-room-er" else ""
    badge = '<span class="pdh-svc__badge">Open 24/7</span>' if is_24_7(s) else ""
    return f"""                        <li class="pdh-dir__card{er}" data-search="{e(search)}">
                            <p class="pdh-svc__cat">{CATEGORY_LABELS[s['category']]}{badge}</p>
                            <h3 class="pdh-dir__name">{e(s['name'])}{multi}</h3>
                            <p class="pdh-dir__meta">{e(hours) if hours else 'Hours not listed'}</p>
                            <p class="pdh-dir__links"><a href="{APPOINTMENT_LINE[1]}">Call {e(s['contact'] or APPOINTMENT_LINE[0])}</a> <a href="/services/#{s['id']}">Details</a></p>
                        </li>"""


def directory_page(services, service_terms, contacts):
    floors = sorted({f for s in services for f in (s["floors"] or [])}, reverse=True)
    on = {f: [s for s in services if f in (s["floors"] or [])] for f in floors}
    for f in floors:  # medical services first, then facilities
        on[f].sort(key=lambda s: (s["category"] != "service", s["name"]))
    tbd = [s for s in services if not s["floors"] and (s["location"] or "").upper().startswith("TBD")]
    start = 0 if 0 in floors else floors[-1]
    tabs, panels = [], []
    for f in floors:
        k, names = floor_key(f), ", ".join(s["name"].split(" (")[0] for s in on[f][:3]) + ("…" if len(on[f]) > 3 else "")
        sel = f == start
        cls = " pdh-floor--ground" if f == 0 else " pdh-floor--basement" if f == -1 else ""
        er = '<span class="pdh-floor__er">ER</span>' if any(s["id"] == "emergency-room-er" for s in on[f]) else ""
        tabs.append(f"""                    <li><button class="pdh-floor{cls}" type="button" role="tab" id="floor-tab-{k}" aria-controls="floor-{k}" aria-selected="{'true' if sel else 'false'}"{'' if sel else ' tabindex="-1"'} data-floor="{k}">
                        <span class="pdh-floor__num">{floor_short(f)}</span><span class="pdh-floor__names">{e(names)}</span>{er}<span class="pdh-floor__count" data-count>{len(on[f])}</span>
                    </button></li>""")
        cards = "\n".join(directory_card(s, service_terms.get(s["id"], [])) for s in on[f])
        panels.append(f"""                <section class="pdh-dir__panel" id="floor-{k}" role="tabpanel" aria-labelledby="floor-tab-{k}" tabindex="-1">
                    <h2 class="pdh-dir__floor">{floor_name(f)} <span>{len(on[f])} {'place' if len(on[f]) == 1 else 'places'}</span></h2>
                    <ul class="pdh-dir__cards">
{cards}
                    </ul>
                </section>""")
    tbd_html = ""
    if tbd:
        items = "".join(f'<li><a href="/services/#{s["id"]}">{e(s["name"])}</a></li>' for s in tbd)
        tbd_html = f'<p class="pdh-dir__tbd"><strong>Location to be announced:</strong></p><ul class="pdh-dir__tbd-list">{items}</ul>'
    parking = next((s for s in services if s["id"] == "parking"), None)
    er_line = next((h for h in contacts["hotlines"] if h["id"] == "emergency"), None)
    return f"""<section class="pdh-finder pdh-dir" aria-labelledby="pdh-dir-title">
        <div class="pdh-finder__inner">
            <nav class="pdh-breadcrumb" aria-label="Breadcrumb"><a href="/">Home</a> <span aria-hidden="true">/</span> <a href="/services/">Services</a> <span aria-hidden="true">/</span> <span aria-current="page">Find Your Way</span></nav>
            <h1 class="pdh-finder__title" id="pdh-dir-title">Find Your Way</h1>
            <p class="pdh-finder__lede">Explore PDH floor by floor. Select a floor to see what's there, or search for a service and we'll show you which floor to go to.</p>

            <form class="pdh-dir__search" role="search" data-pdh-dir-search>
                <label for="pdh-dir-q">Where do you need to go?</label>
                <input id="pdh-dir-q" name="q" type="search" autocomplete="off" placeholder="e.g. X-ray, dialysis, pharmacy, chapel">
                <p class="pdh-dir__status" aria-live="polite" data-pdh-dir-status></p>
            </form>

            <div class="pdh-dir__layout">
                <div class="pdh-bldg">
                    <div class="pdh-bldg__roof" aria-hidden="true"><span>PDH</span></div>
                    <ol class="pdh-bldg__floors" role="tablist" aria-label="Floors" aria-orientation="vertical">
{chr(10).join(tabs)}
                    </ol>
                    <p class="pdh-bldg__street" aria-hidden="true">Street level</p>
                </div>
                <div class="pdh-dir__panels">
{chr(10).join(panels)}
                    {tbd_html}
                </div>
            </div>

            <section class="pdh-dir__getting" aria-labelledby="pdh-dir-getting">
                <h2 id="pdh-dir-getting">Getting here</h2>
                <div class="pdh-dir__getting-grid">
                    <div><h3>Address</h3><p>{e(contacts['address'])}</p>
                        <p><a href="https://www.google.com/maps/search/?api=1&amp;query=Para%C3%B1aque+Doctors+Hospital%2C+175+Do%C3%B1a+Soledad+Ave%2C+Para%C3%B1aque" target="_blank" rel="noopener">Get directions</a></p></div>
                    <div><h3>Parking</h3><p>{e(parking['description']) if parking else 'Ask our staff for parking.'}</p></div>
                    <div class="pdh-dir__getting-er"><h3>Emergency entrance</h3><p>The Emergency Room is on the Ground Floor and open 24/7.</p>
                        {f'<p><a href="{tel(er_line["mobile"])}">Call {e(er_line["mobile"])}</a></p>' if er_line and er_line['mobile'] else ''}</div>
                </div>
            </section>

            <p class="pdh-note">Locations and hours come from PDH's published service list and may change. Please call {APPOINTMENT_LINE[0]} to confirm before your visit.</p>
        </div>
    </section>"""


# ---------------------------------------------------------------- AI-search discoverability

SAME_AS = ["https://www.facebook.com/paranaquedoctorshospitaluhbi/", "https://www.instagram.com/paranaquedoctorshospital/",
           "https://www.linkedin.com/company/paranaquedoctorshospital"]
MAPS_URL = "https://www.google.com/maps/search/?api=1&query=Para%C3%B1aque+Doctors+Hospital%2C+175+Do%C3%B1a+Soledad+Ave%2C+Para%C3%B1aque"
JSONLD_START, JSONLD_END = "<!-- pdh:hospital-jsonld -->", "<!-- /pdh:hospital-jsonld -->"
ROBOTS_START, ROBOTS_END = "<!-- pdh:robots -->", "<!-- /pdh:robots -->"
AI_BOTS = ["GPTBot", "OAI-SearchBot", "ChatGPT-User", "ClaudeBot", "Claude-SearchBot", "PerplexityBot", "Google-Extended"]


def postal_address(address):
    m = re.match(r"(?P<street>.+?),\s*Parañaque,\s*(?P<zip>\d{4}),\s*Metro Manila", address or "")
    if not m:
        raise SystemExit(f"Unexpected address format in contacts.json: {address!r}")
    return {"@type": "PostalAddress", "streetAddress": m.group("street"), "addressLocality": "Parañaque",
            "postalCode": m.group("zip"), "addressRegion": "Metro Manila", "addressCountry": "PH"}


def hospital_jsonld(hospital, contacts, services, doctors):
    hotlines = {h["id"]: h for h in contacts["hotlines"]}
    points = [{"@type": "ContactPoint", "contactType": label, "telephone": tel(hotlines[k]["mobile"])[4:]}
              for k, label in (("emergency", "emergency"), ("information-services", "customer service"),
                               ("admitting-department", "admissions"), ("hmo-hub", "billing support")) if k in hotlines and hotlines[k]["mobile"]]
    data = {
        "@context": "https://schema.org",
        "@type": "Hospital",
        "@id": SITE_URL + "/#hospital",
        "name": HOSPITAL,
        "alternateName": "PDH",
        "url": SITE_URL + "/",
        "logo": SITE_URL + "/assets/images/pdh-logo.png",
        "image": SITE_URL + "/assets/images/pdh/pdh-facade-2026.jpg",
        "description": hospital["intro"][0],
        "foundingDate": "2007-05-08",
        "telephone": "+63287760644",
        "email": (contacts["emails"] or [None])[0],
        "address": postal_address(contacts["address"]),
        "hasMap": MAPS_URL,
        "openingHours": "Mo-Su 00:00-23:59",
        "isAcceptingNewPatients": True,
        "parentOrganization": {"@type": "Organization", "name": "Metro Pacific Health"},
        "sameAs": SAME_AS,
        "contactPoint": points,
        "medicalSpecialty": sorted({d["department"] for d in doctors if d["department"]}),
        "department": [{"@type": "MedicalOrganization", "name": s["name"], "url": f"{SITE_URL}/services/#{s['id']}",
                        **({"openingHours": "Mo-Su 00:00-23:59"} if is_24_7(s) else {})}
                       for s in services if s["category"] == "service" and s["floors"]],
    }
    return json.dumps(data, ensure_ascii=False, indent=1)


def inject_homepage_jsonld(block):
    """Keep the Hospital JSON-LD in index.html in sync with the data (between marker comments)."""
    path = os.path.join(ROOT, "index.html")
    page_html = open(path, encoding="utf-8").read()
    tag = f'{JSONLD_START}\n<script type="application/ld+json">\n{block}\n</script>\n{JSONLD_END}'
    if JSONLD_START in page_html:
        page_html = re.sub(re.escape(JSONLD_START) + r".*?" + re.escape(JSONLD_END), lambda m: tag, page_html, flags=re.S)
    else:
        anchor = page_html.index('<link rel="canonical"')
        anchor = page_html.index("\n", anchor) + 1
        page_html = page_html[:anchor] + tag + "\n" + page_html[anchor:]
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(page_html)


def write_sitemap(doctors, lastmod):
    paths = ["/", "/doctors/", "/services/", "/directory/"] + [f"/doctors/{d['id']}/" for d in doctors]
    urls = "\n".join(f"  <url><loc>{SITE_URL}{p}</loc><lastmod>{lastmod}</lastmod></url>" for p in paths)
    write(os.path.join(ROOT, "sitemap.xml"),
          f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{urls}\n</urlset>\n')
    return len(paths)


def write_robots():
    if PRE_LAUNCH:
        lines = ["# PRE-LAUNCH: this site is not yet PDH's official address (pdh.com.ph).",
                 "# Google may crawl so it can see the noindex tag on every page; AI crawlers are asked to stay out.",
                 "User-agent: *", "Allow: /", ""]
        for bot in AI_BOTS:
            lines += [f"User-agent: {bot}", "Disallow: /", ""]
    else:
        lines = ["# Search engines and AI assistants are welcome: PDH wants patients to find accurate hospital information.",
                 "User-agent: *", "Allow: /", ""]
        for bot in AI_BOTS:
            lines += [f"User-agent: {bot}", "Allow: /", ""]
        lines.append(f"Sitemap: {SITE_URL}/sitemap.xml")
    write(os.path.join(ROOT, "robots.txt"), "\n".join(lines).rstrip("\n") + "\n")


def inject_robots_meta():
    """Pre-launch noindex tag in index.html (generated pages copy the head, so every page gets it)."""
    path = os.path.join(ROOT, "index.html")
    page_html = open(path, encoding="utf-8").read()
    tag = f'{ROBOTS_START}<meta name="robots" content="noindex, follow">{ROBOTS_END}' if PRE_LAUNCH else f"{ROBOTS_START}{ROBOTS_END}"
    if ROBOTS_START in page_html:
        page_html = re.sub(re.escape(ROBOTS_START) + r".*?" + re.escape(ROBOTS_END), lambda m: tag, page_html, flags=re.S)
    else:
        anchor = page_html.index('<meta name="viewport"')
        anchor = page_html.index("\n", anchor) + 1
        page_html = page_html[:anchor] + tag + "\n" + page_html[anchor:]
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(page_html)


def write_llms(hospital, contacts, services, doctors, hmos):
    hot = {h["id"]: h for h in contacts["hotlines"]}
    lines = [f"# {HOSPITAL} (PDH)", "", f"> {hospital['intro'][0]}", "",
             "Information below comes from PDH's published website. Schedules and locations can change; "
             f"patients should call {APPOINTMENT_LINE[0]} to confirm.", "",
             "## Emergency", "",
             f"- The Emergency Room is open 24/7 on the Ground Floor.",
             f"- Emergency hotline: {hot['emergency']['numbers']}" if "emergency" in hot else "", "",
             "## Contact", "", f"- Address: {contacts['address']}"]
    lines += [f"- {h['name']}: {h['numbers']}" for h in contacts["hotlines"]]
    lines += [f"- Email: {', '.join(contacts['emails'])}", f"- Directions: {MAPS_URL}", "",
              "## Key pages", "",
              f"- [Find a Doctor]({SITE_URL}/doctors/): search {len(doctors)} doctors by name, specialty, department and clinic day; each doctor has a profile page with their clinic schedule.",
              f"- [Services & Facilities]({SITE_URL}/services/): every service with its location, opening hours and phone number.",
              f"- [Find Your Way]({SITE_URL}/directory/): floor-by-floor hospital directory.", "",
              "## Services and where to find them", ""]
    for s in services:
        if s["category"] == "room":
            continue
        hours = (s["schedule"] or "not listed").split("\n")[0].rstrip(":")
        lines.append(f"- {s['name']}: {s['location'] or 'location not listed'}; hours: {hours}")
    lines += ["", "## About", ""]
    lines += [p for p in hospital["intro"][1:3]]
    lines += ["", f"- Mission: {hospital['mission']}", f"- Vision: {hospital['vision']}", "",
              "## HMO partners", "", ", ".join(sorted(h["name"] for h in hmos)), ""]
    write(os.path.join(ROOT, "llms.txt"), "\n".join(l for l in lines if l is not None) + "\n")


def write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)


def main():
    doctors = sorted(load("doctors"), key=lambda d: fold(d["name"]))
    contacts = load("contacts")[0]
    inject_robots_meta()
    head, body_top, footer = shell()
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)  # generated output only; removes pages for doctors no longer listed

    write(os.path.join(OUT, "index.html"), page(
        head, body_top, footer,
        title=f"Find a Doctor | {HOSPITAL}",
        description=f"Search {len(doctors)} doctors at {HOSPITAL} by name, specialty, department and clinic day.",
        path="/doctors/",
        main=finder(doctors),
        scripts=f'<script src="/assets/js/pdh-doctors.js" data-page-size="{INITIAL_PAGE_SIZE}" defer></script>\n',
    ))
    for d in doctors:
        spec = d["specialty"] or d["department"]
        write(os.path.join(OUT, d["id"], "index.html"), page(
            head, body_top, footer,
            title=f"{d['name']}{' – ' + spec if spec else ''} | {HOSPITAL}",
            description=f"{d['name']}{', ' + spec if spec else ''} at {HOSPITAL}. Clinic schedule: {d['schedule'] or 'not listed'}.",
            path=f"/doctors/{d['id']}/",
            extra_head=physician_jsonld(d, contacts),
            main=profile(d, contacts),
        ))
    print(f"Wrote doctors/index.html and {len(doctors)} profile pages")

    services = load("services")
    raw_terms, specialties, service_terms, hotline = load_terms(doctors, services, contacts)
    if os.path.isdir(SERVICES_OUT):
        shutil.rmtree(SERVICES_OUT)
    write(os.path.join(SERVICES_OUT, "index.html"), page(
        head, body_top, footer,
        title=f"Services & Facilities | {HOSPITAL}",
        description=f"Find services and facilities at {HOSPITAL}: location, opening hours and who to call.",
        path="/services/",
        main=services_page(services, service_terms),
        scripts='<script src="/assets/js/pdh-services.js" defer></script>\n',
    ))
    print(f"Wrote services/index.html ({len(services)} services and facilities)")

    index = search_index(doctors, services, raw_terms, specialties, service_terms, hotline, load("hmo-partners"), contacts)
    with open(os.path.join(ROOT, "data", "search-index.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(index, f, ensure_ascii=False, separators=(",", ":"))
    print(f"Wrote data/search-index.json ({os.path.getsize(os.path.join(ROOT, 'data', 'search-index.json')) // 1024} KB)")

    directory_out = os.path.join(ROOT, "directory")
    if os.path.isdir(directory_out):
        shutil.rmtree(directory_out)
    write(os.path.join(directory_out, "index.html"), page(
        head, body_top, footer,
        title=f"Find Your Way: Floor Directory | {HOSPITAL}",
        description=f"Floor-by-floor directory of {HOSPITAL}: find the ER, laboratory, radiology, pharmacy, dialysis and every other service.",
        path="/directory/",
        main=directory_page(services, service_terms, contacts),
        scripts='<script src="/assets/js/pdh-directory.js" defer></script>\n',
    ))
    print("Wrote directory/index.html")

    hospital = load("hospital")[0]
    inject_homepage_jsonld(hospital_jsonld(hospital, contacts, services, doctors))
    lastmod = json.load(open(os.path.join(ROOT, "data", "doctors.json"), encoding="utf-8"))["meta"]["generated_at"][:10]
    n = write_sitemap(doctors, lastmod)
    write_robots()
    write_llms(hospital, contacts, services, doctors, load("hmo-partners"))
    print(f"Wrote Hospital JSON-LD into index.html, sitemap.xml ({n} URLs), robots.txt, llms.txt")


if __name__ == "__main__":
    main()
