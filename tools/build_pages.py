"""Generate the site's data-driven pages and the homepage search index.

Usage:
    python tools/build_pages.py

Outputs:
    doctors/index.html            Doctor Finder
    doctors/<id>/index.html       one profile page per doctor
    services/index.html           Services directory ("Where is it?")
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
    head = re.sub(r"<title>.*?</title>", f"<title>{e(title)}</title>", head, flags=re.S)
    for attr, value in (("og:title", title), ("og:description", description), ("og:url", url)):
        head = re.sub(rf'(<meta property="{attr}" content=")[^"]*', lambda m: m.group(1) + e(value), head)
    for attr, value in (("twitter:title", title), ("twitter:description", description), ("twitter:url", url)):
        head = re.sub(rf'(<meta name="{attr}" content=")[^"]*', lambda m: m.group(1) + e(value), head)
    head = re.sub(r'(<meta name="description" content=")[^"]*', lambda m: m.group(1) + e(description), head)
    head = re.sub(r'(<link rel="canonical" href=")[^"]*', lambda m: m.group(1) + url, head)
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
        specialties.append({"label": group["label"], "url": target_url(group["target"]), "count": count, "terms": group["terms"]})
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
        rows.append(("Location", e(s["location"])))
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
                     "oc": d["on_call"]} for d in doctors],
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


def write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)


def main():
    doctors = sorted(load("doctors"), key=lambda d: fold(d["name"]))
    contacts = load("contacts")[0]
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


if __name__ == "__main__":
    main()
