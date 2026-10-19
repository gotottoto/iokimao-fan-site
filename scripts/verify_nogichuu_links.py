#!/usr/bin/env python3
"""Verify candidate official Nogizaka Koujichuu episode links before publishing.

Reads data/nogichuu_research.json and checks each candidate TV Tokyo detail URL.
For known TV Tokyo URL patterns, tries both 24:00 and 24:30 schedule variants.
It never invents episode titles: it records the official page title only when a
matching official page is successfully fetched.
"""
from __future__ import annotations
import json
import re
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
FILE = ROOT / "data" / "nogichuu_research.json"
UA = "Mozilla/5.0 (compatible; MaoIokiFanSite/1.0)"
BASE = "https://www.tv-tokyo.co.jp/broad_tvtokyo/program/detail"

class PageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.h1 = False
        self.title = False
        self.parts = []
        self.page_title = []
        self.og_title = None
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "h1":
            self.h1 = True
        if tag == "title":
            self.title = True
        if tag == "meta" and a.get("property") == "og:title":
            self.og_title = a.get("content")
    def handle_endtag(self, tag):
        if tag == "h1":
            self.h1 = False
        if tag == "title":
            self.title = False
    def handle_data(self, data):
        value = re.sub(r"\s+", " ", data).strip()
        if value and self.h1:
            self.parts.append(value)
        if value and self.title:
            self.page_title.append(value)

def fetch(url):
    req = Request(url, headers={"User-Agent": UA})
    with urlopen(req, timeout=15) as res:
        body = res.read().decode(res.headers.get_content_charset() or "utf-8", errors="replace")
        return res.status, body

def candidates(url):
    p = urlsplit(url)
    m = re.search(r"/(20\d{2})(\d{2})/21932_(20\d{2})(\d{2})(\d{2})(2400|2430)\.html$", p.path)
    if not m:
        return [url]
    year, month, y2, m2, day, _clock = m.groups()
    stem = f"{BASE}/{year}{month}/21932_{y2}{m2}{day}"
    return [stem + "2400.html", stem + "2430.html"]

def main():
    if not FILE.exists():
        raise SystemExit(f"Missing research file: {FILE}")
    data = json.loads(FILE.read_text(encoding="utf-8"))
    rows = data.get("episodes", [])
    checked = verified = failed = 0
    now = datetime.now(timezone.utc).isoformat()
    for row in rows:
        if str(row.get("link_status", "")).startswith("verified"):
            continue
        original = row.get("url", "")
        if not original:
            row["link_status"] = "missing_url"
            failed += 1
            continue
        checked += 1
        matched = False
        for url in candidates(original):
            try:
                status, html = fetch(url)
            except (HTTPError, URLError, TimeoutError, OSError) as exc:
                print(f"FETCH_FAIL #{row.get('episode')}: {url} ({exc})")
                continue
            if status >= 400 or "乃木坂工事中" not in html:
                continue
            parser = PageParser()
            parser.feed(html)
            title = parser.og_title or " ".join(parser.parts) or " ".join(parser.page_title)
            if not title or "乃木坂工事中" not in title:
                # The page must explicitly identify the show before we accept it.
                continue
            row["url"] = url
            row["source_url"] = url
            row["official_page_title"] = title
            row["link_status"] = "verified_official_broadcaster"
            row["verified_at"] = now
            row["status"] = "verified"
            matched = True
            verified += 1
            print(f"VERIFIED #{row.get('episode')} {row.get('date')} | {url} | {title}")
            break
        if not matched:
            row["link_status"] = "not_found_or_unconfirmed"
            row["last_link_check_at"] = now
            failed += 1
            print(f"UNCONFIRMED #{row.get('episode')} {row.get('date')} | {original}")
        time.sleep(0.15)
    data["last_link_check_at"] = now
    data["verified_count"] = sum(1 for x in rows if str(x.get("link_status", "")).startswith("verified"))
    data["unverified_count"] = len(rows) - data["verified_count"]
    FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"LINK CHECK COMPLETE: checked={checked}, newly_verified={verified}, unconfirmed={failed}, total={len(rows)}, verified_total={data['verified_count']}")
if __name__ == "__main__":
    main()
