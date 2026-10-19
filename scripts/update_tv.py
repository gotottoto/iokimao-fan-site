#!/usr/bin/env python3
"""Collect official Nogizaka Koujichuu preview candidates."""

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
        href = attrs.get("href", "")

        if tag == "a" and href:
            absolute = urljoin(BASE, href)
            path = urlsplit(absolute).path

            if "/news/detail/" in path:
                self.href = stable_url(absolute)
                self.parts = []

    def handle_data(self, data):
        if self.href:
            text = re.sub(r"\s+", " ", data).strip()
            if text:
                self.parts.append(text)

    def handle_endtag(self, tag):
        if tag == "a" and self.href:
            title = " ".join(self.parts).strip()
            if title:
                self.links.append((self.href, title))

            self.href = None
            self.parts = []


def fetch(url: str) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; MaoIokiFanSite/1.0)"
        },
    )
    with urlopen(request, timeout=30) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def main() -> int:
    page = fetch(NEWS_URL)

    parser = NewsParser()
    parser.feed(page)

    print(f"Fetched page: {NEWS_URL}")
    print(f"Official news detail links found: {len(parser.links)}")

    # Diagnostic output: show matching titles even if they are not
    # recognized as previews.
    matching = [
        (url, title)
        for url, title in parser.links
        if "乃木坂工事中" in title
    ]

    print(f"Links mentioning 乃木坂工事中: {len(matching)}")
    for url, title in matching[:20]:
        print(f"  TITLE: {title}")
        print(f"  URL: {url}")

    candidates = [
        (url, title)
        for url, title in matching
        if "次回予告" in title or "次回" in title
    ]

    if OUTPUT.exists():
        existing = json.loads(OUTPUT.read_text(encoding="utf-8"))
    else:
        existing = []

    if not isinstance(existing, list):
        raise SystemExit("tv_episodes.json must contain a JSON list.")

    known = {
        stable_url(item["source_url"])
        for item in existing
        if isinstance(item, dict) and item.get("source_url")
    }

    added = 0
    now = datetime.now(timezone.utc).isoformat()

    for url, title in candidates:
        url = stable_url(url)

        if url in known:
            continue

        existing.append({
            "date": None,
            "category": "レギュラー",
            "title": title,
            "detail": (
                "公式の次回予告候補。放送日・内容・"
                "五百城茉央の出演有無を確認してください。"
            ),
            "url": url,
            "source_url": url,
            "appearance": "要確認",
            "status": "needs_review",
            "detected_at": now,
        })

        known.add(url)
        added += 1

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(existing, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Official preview candidates found: {len(candidates)}")
    print(f"New review candidates added: {added}")
    print("Existing records preserved; appearance status was not guessed.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
