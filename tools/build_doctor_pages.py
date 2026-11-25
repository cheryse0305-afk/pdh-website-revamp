"""Generate the Doctor Finder (doctors/index.html) and one profile page per doctor (doctors/<id>/index.html).

Usage:
    python tools/build_doctor_pages.py

Reads data/doctors.json and data/contacts.json. The header, navigation and footer are taken from index.html
on every run, so the pages always match the homepage. Re-run after changing index.html's header/footer or after
refreshing the data (see workflows/refresh_pdh_data.md).
"""

import html
import json
import os
import re
import shutil
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "doctors")
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
    head += '<link rel="stylesheet" href="/assets/css/pdh-doctors.css">\n' + extra_head
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
    return f"""            <li class="pdh-doc" data-search="{e(fold(' '.join(filter(None, [d['name'], d['specialty'], d['department']]))))}"
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


if __name__ == "__main__":
    main()
