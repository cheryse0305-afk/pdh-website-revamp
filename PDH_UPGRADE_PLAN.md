# PDH Website Upgrade Plan

**Project:** Parañaque Doctors Hospital website revamp
**Live site:** https://pdh-website-revamp.vercel.app/
**Repository:** github.com/cheryse0305-afk/pdh-website-revamp (local branch `master` → `origin/main`)
**Audit date:** 25 November 2026
**Status:** Audit only. No existing files were modified.

---

## Summary

The live site is a single static HTML homepage built on a clone of the Tampa General Hospital (TGH) homepage, with PDH content, images and links. It deploys from GitHub to Vercel with no build step.

Before any AI or lead-generation features are added, **five production issues need fixing first**. The most urgent one: 82 images on the live site point to `http://127.0.0.1:5500`, a local development address. For real visitors, the logo, all PDH photos and all partner logos fail to load. The site also depends at runtime on TGH's own servers for its stylesheet, JavaScript and icons, so TGH can break the site at any time.

After that, the recommended order is:
1. **A verified data layer.** Services, floors, contacts, HMOs and the doctor directory, as JSON files in the repo.
2. **Doctor Finder and lead capture.** Appointment requests and callback requests.
3. **The AI Concierge and natural-language search.** These use the same verified data and the same inquiry pipeline.

Every feature in this plan is backed by real data or a real endpoint. None is a placeholder.

---

## 1. Existing website architecture

| Layer | What exists today |
|---|---|
| Hosting | Vercel, static hosting. Auto-deploys from GitHub `main`. No `vercel.json`, no `package.json`, no build step, no serverless functions (`/api` returns 404). |
| Page served | `index.html`, a 77 KB single page. It's identical to the live site. |
| Working copy | `pdh-homepage.html`. This is the same page plus an uncommitted logo-alignment fix. **There are two sources of truth.** |
| Design system | TGH's `global.css` and `main.js`, loaded **from tgh.org at runtime** through `<base href="https://www.tgh.org/">`. |
| PDH overrides | A small inline `<style>` block covering logo sizing and the HMO partner marquee. |
| Fonts | TGH's Adobe Fonts kit (`use.typekit.net/xus6sna.css`). These kits are licensed to the kit owner's domains. |
| Icons | `<use xlink:href="#icon-…">` references (64 of them). The page has no icon definitions; TGH's scripts load them from tgh.org. |
| Media | 259 files in `assets/images/` (90 MB), plus 86 images in the repo root (25 MB). |
| Video | PDH's Vimeo video "ALAGANG PDH AKO" as the hero background (iframe). |
| Inner pages | None on the new site. 91 links go to the old WordPress site (pdh.com.ph). |
| Content source | The old site's WordPress REST API, exported by `tools/export_pdh_content.py` into `.tmp/pdh-content/` (gitignored, so not deployed). |

**How the page works today:** the HTML loads TGH's CSS and JS from tgh.org. TGH's JS runs the dropdown menus, the mobile drill-down menu, the sticky header and the animations. All content and links are hard-coded in `index.html`.

---

## 2. Features already implemented (working)

| Feature | Notes |
|---|---|
| PDH-branded homepage | Hero, "Why PDH?", service tiles, "Here for You, 24/7", HMO partners, featured services, news and footer, all with real PDH content. |
| Desktop and mobile navigation | PDH menu structure. Depends on TGH's remote JS. |
| Hero background video | Vimeo, autoplay, muted, loop. |
| HMO partner marquee | CSS-only. Pauses on hover and respects reduced-motion settings. |
| Click-to-call and email | 7 `tel:` / `mailto:` links, all with real PDH numbers. |
| HMO online approval | Links to PDH's existing Google Form. |
| Service feedback | Links to PDH's existing Cempia survey. |
| Site search | The three search boxes submit to the old site's WordPress search (`pdh.com.ph/?s=`). This works, but it sends visitors away from the new site. |
| Social links | Facebook, Instagram, LinkedIn. |
| Basic SEO | `<title>`, meta description, Open Graph tags, canonical link. |
| Content export tool | `tools/export_pdh_content.py` exports pages, posts, 289 doctors and media metadata. |

---

## 3. Partially functional / broken in production

Ordered by severity.

