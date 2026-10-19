#!/usr/bin/env python3
"""Add new official blog links to the existing archive cards."""

import json
import re
import html
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BLOG_HTML = ROOT / "blog.html"
PENDING_JSON = ROOT / "data" / "blog_pending.json"


def article_id(url):
    match = re.search(r"/diary/detail/(\d+)", url)
    return match.group(1) if match else None


def parse_entry(item):
    title = (item.get("title") or "").strip()
    url = (item.get("url") or "").strip()

    if not url.startswith("https://www.nogizaka46.com/"):
        return None
    if not article_id(url):
        return None

    # update_blog.py stores the date separately and may leave no date in title.
    date = None
    date_value = item.get("date")
    if isinstance(date_value, str) and date_value.strip():
        try:
            date = datetime.strptime(date_value[:10], "%Y-%m-%d")
        except ValueError:
            date = None

    # Backward compatibility for older pending entries whose title ends in a date.
    # New candidates may store the date in a separate "date" field.
    date = None
    date_value = item.get("date")
    if isinstance(date_value, str) and date_value.strip():
        try:
            date = datetime.strptime(date_value[:10], "%Y-%m-%d")
        except ValueError:
            date = None

    # Keep compatibility with older entries that append the date to the title.
    match = re.search(
        r"\\s+(\\d{4})[./-](\\d{2})[./-](\\d{2})(?:\\s+\\d{1,2}:\\d{2})?$",
        title,
    )
    clean_title = title
    if match:
        if date is None:
            year, month, day = map(int, match.groups())
            try:
                date = datetime(year, month, day)
            except ValueError:
                return None
        clean_title = title[:match.start()].strip()

    if date is None or not clean_title:
        return None

    return {
        "id": article_id(url),
        "url": url,
        "date": date,
        "title": clean_title,
    }


def make_card(item):
    date_text = item["date"].strftime("%Y.%m.%d")
    title = html.escape(item["title"], quote=True)
    url = html.escape(item["url"], quote=True)
    return (
        f'<a class="post" href="{url}" rel="noopener" target="_blank">'
        '<div class="post-content">'
        f'<time>{date_text}</time>'
        f'<h3>{title}</h3>'
        '<span class="go">公式ブログで読む ↗</span>'
        '</div></a>'
    )


def main():
    if not BLOG_HTML.exists() or not PENDING_JSON.exists():
        raise SystemExit("blog.html or blog_pending.json is missing.")

    source = BLOG_HTML.read_text(encoding="utf-8")
    entries = json.loads(PENDING_JSON.read_text(encoding="utf-8"))
    if not isinstance(entries, list):
        raise SystemExit("blog_pending.json must contain a JSON list.")

    existing_ids = set(re.findall(
        r'href=["\'][^"\']*/diary/detail/(\d+)', source
    ))
    added = 0
    skipped = 0

    for raw in entries:
        if not isinstance(raw, dict):
            skipped += 1
            continue
        item = parse_entry(raw)
        if not item or item["id"] in existing_ids:
            skipped += 1
            continue

        year = item["date"].year
        section_pattern = (
            r'(<section\b[^>]*\bid="y'
            + str(year)
            + r'"[^>]*>.*?<div class="posts">)'
            r'(.*?)'
            r'(</div>\s*</section>)'
        )
        section = re.search(section_pattern, source, re.S)
        if not section:
            print(f"Skipped: no archive section for {year}")
            skipped += 1
            continue

        cards = section.group(2)
        new_card = make_card(item)
        card_pattern = re.compile(r'<a class="post"\b.*?</a>', re.S)
        insert_at = len(cards)
        for card in card_pattern.finditer(cards):
            date_match = re.search(
                r'<time>(\d{4}\.\d{2}\.\d{2})</time>', card.group()
            )
            if not date_match:
                continue
            old_date = datetime.strptime(date_match.group(1), "%Y.%m.%d")
            if old_date < item["date"]:
                insert_at = card.start()
                break

        cards = cards[:insert_at] + new_card + cards[insert_at:]
        source = (
            source[:section.start()]
            + section.group(1)
            + cards
            + section.group(3)
            + source[section.end():]
        )
        existing_ids.add(item["id"])
        added += 1

    if added:
        BLOG_HTML.write_text(source, encoding="utf-8")
    print(f"New cards added: {added}")
    print(f"Skipped or already listed: {skipped}")
    print("Existing card styles and other pages were preserved.")


if __name__ == "__main__":
    main()
