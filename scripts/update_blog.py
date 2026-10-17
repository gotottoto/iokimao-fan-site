
#!/usr/bin/env python3
"""Collect official Mao Ioki blog entries for manual review."""

import json
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen
from urllib.parse import urljoin

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "blog_pending.json"
SOURCE = (
    "https://www.nogizaka46.com/s/n46/diary/MEMBER/list"
    "?cd=MEMBER&ct=55396"
)
BASE = "https://www.nogizaka46.com"


class BlogParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.entries = []
        self.current_link = None
        self.current_text = []
        self.in_link = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a" and attrs.get("href"):
            href = urljoin(BASE, attrs["href"])
            if "/s/n46/diary/detail/" in href:
                self.current_link = href
                self.current_text = []
                self.in_link = True

    def handle_data(self, data):
        if self.in_link:
            text = re.sub(r"\s+", " ", data).strip()
            if text:
                self.current_text.append(text)

    def handle_endtag(self, tag):
        if tag == "a" and self.in_link:
            title = " ".join(self.current_text).strip()
            if title and self.current_link:
                self.entries.append({
                    "title": title,
                    "url": self.current_link,
                    "category": "blog",
                    "source": SOURCE,
                    "status": "needs_review",
                })
            self.current_link = None
            self.current_text = []
            self.in_link = False


def main():
    request = Request(
        SOURCE,
        headers={"User-Agent": "MaoIokiFanSite/1.0"},
    )

    try:
        with urlopen(request, timeout=30) as response:
            html = response.read().decode(
                response.headers.get_content_charset() or "utf-8",
                errors="replace",
            )
    except (URLError, TimeoutError, OSError) as exc:
        raise SystemExit(f"Official blog fetch failed: {exc}")

    parser = BlogParser()
    parser.feed(html)

    unique = {}
    for entry in parser.entries:
        unique[entry["url"]] = entry

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    if OUTPUT.exists():
        try:
            existing = json.loads(
                OUTPUT.read_text(encoding="utf-8")
            )
        except (json.JSONDecodeError, OSError):
            raise SystemExit(
                "Existing review file is unreadable; refusing to overwrite it."
            )
    else:
        existing = []

    if not isinstance(existing, list):
        raise SystemExit("Review file must contain a JSON list.")

    known_urls = {
        item.get("url")
        for item in existing
        if isinstance(item, dict)
    }

    added = []
    for url, entry in unique.items():
        if url not in known_urls:
            entry["detected_at"] = datetime.now(
                timezone.utc
            ).isoformat()
            added.append(entry)

    OUTPUT.write_text(
        json.dumps(existing + added, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Official blog links found: {len(unique)}")
    print(f"New review candidates added: {len(added)}")
    print(f"Review file: {OUTPUT.relative_to(ROOT)}")
    print("No HTML pages were modified or published.")


if __name__ == "__main__":
    main()
