
#!/usr/bin/env python3
"""Collect official Nogizaka Koujichuu schedule and preview candidates."""

from __future__ import annotations

import json
import re
import time
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "tv_episodes.json"

BASE = "https://www.nogizaka46.com"
SCHEDULE_URL = BASE + "/s/n46/media/list?ima=0000&pri1={ym}&wd00={year}&wd01={month}&wd02=01"
NEWS_URLS = [
    "https://sp.nogizaka46.com/p/news",
    BASE + "/s/n46/news/list",
]

USER_AGENT = "Mozilla/5.0 (compatible; MaoIokiFanSite/1.0)"
MAX_MONTHS = 36


def stable_url(url: str) -> str:
    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc, p.path.rstrip("/"), "", ""))


def fetch(url: str) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=30) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


class LinkParser(HTMLParser):
    """Collect relevant official links; derive article titles from detail pages."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self.href = None
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "a":
            return
        attrs = dict(attrs)
        href = attrs.get("href", "")
        if not href:
            return
        absolute = stable_url(urljoin(BASE, href))
        path = urlsplit(absolute).path
        if (
            "/s/n46/media/detail/" in path
            or "/s/n46/news/detail/" in path
            or "/p/news/" in path
        ):
            self.href = absolute
            self.parts = []

    def handle_data(self, data):
        if self.href:
            value = re.sub(r"\\s+", " ", data).strip()
            if value:
                self.parts.append(value)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self.href:
            title = " ".join(self.parts).strip()
            self.links.append((self.href, title))
            self.href = None
            self.parts = []


def month_range(count):
    today = date.today()
    year, month = today.year, today.month

    for _ in range(count):
        yield f"{year:04d}{month:02d}"
        month -= 1
        if month == 0:
            month = 12
            year -= 1


def extract_date(text):
    match = re.search(r"(20\d{2})[./年-](\d{1,2})[./月-](\d{1,2})", text)
    if not match:
        return None
    try:
        return date(
            int(match.group(1)),
            int(match.group(2)),
            int(match.group(3)),
        ).isoformat()
    except ValueError:
        return None


def load_existing():
    if not OUTPUT.exists():
        return []

    try:
        data = json.loads(OUTPUT.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Cannot read existing TV data: {exc}")

    if not isinstance(data, list):
        raise SystemExit("tv_episodes.json must contain a JSON list.")

    return data


def main():
    existing = load_existing()
    now = datetime.now(timezone.utc).isoformat()

    # Preserve all existing records. Deduplicate new discoveries by URL.
    known_urls = {
        stable_url(item.get("url", ""))
        for item in existing
        if isinstance(item, dict) and item.get("url")
    }

    added_schedule = 0
    added_previews = 0
    failed_pages = 0
    schedule_links_found = 0

    # Collect historical and current official schedule entries.
    for ym in month_range(MAX_MONTHS):
        url = SCHEDULE_URL.format(ym=ym, year=ym[:4], month=ym[4:6])

        try:
            page = fetch(url)
        except Exception as exc:
            print(f"Schedule fetch failed ({ym}): {exc}")
            failed_pages += 1
            continue

        
       
        # Parse anchors with HTMLParser rather than a regex. Official pages can
        # contain nested markup and attributes that make a simple regex brittle.
        parser = LinkParser()
        parser.feed(page)
        links = []
        seen_page_urls = set()
        for raw_link, title in parser.links:
            if "/s/n46/media/detail/" not in raw_link:
                continue
            link = stable_url(raw_link)
            if link in seen_page_urls:
                continue
            seen_page_urls.add(link)
            links.append((link, title))

        # Keep a small diagnostic so a successful HTTP response with an empty
        # result is distinguishable from a network failure.
        if not links:
            print(f"Schedule {ym}: no media detail anchors parsed; HTML length={len(page)}")
            print("HTML preview:", re.sub(r"\\s+", " ", page[:300])[:300])
        else:
            print(f"Schedule {ym}: {len(links)} official media links")
            print("Link samples:", links[:5])
        schedule_links_found += len(links)

        for link, title in links:
            link = stable_url(link)
            if link in known_urls:
                continue

            try:
                detail_page = fetch(link)
            except Exception as exc:
                print(f"Detail fetch failed: {link}: {exc}")
                failed_pages += 1
                continue

            # The official detail page contains the broadcast date.
            clean_text = re.sub(r"<[^>]+>", " ", detail_page)
            clean_text = re.sub(r"\s+", " ", clean_text)

            page_title = re.search(
                r"<h1\b[^>]*>(.*?)</h1>",
                detail_page,
                re.I | re.S,
            )
            title_text = ""
            if page_title:
                title_text = re.sub(r"<[^>]+>", " ", page_title.group(1))
                title_text = re.sub(r"\s+", " ", title_text).strip()
                if title_text:
                    title = title_text

            # The schedule page may contain unrelated media entries. Confirm the
            # programme on the detail page before adding any TV episode.
            if "乃木坂工事中" not in title_text and "乃木坂工事中" not in clean_text:
                continue

            broadcast_date = extract_date(clean_text)

            # Only add records when the official detail page confirms
            # the date. Never guess a broadcast date from the listing.
            if not broadcast_date:
                print(f"Date not confirmed; skipped: {link}")
                continue

            existing.append({
                "date": broadcast_date,
                "category": "レギュラー",
                "title": "テレビ東京系「乃木坂工事中」",
                "detail": "公式スケジュールに掲載された放送回。",
                "url": link,
                "source_url": link,
                "status": "official_schedule",
                "detected_at": now,
            })
            known_urls.add(link)
            added_schedule += 1

            time.sleep(0.3)

        time.sleep(0.3)

    # Fallback: inspect monthly official news archives. Archive card text can be
    # outside the anchor, so identify candidate article URLs first and inspect
    # each official detail page for its real title and publication date.
    news_urls = []
    for ym in month_range(MAX_MONTHS):
        news_urls.extend([
            BASE + f"/s/n46/news/list?dy={ym}",
            BASE + f"/s/n46/news/list?ima=0000&pri1={ym}",
        ])
    news_urls.extend(NEWS_URLS)

    seen_news = set()
    article_urls = []
    for news_url in news_urls:
        try:
            page = fetch(news_url)
        except Exception as exc:
            print(f"News fetch failed: {news_url}: {exc}")
            failed_pages += 1
            continue

        parser = LinkParser()
        parser.feed(page)
        for link, list_title in parser.links:
            path = urlsplit(link).path
            if ("/s/n46/news/detail/" in path or "/p/news/" in path) and link not in seen_news:
                seen_news.add(link)
                article_urls.append((link, list_title))
        time.sleep(0.1)

    print("Official news article links discovered:", len(article_urls))
    for link, list_title in article_urls:
        print(f"NEWS INDEX ITEM: title={list_title!r} | url={link}")
    for link, list_title in article_urls:
        if link in known_urls:
            continue
        # Use a title already present in the official index when available.
        if "乃木坂工事中" in list_title and ("次回予告" in list_title or "次回" in list_title):
            article_id_match = re.search(r"/(?:p/news/|s/n46/news/detail/)(\d+)", urlsplit(link).path)
            article_id = article_id_match.group(1) if article_id_match else None
            canonical = f"https://sp.nogizaka46.com/p/news/{article_id}" if article_id else link
            existing.append({
                "date": None,
                "category": "レギュラー",
                "title": list_title,
                "detail": "公式の次回予告。放送日が確認できたら更新します。",
                "url": canonical,
                "source_url": canonical,
                "status": "needs_review",
                "detected_at": now,
            })
            known_urls.add(canonical)
            added_previews += 1
            print(f"Preview candidate found from index: {list_title} | {canonical}")
            continue
        article_id_match = re.search(r"/(?:p/news/|s/n46/news/detail/)(\d+)", urlsplit(link).path)
        article_id = article_id_match.group(1) if article_id_match else None
        detail_page = ""
        fetched_url = link
        # Legacy /p/news/ links in the archive can return 404 on www. Try
        # the canonical official detail URL and mobile URL before failing.
        candidates = [link]
        if article_id:
            candidates.extend([
                f"{BASE}/s/n46/news/detail/{article_id}",
                f"https://sp.nogizaka46.com/p/news/{article_id}",
            ])
        last_error = None
        for candidate_url in dict.fromkeys(candidates):
            try:
                detail_page = fetch(candidate_url)
                fetched_url = stable_url(candidate_url)
                break
            except Exception as exc:
                last_error = exc
        if not detail_page:
            print(f"News detail fetch failed: {link}: {last_error}")
            failed_pages += 1
            continue

        # Official templates can put og:title attributes in either order.
        meta_tags = re.findall(r"<meta\\b[^>]*>", detail_page, re.I | re.S)
        meta_title = None
        for tag in meta_tags:
            if not re.search(r"""\\bproperty=["']og:title["']""", tag, re.I):
                continue
            content_match = re.search(r"""\\bcontent=["']([^"']+)["']""", tag, re.I | re.S)
            if content_match:
                meta_title = content_match.group(1)
                break
        if not meta_title:
            title_match = re.search(r"<title\\b[^>]*>(.*?)</title>", detail_page, re.I | re.S)
            meta_title = title_match.group(1) if title_match else None
        title = ""
        if title_match:
            title = re.sub(r"<[^>]+>", " ", title_match.group(1))
            title = re.sub(r"\s+", " ", title).strip()
            title = title.replace("｜乃木坂46公式サイト", "").strip()

        plain = re.sub(r"<script\b[^>]*>.*?</script>|<style\b[^>]*>.*?</style>", " ", detail_page, flags=re.I | re.S)
        plain = re.sub(r"<[^>]+>", " ", plain)
        plain = re.sub(r"\s+", " ", plain)
        if "乃木坂工事中" not in (title + " " + plain):
            continue
        if "次回予告" not in title and "次回" not in title:
            continue

        publication_date = extract_date(plain)
        existing.append({
            "date": None,
            "category": "レギュラー",
            "title": title or "＜次回予告＞「乃木坂工事中」",
            "detail": "公式の次回予告。日付は記事掲載日であり、放送日としては扱っていません。",
            "url": link,
            "source_url": link,
            "status": "needs_review",
            "detected_at": now,
            "publication_date": publication_date,
        })
        known_urls.add(link)
        added_previews += 1
        print(f"Preview candidate found: {title} | {link}")
        time.sleep(0.1)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(existing, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print("Schedule links found:", schedule_links_found)
    print("Historical schedule records added:", added_schedule)
    print("Preview candidates added:", added_previews)
    print("Failed page requests:", failed_pages)
    print("Total records preserved and stored:", len(existing))


if __name__ == "__main__":
    main()
