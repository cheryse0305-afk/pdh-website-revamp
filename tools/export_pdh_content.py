"""Export all content from the old PDH website (pdh.com.ph) via the WordPress REST API.

Usage:
    python tools/export_pdh_content.py            # text + data only
    python tools/export_pdh_content.py --images   # also download images used in content

Outputs (all regenerable):
    .tmp/pdh-content/raw/{pages,posts,doctors,media}.json   full API responses
    .tmp/pdh-content/pages/<slug>.md                        readable text per page
    .tmp/pdh-content/posts/<slug>.md                        readable text per news post
    .tmp/pdh-content/doctors.csv                            doctor name, URL, photo
    .tmp/pdh-content/images.csv                             every image used, with alt text
    assets/images/pdh/<file>                                downloaded images (--images)
"""

import argparse
import csv
import html
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser

BASE = "https://pdh.com.ph/wp-json/wp/v2/"
UA = {"User-Agent": "Mozilla/5.0 (PDH content export)"}
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, ".tmp", "pdh-content")
IMG_DIR = os.path.join(ROOT, "assets", "images", "pdh")


def get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read(), r.headers


def fetch_all(endpoint):
    """Fetch every item of an endpoint, following X-WP-TotalPages."""
    items, page = [], 1
    while True:
        body, headers = get(f"{BASE}{endpoint}?per_page=100&page={page}")
        items += json.loads(body)
        total = int(headers.get("X-WP-TotalPages", 1))
        print(f"  {endpoint}: page {page}/{total}")
        if page >= total:
            return items
        page += 1


class TextExtractor(HTMLParser):
    """Turn Elementor HTML into readable markdown-ish text, keeping images and links."""

    BLOCK = {"p", "div", "section", "li", "br", "tr", "h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lines, self.buf, self.skip, self.heading = [], [], 0, None
        self.images, self.links = [], []

    def flush(self):
        text = re.sub(r"\s+", " ", "".join(self.buf)).strip()
        self.buf = []
        if not text:
            return
        if self.heading:
            text = "#" * int(self.heading[1]) + " " + text
        if not self.lines or self.lines[-1] != text:  # Elementor repeats blocks
            self.lines.append(text)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("script", "style", "svg", "noscript"):
            self.skip += 1
        elif tag == "img":
            src = a.get("data-src") or a.get("src")
            if src and not src.startswith("data:"):
                self.images.append((src, a.get("alt") or ""))
                self.lines.append(f"![{a.get('alt') or ''}]({src})")
        elif tag == "a" and a.get("href"):
            self.links.append(a["href"])
        if tag in self.BLOCK:
            self.flush()
            if re.fullmatch(r"h[1-6]", tag):
                self.heading = tag

    def handle_endtag(self, tag):
        if tag in ("script", "style", "svg", "noscript"):
            self.skip = max(0, self.skip - 1)
        if tag in self.BLOCK:
            self.flush()
            if tag == self.heading:
                self.heading = None

    def handle_data(self, data):
        if not self.skip:
            self.buf.append(data)


def extract(rendered_html):
    p = TextExtractor()
    p.feed(rendered_html or "")
    p.flush()
    return p


def write_markdown(folder, item, media_by_id):
    title = html.unescape(item["title"]["rendered"])
    p = extract(item["content"]["rendered"])
    featured = media_by_id.get(item.get("featured_media"))
    header = [f"# {title}", "", f"Source: {item['link']}", f"Last modified: {item['modified']}"]
    if featured:
        header.append(f"Featured image: {featured['source_url']}")
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, f"{item['slug']}.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(header + ["", *p.lines]) + "\n")
    return p.images + ([(featured["source_url"], featured.get("alt_text", ""))] if featured else [])


def download(url):
    name = os.path.basename(urllib.parse.urlparse(url).path)
    dest = os.path.join(IMG_DIR, name)
    if os.path.exists(dest):
        return "skip"
    try:
        body, _ = get(url)
        with open(dest, "wb") as f:
            f.write(body)
        return "ok"
    except Exception as e:
        print(f"  failed: {url} ({e})", file=sys.stderr)
        return "fail"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", action="store_true", help="download images used in content")
    args = ap.parse_args()

    os.makedirs(os.path.join(OUT, "raw"), exist_ok=True)
    data = {}
    for name, endpoint in [("pages", "pages"), ("posts", "posts"), ("doctors", "doctor"), ("media", "media")]:
        print(f"Fetching {name}...")
        data[name] = fetch_all(endpoint)
        with open(os.path.join(OUT, "raw", f"{name}.json"), "w", encoding="utf-8") as f:
            json.dump(data[name], f, ensure_ascii=False, indent=1)

    media_by_id = {m["id"]: m for m in data["media"]}
    images = {}
    for kind in ("pages", "posts"):
        for item in data[kind]:
            for src, alt in write_markdown(os.path.join(OUT, kind), item, media_by_id):
                images.setdefault(src, alt)

    with open(os.path.join(OUT, "doctors.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["name", "slug", "url", "photo"])
        for d in sorted(data["doctors"], key=lambda d: d["title"]["rendered"]):
            photo = media_by_id.get(d["featured_media"], {}).get("source_url", "")
            if photo:
                images.setdefault(photo, d["title"]["rendered"])
            w.writerow([html.unescape(d["title"]["rendered"]), d["slug"], d["link"], photo])

    with open(os.path.join(OUT, "images.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["url", "alt", "local_file"])
        for src, alt in images.items():
            local = "assets/images/pdh/" + os.path.basename(urllib.parse.urlparse(src).path)
            w.writerow([src, alt, local])

    print(f"Pages: {len(data['pages'])}, posts: {len(data['posts'])}, "
          f"doctors: {len(data['doctors'])}, images referenced: {len(images)}")

    if args.images:
        os.makedirs(IMG_DIR, exist_ok=True)
        print(f"Downloading {len(images)} images to {IMG_DIR}...")
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(download, images))
        print({r: results.count(r) for r in set(results)})

    print(f"Done. Output in {OUT}")


if __name__ == "__main__":
    main()