| # | Issue | Impact | Evidence |
|---|---|---|---|
| P0-1 | **82 image URLs use `http://127.0.0.1:5500/…`** | The logo, all PDH photos, all partner logos and section backgrounds fail to load for every visitor. They only appear on the developer's machine while Live Server is running. Browsers also block `http` images on an `https` page. | `grep 127.0.0.1` on the live HTML returns 82. The files themselves are deployed (`/assets/images/pdh-logo.png` returns 200). |
| P0-2 | **Runtime dependency on tgh.org** for CSS, JS, icons and some images | If TGH changes, renames or blocks hotlinking, the whole layout, the menus and the icons break with no warning. | `<base href="https://www.tgh.org/">`, `/assets/css/global.css` and `/assets/js/main.js` both resolve to tgh.org. |
| P0-3 | **Logo links go to tgh.org** | Clicking the PDH logo in the header or footer takes visitors to Tampa General's website. | `href="/"` resolves against `<base>`. |
| P0-4 | **Licensing and IP exposure** | The site runs TGH's proprietary CSS and JS, TGH's Adobe Fonts kit and TGH's layout. `tgh-reference.html`, a full copy of TGH's homepage, is publicly served at `/tgh-reference.html`. That's acceptable for an internal prototype, but it's a legal risk for a public hospital website. | `/tgh-reference.html`, `/index-backup.html`, `/pdh-homepage.html` and `/tools/export_pdh_content.py` all return 200. |
| P0-5 | **Two sources of truth, plus an uncommitted fix** | The logo-alignment fix exists in `pdh-homepage.html` but isn't in `index.html`, the file that's actually deployed. | `diff index.html pdh-homepage.html` |
| P1-1 | Icons (chevrons, emergency icons) | They render only if TGH's script can load its icon sprite cross-origin. **Needs checking in a browser.** | 64 icon references, 0 icon definitions in the page. |
| P1-2 | Fonts | TGH's Adobe Fonts kit may refuse to serve fonts to `vercel.app`, which would silently fall back to a different font. **Needs checking in a browser.** | The kit CSS returns 200; the font files are domain-restricted by Adobe. |
| P1-3 | "Find a Doctor" | Links to the old site's directory. There's no search or filtering on the new site. | |
| P1-4 | Search | Works, but leaves the new site, and the results are WordPress pages. | |
| P1-5 | Repository bloat | 85 of the 86 root images are identical copies of files in `assets/images/pdh/` (25 MB). Some originals are very large: a 6.3 MB doctor PNG and a 3.7 MB network map. | |
| P1-6 | Missing SEO files | `robots.txt`, `sitemap.xml` and `favicon.ico` return 404. There's no structured data (JSON-LD) at all. | |

---

## 4. Missing functionality (against your goals A–F)

