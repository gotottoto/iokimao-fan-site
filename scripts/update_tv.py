#!/usr/bin/env python3
"""Collect official Nogizaka Koujichuu preview links as review candidates.

This deliberately does NOT guess Mao Ioki's appearance status or publish episode
summaries as confirmed. The official preview/news page is used as a candidate
source; review candidates are merged into data/tv_episodes.json without deleting
existing records.
"""
from __future__ import annotations
import json
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "tv_episodes.json"
NEWS_URL = "https://www.nogizaka46.com/s/n46/news/list"
BASE = "https://www.nogizaka46.com"


def stable_url(url: str) -> str:
    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc, p.path, "", ""))


class NewsParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.href = None
        self.parts = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a" and attrs.get("href") and "/s/n46/news/detail/" in attrs["href"]:
            self.href = stable_url(urljoin(BASE, attrs["href"]))
            self.parts = []

    def handle_data(self, data):
        if self.href:
            s = re.sub(r"\s+", " ", data).strip()
            if s:
                self.parts.append(s)

    def handle_endtag(self, tag):
        if tag == "a" and self.href:
            title = " ".join(self.parts).strip()
            if title:
                self.links.append((self.href, title))
            self.href = None
            self.parts = []


def fetch(url: str) -> str:
    req = Request(url, headers={"User-Agent": "MaoIokiFanSite/1.0 (official preview candidate collector)"})
    with urlopen(req, timeout=30) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def main() -> int:
    try:
        html = fetch(NEWS_URL)
    except Exception as exc:
        raise SystemExit(f"Official news fetch failed; existing data was not changed: {exc}")

    parser = NewsParser()
    parser.feed(html)
    # Only collect links whose visible title looks like an official programme preview.
    candidates = [(url, title) for url, title in parser.links if "乃木坂工事中" in title and ("次回予告" in title or "次回" in title)]

    if OUTPUT.exists():
        try:
            existing = json.loads(OUTPUT.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SystemExit(f"Cannot read {OUTPUT}: {exc}")
    else:
        existing = []
    if not isinstance(existing, list):
        raise SystemExit("data/tv_episodes.json must contain a JSON list")

    known = {stable_url(x.get("source_url", "")) for x in existing if isinstance(x, dict) and x.get("source_url")}
    now = datetime.now(timezone.utc).isoformat()
    added = 0
    for url, title in candidates:
        url = stable_url(url)
        if url in known:
            continue
        existing.append({
            "date": None,
            "category": "レギュラー",
            "title": title,
            "detail": "公式の次回予告候補。放送日・内容・五百城茉央の出演有無を確認してください。",
            "url": url,
            "source_url": url,
            "appearance": "要確認",
            "status": "needs_review",
            "detected_at": now,
        })
        known.add(url)
        added += 1

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(existing, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Official preview candidates found: {len(candidates)}")
    print(f"New review candidates added: {added}")
    print("No appearance status was guessed; existing episode records were preserved.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
