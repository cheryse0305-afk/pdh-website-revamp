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
3. Review with `git diff data/` before committing.
4. Commit the data files. Pushing to `main` deploys to production, so confirm with the project owner first.

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
- **Every doctor lists the general line** "8776-0644 to 46"; there are no direct numbers on the old site.
- **The Windows terminal shows en-dashes as `�`.** The JSON files are correct UTF-8.

## Known data gaps (as of 25 Nov 2026, for the reviewer)
- Dr Michael John Pabalate has no department or specialty.
- Inconsistent specialty names: "Infectious" / "Infectious Diseases"; "Allergology & Immunology" / "Allergology, Immunology" / "Allergology, Asthma".
- Animal Bite Center, Chemo Infusion Center and Patient Experience Department are "TBD" for location and schedule.
- HMO partner names are inferred; check "Pacific Cross" and "IMS Wellth Care" in particular.
