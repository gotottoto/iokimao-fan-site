
#!/usr/bin/env python3
"""Collect official Mao Ioki blog entries for manual review."""

import json
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "blog_pending.json"
SOURCE = (
    "https://www.nogizaka46.com/s/n46/diary/MEMBER/list"
    "?cd=MEMBER&ct=55396"
)
BASE = "https://www.nogizaka46.com"


def clean_url(url):
    """Remove tracking parameters so the same post has one stable URL."""
    parts = urlsplit(url)
    return urlunsplit((
        parts.scheme,
        parts.netloc,
        parts.path,
        "",
        "",
    ))


class BlogParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.entries = []
        self.current_link = None
        self.current_text = []
        self.in_link = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag != "a" or not attrs.get("href"):
            return

        href = urljoin(BASE, attrs["href"])
        if "/s/n46/diary/detail/" not in href:
            return

        self.current_link = clean_url(href)
        self.current_text = []
        self.in_link = True

    def handle_data(self, data):
        if self.in_link:
            text = re.sub(r"\s+", " ", data).strip()
            if text:
                self.current_text.append(text)

    def handle_endtag(self, tag):
        if tag != "a" or not self.in_link:
            return

        raw_title = " ".join(self.current_text).strip()
        match = re.match(
            r"^(.*?)\s+(\d{4})\.(\d{2})\.(\d{2})"
            r"(?:\s+(\d{2}):(\d{2}))?$",
            raw_title,
        )

        if match and match.group(1).strip():
            title = match.group(1).strip()
            year, month, day = map(int, match.group(2, 3, 4))
            date_text = f"{year:04d}-{month:02d}-{day:02d}"

            try:
                datetime(year, month, day)
            except ValueError:
                date_text = None
        else:
            title = raw_title
            date_text = None

        if title and self.current_link:
            self.entries.append({
                "title": title,
                "date": date_text,
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
        if entry["url"] not in unique:
            unique[entry["url"]] = entry

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    if OUTPUT.exists():
        try:
            existing = json.loads(OUTPUT.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise SystemExit(f"Cannot read existing review data: {exc}")
    else:
        existing = []

    if not isinstance(existing, list):
        raise SystemExit("Review file must contain a JSON list.")

    known = {
        clean_url(item["url"])
        for item in existing
        if isinstance(item, dict) and isinstance(item.get("url"), str)
    }

    added = []
    now = datetime.now(timezone.utc).isoformat()

    for url, entry in unique.items():
        if url in known:
            continue
        entry["detected_at"] = now
        added.append(entry)

    OUTPUT.write_text(
        json.dumps(existing + added, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    missing_dates = sum(1 for item in unique.values() if not item["date"])

    print(f"Official blog links found: {len(unique)}")
    print(f"New review candidates added: {len(added)}")
    print(f"Entries needing date review: {missing_dates}")
    print(f"Review file: {OUTPUT.relative_to(ROOT)}")
    print("Existing HTML was not changed; nothing was published.")


if __name__ == "__main__":
    main()