| Goal | Status |
|---|---|
| **A. AI Hospital Concierge** | Not present. No chat UI, no backend, no knowledge base. |
| **B. Smart lead generation** | Not present. No forms on the site, no inquiry storage, no notifications. The only intake is the external HMO Google Form. |
| **C. Smart Doctor Finder** | Not present. Data available: 289 doctor names and photos from the API. Specialty and schedule are only on the old directory page, which is paginated (`/all-doctors/page/N/`) and can be exported. |
| **D. Interactive experience** | No on-site search, service finder, map or floor guide. Real floor data exists, e.g. ER on the ground floor, Hemodialysis on the 2nd, ICU/NICU/PICU on the 3rd, OPD on the 3rd–6th, Nuclear Medicine on the 7th. |
| **E. Advanced AI** | Not present: natural-language search, voice, recommendations, inquiry routing. |
| **F. Technical** | Mobile layout works (TGH's responsive CSS). Missing: image optimisation, JSON-LD, sitemap, robots.txt, security headers (CSP), a consent banner, an accessibility audit. |

---

## 5. Recommended improvements

### Phase 0: Stabilise production (required before anything else)

1. **Fix all image paths.** Replace `http://127.0.0.1:5500/…` with root-relative PDH paths (`/assets/images/…`).
2. **Self-host the remaining runtime assets.** Move the CSS, JS behaviour and icons into the repo so nothing loads from tgh.org, then remove `<base href>`.
   - **Recommended:** replace TGH's `main.js` with a small PDH script (`assets/js/pdh-nav.js`) that only does what the page uses: dropdowns, mobile drill-down, sticky header, search toggle.
   - Replace the TGH font kit with an openly licensed font (for example from Google Fonts).
   - This step also mostly resolves the licensing exposure in P0-4.
3. **Point logo links to `/`** (the PDH homepage).
4. **Remove non-production files from the deployment:** `tgh-reference.html`, `index-backup.html`, `tools/` and the duplicate root images. Either keep them out of the repo or exclude them with `.vercelignore`.
5. **Single source of truth:** keep `index.html` as the only page file and drop `pdh-homepage.html` after merging the logo fix.
6. **Add `vercel.json`** with security headers (CSP, `X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy` allowing the microphone only on the site itself, for voice) and clean URLs.

### Phase 1: Verified data layer (the foundation for C, A and E)

7. **`data/` folder (JSON, committed and versioned):**
   - `services.json`: name, description, floor, phone, hours, URL. Source: the Our Services page plus each service page.
   - `doctors.json`: name, specialty, sub-specialty, clinic schedule, phone, photo. Source: the paginated `/all-doctors/` directory plus the API.
   - `contacts.json`: hotlines, address, email.
   - `hmo-partners.json`: name and logo.
   - `hospital.json`: profile, mission, vision, core values, leadership, barangay partners.
   - `faq.json`: only answers PDH has verified. Created later, filled by hospital staff (not generated).
8. **`tools/build_pdh_data.py`** (built 25 Nov 2026): scrapes the paginated doctor directory and the services, contact and About pages, and writes all `data/*.json` files. Each record carries `review_status` (`pending` / `verified`), `reviewed_by`, `reviewed_at` and a content fingerprint. Re-running keeps review status for unchanged records and resets changed ones to `pending` with `changed_since_review: true`.
9. **A human review step:** someone at PDH signs off on the JSON before it's used by the chatbot. This is the "verified hospital information" requirement in goal A.

### Phase 2: Lead generation and Doctor Finder (goals B and C)

10. **Serverless inquiry endpoint `/api/inquiry`** (a Vercel Function, plain Node with no framework):
    - **Types:** appointment request, callback request, general inquiry, HMO question.
    - **Validation on the server**, plus spam protection (honeypot field and per-IP rate limiting).
    - **Rule-based categorisation and routing** (for example HMO → HMO Hub, emergency keywords → show the ER number immediately rather than queueing).
    - **Storage and staff notification** (see §6 for the options).
    - **Data Privacy Act (RA 10173) compliance:** an explicit consent checkbox linked to PDH's privacy policy, collect only what's needed, no diagnosis details stored.
11. **Inquiry forms:** one reusable form component used in four places: a "Request an Appointment" section on the homepage, doctor profiles, service cards, and a "Request a Callback" link in the header and footer.
12. **Doctor Finder page `/doctors/`:** client-side search by name and specialty, filters (specialty, day of week), and an "Request an appointment" button on every card. No extra dependencies; it filters `doctors.json` in the browser.
13. **Doctor profile pages `/doctors/<slug>/`:** generated as static HTML by a Python tool from `doctors.json`. That makes them fast, crawlable and SEO-friendly, each with `Physician` JSON-LD and a pre-filled appointment-request form.
14. **Contextual calls to action:** service pages and doctor pages pre-fill the form's "department" and "doctor" fields.

### Phase 3: AI Concierge and smart search (goals A, D and E)

15. **`/api/chat`:** a Claude-powered concierge (Claude Haiku 5.5 for speed and cost), grounded only in `data/*.json`.
    - **Answers** questions about services, floors, hours, HMOs and doctors.
    - **Says "I don't know"** and offers a callback when the answer isn't in the verified data.
    - **No medical advice or diagnosis.** Emergency phrases trigger an immediate ER hotline response.
    - **Hands off** to the inquiry form with the conversation's context pre-filled. A chat can turn into a real lead.
    - **API key** stored as a Vercel environment variable, never sent to the browser. Rate-limited.
16. **Chat widget** (`assets/js/pdh-concierge.js`): accessible (keyboard, screen reader and focus handling), mobile-first, loads only when opened.
17. **Natural-language search:** the same `/api/chat` backend in "search mode". For example, "dialysis on Saturday" returns matching services and doctors as links. Replaces the WordPress search redirect.
18. **Interactive service finder:** a guided "What do you need help with?" picker built over `services.json`, with no AI dependency.
19. **Hospital map:**
    - A Google Maps embed of 175 Doña Soledad Ave., with no API key needed.
    - An interactive **floor directory** generated from the verified floor data in `services.json`.

### Phase 4: Enhancements

20. **Voice:** the browser's built-in Web Speech API, so no extra dependency. Voice input goes into the concierge; read-aloud is optional. It's shown only on browsers that support it (Chrome, Edge, Safari); Firefox users get text only.
21. **AI-assisted inquiry triage:** Claude classifies free-text inquiries into department and urgency to supplement the rule-based routing. A human always sees the original message.
22. **Recommendations:** "Related services" and "doctors for this service" from the data relationships, with no tracking needed.
23. **Personalised journeys:** session-only context (for example, a visitor viewing OB services sees OB doctors and an OB inquiry form). No cross-visit tracking without consent.
24. **SEO and AI-search discoverability:** `Hospital` / `MedicalOrganization` / `Physician` JSON-LD, `sitemap.xml`, `robots.txt`, `llms.txt`.
25. **Performance:** recompress large images (WebP or AVIF, width variants), lazy-load below-the-fold media, defer the Vimeo iframe.
26. **Accessibility:** a WCAG 2.2 AA pass covering contrast, focus order, the menu's keyboard behaviour, form labels and errors.
27. **Animations:** subtle reveal and transition effects that respect `prefers-reduced-motion`. Lowest priority.

---

## 6. Required technologies and integrations

| Need | Recommendation | New dependency? |
|---|---|---|
| Backend | **Vercel Functions** (`/api/*.js`, Node runtime) | None. Built into Vercel. |
| AI | **Claude API** (Claude Haiku 5.5 for the concierge, Claude Sonnet 5.5 optional for triage), called with `fetch` | None (no SDK needed). Needs an Anthropic API key. |
| Inquiry storage | **Decision needed. See below.** | Depends on the option. |
| Staff notifications | Email through a transactional service (e.g. Resend), or a Google Sheets notification | An API key. Resend needs a verified sending domain. |
| Spam protection | Honeypot field and rate limiting. Cloudflare Turnstile optional. | None, or a Turnstile key. |
| Maps | Google Maps embed iframe | None, no key. |
| Voice | Web Speech API | None. |
| Doctor and content data | Existing Python tool plus a new doctor exporter | None (Python standard library). |

**Inquiry storage options (your decision):**

| Option | Pros | Cons |
|---|---|---|
| **A. Google Sheets** | Staff can use it immediately. Matches your existing workflow (outputs to Google Sheets). Free. | Weak access control and audit trail for personal health-related data. Needs a Google service account. |
| **B. Postgres (Neon, via the Vercel Marketplace)** | Proper access control, audit-friendly, scalable. Free tier available. | Needs a simple staff view, or staff use Neon's console. |
| **C. Supabase** | Postgres with built-in auth and a ready-made table UI for staff. | One more vendor account. |

**Recommendation:** Option B or C for production, because these are patient inquiries covered by the Data Privacy Act. Option A is fine for a pilot if no medical details are collected.

**Environment variables (Vercel project settings):** `ANTHROPIC_API_KEY`, storage credentials, and the notification API key or recipient email address.

---

## 7. Files that would need modification

### Existing files to modify

| File | Changes |
|---|---|
| `index.html` | Fix image paths, remove `<base>`, fix logo links, swap in self-hosted CSS and JS, add the inquiry form section, chat widget loader, JSON-LD and Doctor Finder links. |
| `pdh-homepage.html` | Merge its logo fix into `index.html`, then retire it. |
| `.gitignore` | Add `.env` and local-only files. |
| `tools/export_pdh_content.py` | Optional: a `--data` flag to write curated JSON into `data/`. |

### New files

| File | Purpose |
|---|---|
| `vercel.json` | Security headers, clean URLs. |
| `.vercelignore` | Keep `tgh-reference.html`, backups, `tools/` and `.tmp/` off the live site. |
| `assets/css/pdh.css` | PDH styles moved out of the inline block, plus new components. |
| `assets/css/pdh-base.css` | Self-hosted base styles (replacing the hotlinked TGH stylesheet). |
| `assets/js/pdh-nav.js` | Menu, mobile menu and sticky header behaviour (replacing TGH's `main.js`). |
| `assets/js/pdh-inquiry.js` | The form component: validation, submission, success and error states. |
| `assets/js/pdh-doctors.js` | Doctor Finder search and filters. |
| `assets/js/pdh-concierge.js` | Chat widget and voice. |
| `api/inquiry.js` | Lead intake, validation, categorisation, storage, notification. |
| `api/chat.js` | AI concierge and natural-language search. |
| `data/services.json`, `doctors.json`, `contacts.json`, `hospital.json`, `hmo-partners.json`, `faq.json` | Verified knowledge base. |
| `doctors/index.html`, `doctors/<slug>/index.html` | Doctor Finder and profile pages (generated). |
| `tools/build_pdh_data.py`, `tools/build_pages.py` | Data export; generation of doctor pages, services directory and the homepage search index. |
| `robots.txt`, `sitemap.xml`, `llms.txt`, `favicon.ico` | SEO and discoverability. |
| `workflows/*.md` | Procedures for refreshing data and regenerating pages. Created only with your approval, per the project rules. |

---

## 8. Recommended implementation sequence

Each step is a small, separately deployable change. Each one is checked against the live Vercel preview before moving on.

| Step | Work | Depends on | Outcome |
|---|---|---|---|
| 1 | **Fix the production image paths** and logo links, merge the logo fix, single source file | none | Images load for all visitors |
| 2 | Clean up the deployment: `.vercelignore`, remove the public TGH reference and duplicate files | 1 | No TGH copies or tooling served publicly |
| 3 | Self-host CSS, JS, icons and fonts; remove `<base href>` | 1 | No runtime dependency on tgh.org |
| 4 | `vercel.json` security headers; `robots.txt`, `sitemap.xml`, JSON-LD | 3 | Secure baseline, indexable |
| 5 | Verified data layer (`data/*.json`), doctor export tool, **PDH review** | none (in parallel with 1–4) | Trusted single source for all features |
| 6 | Inquiry pipeline: `/api/inquiry` plus storage, notification and consent | 4, storage decision | Real, stored leads |
| 7 | Inquiry forms: appointment, callback, contextual pre-fill | 6 | Lead capture on the homepage |
| 8 | Doctor Finder and generated profile pages | 5, 7 | Searchable doctors with appointment CTAs |
| 9 | Service finder and floor directory, plus the map embed | 5 | Interactive wayfinding |
| 10 | AI Concierge (`/api/chat` and widget), with handoff to the inquiry form | 5, 7, API key | Grounded AI assistant |
| 11 | Natural-language search on the concierge backend | 10 | On-site smart search |
| 12 | Voice input, AI triage, recommendations, journeys | 10, 6 | Advanced AI layer |
| 13 | Performance, accessibility audit, animations | ongoing | Polish |

---

## Highest-priority improvements (awaiting approval)

1. **Fix broken images on the live site.** This is a critical production bug affecting every visitor today.
2. **Fix the logo links that send visitors to Tampa General.**
3. **Remove publicly served non-production files:** the TGH homepage copy, backups and tools.
4. **Decouple from tgh.org:** self-host the CSS, JS, icons and fonts, and remove `<base href>`. This fixes reliability and most of the licensing exposure.
5. **Build the verified data layer**, including the full doctor directory with specialties and schedules.
6. **Lead capture pipeline:** appointment and callback forms backed by a real endpoint and storage.

### Decisions needed from you

- **Approval to start Phase 0** (items 1–4).
- **Inquiry storage:** Google Sheets, Postgres (Neon) or Supabase.
- **Staff notification:** who receives inquiries, and by which channel.
- **Anthropic API key** for the concierge (Phase 3).
- **Data owner at PDH** to verify `data/*.json` before the chatbot uses it.
- **Brand assets:** an official transparent or white horizontal logo (SVG preferred).
- **Licensing:** confirm whether this site will stay internal or go public under PDH's name. If public, Step 3 should be treated as required, not optional.
