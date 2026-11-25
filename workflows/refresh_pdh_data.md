# Refresh and review PDH data

## Objective
Keep `data/*.json` (doctors, services, contacts, hospital profile, HMO partners) in sync with the old PDH website, and track which records a PDH staff member has verified. The Doctor Finder, inquiry forms and AI concierge read these files. **The AI concierge may only use records with `review_status: "verified"`.**

## When to run
- After PDH updates doctors, schedules, services or contact numbers on pdh.com.ph.
- Before enabling or updating any AI feature.
- At least monthly while the old site remains the source of truth.

## Inputs
- Internet access to https://pdh.com.ph (WordPress REST API and the `/all-doctors/` directory).
- `index.html` (the HMO partner list is read from the homepage marquee).

## Steps
1. From the project root, run:
   ```
   python tools/build_pdh_data.py
   ```
   Don't use `python -I`: isolated mode blocks the tool from importing `tools/export_pdh_content.py`.
2. Read the summary line for each file, e.g. `data/doctors.json: 289 records ({'pending': 289, 'verified': 0, 'changed': 0})`.
   - A sudden drop in record counts means the old site's layout changed. Don't commit; see the edge cases below.
   - `changed > 0` means previously verified records changed at the source and need re-review.
3. Regenerate the Doctor Finder, profile pages, services directory and homepage search index:
   ```
   python tools/build_pages.py
   ```
   Also run this after any change to the header, navigation or footer in `index.html` (the generated pages copy them from there) and after editing `data/search-terms.json`. `doctors/`, `services/`, `directory/`, `data/search-index.json`, `sitemap.xml`, `robots.txt`, `llms.txt` and the Hospital JSON-LD block in `index.html` (between the `<!-- pdh:hospital-jsonld -->` markers) are generated output: never edit them by hand.
   The site is in **pre-launch mode** (`PRE_LAUNCH = True` in `tools/build_pages.py`): every page carries `<meta name="robots" content="noindex, follow">` and `robots.txt` asks AI crawlers to stay out, so search engines keep sending patients to the official pdh.com.ph. See "Going live on pdh.com.ph" below.

## Security headers (`vercel.json`)
The Content-Security-Policy only allows our own files plus Google Fonts, Vimeo (the "Our Story" video) and pdh.com.ph images. If you add a new external service (e.g. a chat widget, analytics, a map embed), add its domain to the matching directive or it will be silently blocked. The one inline script in `index.html` (`window.JSON_ENDPOINTS`) is allowed by its SHA-256 hash: if that block is edited, recompute the hash and update `script-src`, or the script will be blocked.

## Going live on pdh.com.ph
1. Point the pdh.com.ph domain at this Vercel project (Vercel → Settings → Domains) and confirm the site loads on it.
2. Redirect important old WordPress URLs to their new equivalents (e.g. `/all-doctors/` → `/doctors/`, `/our-services/` → `/services/`, `/doctor/<name>/` → `/doctors/<name>/`) so existing search results and bookmarks keep working.
3. In `tools/build_pages.py`: set `SITE_URL = "https://pdh.com.ph"` and `PRE_LAUNCH = False`.
4. Update the homepage `<link rel="canonical">`, `og:url` and `twitter:url` in `index.html` to `https://pdh.com.ph/`.
5. Run `python tools/build_pages.py`: this removes the noindex tags, opens `robots.txt` to search engines and AI assistants, and rewrites the sitemap, structured data and `llms.txt` with the new domain.
6. Commit and push, then submit `https://pdh.com.ph/sitemap.xml` in Google Search Console. The tool stops with an error if a search-terms target no longer matches the data (e.g. a specialty was renamed); fix the term file and re-run.
4. Review with `git diff data/` before committing.
5. Commit the data files, `doctors/` and `services/`. Pushing to `main` deploys to production, so confirm with the project owner first.

## Search vocabulary (`data/search-terms.json`)
Hand-written, not generated. It maps everyday English/Filipino words to specialties and services ("puso" to Cardiology, "gamot" to Pharmacy), and lists the emergency and crisis phrases that trigger the homepage safety banners.
- Add words patients actually use; keep targets exact (`spec` / `dept` must match `doctors.json` spelling).
- Emergency banner uses the "Emergency" hotline from `contacts.json`. The crisis banner uses the NCMH hotline numbers in the file (verified via web sources on 2026-11-25); PDH should confirm them before launch.
- The file has its own `review_status`; a clinician or the PDH data owner should review the term mappings and phrases.

## Reviewing records (PDH data owner)
Edit the record in the JSON file and set:
```json
"review_status": "verified",
"reviewed_by": "Full name, role",
"reviewed_at": "2026-11-25",
"review_notes": "optional, e.g. 'schedule confirmed with OPD'"
```
- To correct a wrong value, fix it **on the old website** (the source), then re-run the tool and verify. Edits made only in the JSON are overwritten on the next run.
- Never mark a record verified without checking it against a reliable PDH source (department head, OPD schedule, official memo).
- Records with `changed_since_review: true` were verified before but changed at the source. Check the new values and verify them again.

## Outputs
| File | Source |
|---|---|
| `data/doctors.json` | https://pdh.com.ph/all-doctors/ (all pages) |
| `data/services.json` | https://pdh.com.ph/our-services/ plus each service's detail page |
| `data/contacts.json` | https://pdh.com.ph/contact-2/ |
| `data/hospital.json` | https://pdh.com.ph/about-us/ |
| `data/hmo-partners.json` | `index.html` HMO marquee (names inferred from logo filenames) |

## Edge cases and known quirks
- **Doctor cards** are parsed by Elementor widget IDs (`b757796` name, `12f98c3` department, `2847895` specialty, `a8a4da8` schedule, `34fe994` phone). If PDH rebuilds the directory template, these IDs change and fields come back empty. Update `DOCTOR_WIDGETS` in the tool.
- **Page count** comes from `data-max-page` on the first directory page.
- **Schedules** are free text in about 96 formats. `schedule` keeps the original text; `days` is parsed only when every letter is a known day code, otherwise it's `null` (never guessed). "On call" sets `on_call: true`.
- **The room list is rendered twice** on the Our Services page; the tool keeps the copy with more amenities. Parsing stops at the "How Can We Help You?" block.
- **Services without a "More Details" link** are matched to detail pages by exact slug (e.g. `hemodialysis-center`).
- **Duplicate IDs** stop the tool before writing, because review tracking depends on unique IDs.
- **Doctor photos:** the directory shows `Doctor-Feature-Photo.webp` when a doctor has no photo; the tool sets `has_photo: false` for it (`PLACEHOLDER_PHOTOS` in the tool). `photo_thumb` (300 px) and `photo_medium` (768 px) come from the WordPress media library sizes.
- **Every doctor lists the general line** "8776-0644 to 46"; there are no direct numbers on the old site.
- **The Windows terminal shows en-dashes as `�`.** The JSON files are correct UTF-8.

## Known data gaps (as of 25 Nov 2026, for the reviewer)
- Dr Michael John Pabalate has no department or specialty.
- Inconsistent specialty names: "Infectious" / "Infectious Diseases"; "Allergology & Immunology" / "Allergology, Immunology" / "Allergology, Asthma".
- Animal Bite Center, Chemo Infusion Center and Patient Experience Department are "TBD" for location and schedule.
- HMO partner names are inferred; check "Pacific Cross" and "IMS Wellth Care" in particular.
