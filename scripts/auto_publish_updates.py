#!/usr/bin/env python3
"""Auto-publish new, date-backed items found on official Nogizaka46 pages.

Only official URLs are published. Records are de-duplicated by canonical URL.
Unknown categories are kept out of category archives rather than guessed.
"""
from __future__ import annotations

import html
import json
import re
import time
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = ROOT / "data.json"
BASE = "https://www.nogizaka46.com"
OFFICIAL_HOSTS = {"www.nogizaka46.com", "sp.nogizaka46.com"}
USER_AGENT = "Mozilla/5.0 (compatible; MaoIokiFanSiteAutoPublisher/1.0)"
MAX_NEW_ITEMS = 40


def fetch(url: str) -> str:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=30) as response:
        return response.read().decode(response.headers.get_content_charset() or "utf-8", errors="replace")


def canonical(url: str) -> str:
    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc, p.path.rstrip("/"), "", ""))


def clean_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value or "")
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


class AnchorParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.items = []
        self.href = None
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            attrs = dict(attrs)
            if attrs.get("href"):
                self.href = attrs["href"]
                self.parts = []

    def handle_data(self, data):
        if self.href is not None:
            text = re.sub(r"\s+", " ", data).strip()
            if text:
                self.parts.append(text)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self.href is not None:
            self.items.append((self.href, " ".join(self.parts).strip()))
            self.href = None
            self.parts = []


def links_from(url: str) -> list[tuple[str, str]]:
    parser = AnchorParser()
    parser.feed(fetch(url))
    out = []
    for href, title in parser.items:
        full = urljoin(url, href)
        host = urlsplit(full).netloc.lower()
        if host in OFFICIAL_HOSTS and title:
            out.append((full, clean_text(title)))
    return out


def extract_date(url: str, text: str) -> str | None:
    q = parse_qs(urlsplit(url).query)
    if all(k in q for k in ("wd00", "wd01", "wd02")):
        candidate = "-".join([q["wd00"][0], q["wd01"][0].zfill(2), q["wd02"][0].zfill(2)])
        try:
            return date.fromisoformat(candidate).isoformat()
        except ValueError:
            pass
    path_match = re.search(r"/(?:schedules/)?(20\d{2})[/-](\d{1,2})[/-](\d{1,2})", url)
    if path_match:
        try:
            return date(*map(int, path_match.groups())).isoformat()
        except ValueError:
            pass
    match = re.search(r"(20\d{2})[./年-](\d{1,2})[./月-](\d{1,2})日?", text)
    if match:
        try:
            return date(*map(int, match.groups())).isoformat()
        except ValueError:
            pass
    return None


def category_for(title: str, detail: str, url: str) -> str | None:
    # Classify from event title and URL; include group-wide live appearances and runway events.
    text = (title + " " + url).lower()
    if "/diary/detail/" in url:
        return "ブログ"
    if any(k in text for k in ("雑誌", "グラビア", "巻頭", "掲載誌", "ムック", "写真集", "書籍", "単行本", "brody", "ex大衆", "アップトゥボーイ", "b.l.t.", "blt", "classy.", "週刊少年", "ヤングジャンプ")):
        return "雑誌"
    if any(k in text for k in ("ラジオ", "nhk am", "文化放送", "ニッポン放送", "tokyo fm", "j-wave", "fm yokohama", "mbsラジオ", "らじらー", "レコメン", "乃木坂46の「の」", "乃木坂46の『の』")):
        return "ラジオ"
    if any(k in text for k in ("ランウェイ", "ファッションショー", "girlsaward", "girls award", "東京ガールズコレクション", "tgc", "idol runway collection", "irc 2026", "ファッションイベント", "ライブ/イベント", "ライブ・イベント", "全国ツアー", "真夏の全国ツアー", "ミート＆グリート", "ミート&グリート", "握手会", "リアルミーグリ", "オンラインミーグリ", "イベント", "フェス", "舞台挨拶", "公開収録", "記者会見")):
        return "ライブ/イベント"
    if any(k in text for k in ("web", "配信", "showroom", "youtube", "tiktok", "instagram", "ショートドラマ", "ドラマ", "のぎ動画", "オンライン", "tbsスパークル")):
        return "WEB・配信"
    if any(k in text for k in ("テレビ", "tv", "放送", "出演番組", "music house", "よんチャン", "音道楽", "venue101", "乃木坂工事中", "めざまし", "music station", "テレビ東京", "フジテレビ", "テレビ朝日", "読売テレビ", "abcテレビ", "カンテレ", "nhk総合", "tbs系", "ytv")):
        return "テレビ"
    return None

def template_for(title: str, category: str) -> str:
    text = (title or "").lower()
    if any(k in text for k in ("選抜", "センター", "フォーメーション", "卒業", "加入", "受賞")):
        return "selection"
    if category == "ブログ":
        return "blog"
    if category in ("雑誌", "雑誌・WEB", "書籍"):
        return "magazine"
    if category in ("テレビ", "ラジオ", "WEB・配信"):
        return "media"
    if any(k in text for k in ("ライブ", "イベント", "発売", "リリース", "予約")):
        return "event"
    return "event"


def detail_for(url: str) -> tuple[str, str]:
    page = fetch(url)
    title = ""
    for pattern in (
        r'<meta\b[^>]*(?:property|name)=["\']og:title["\'][^>]*content=["\']([^"\']+)',
        r'<meta\b[^>]*content=["\']([^"\']+)["\'][^>]*(?:property|name)=["\']og:title["\']',
        r"<title\b[^>]*>(.*?)</title>",
    ):
        m = re.search(pattern, page, re.I | re.S)
        if m:
            title = clean_text(m.group(1)).replace("｜乃木坂46公式サイト", "").strip()
            if title:
                break
    plain = clean_text(re.sub(r"<(script|style)\b[^>]*>.*?</\1>", " ", page, flags=re.I | re.S))
    return title, plain[:8000]


def main() -> int:
    if DATA_FILE.exists():
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    else:
        data = []
    if not isinstance(data, list):
        raise SystemExit("data.json must be a JSON array.")

    known = {canonical(x.get("url", "")) for x in data if isinstance(x, dict) and x.get("url")}
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    candidates: dict[str, dict] = {}
    today = datetime.now(timezone.utc).date()
    months = []
    year, month = today.year, today.month
    for _ in range(4):
        months.append(f"{year}{month:02d}")
        month += 1
        if month == 13:
            year, month = year + 1, 1

    # Official media schedule pages are the primary source for dated TV/radio/web/magazine entries.
    for ym in months:
        index_url = f"{BASE}/s/n46/media/list?ima=0000&pri1={ym}"
        try:
            discovered = links_from(index_url)
        except Exception as exc:
            print(f"Schedule index unavailable: {index_url}: {exc}")
            continue
        for url, link_title in discovered:
            key = canonical(url)
            if "/s/n46/media/detail/" not in url or key in known or key in candidates:
                continue
            q = parse_qs(urlsplit(url).query)
            if not all(k in q for k in ("wd00", "wd01", "wd02")):
                continue
            event_date = extract_date(url, link_title)
            if not event_date:
                continue
            try:
                detail_title, detail_text = detail_for(url)
            except Exception as exc:
                print(f"Schedule detail unavailable: {url}: {exc}")
                continue
            title = link_title or detail_title
            if not title or not any(name in (title + " " + detail_text) for name in ("五百城", "乃木坂工事中")):
                # Keep only entries relevant to Mao or the Nogizaka Kojichuu archive.
                continue
            category = category_for(title, detail_text, url)
            if not category:
                print(f"Category unclear; skipped instead of guessing: {title} | {url}")
                continue
            candidates[key] = {
                "date": event_date, "category": category, "title": title,
                "detail": "乃木坂46公式スケジュールから自動取得。リンク先で内容を確認できます。",
                "url": url, "source_url": url, "status": "official_schedule_auto",
                "auto_added": True, "template": template_for(title, category), "breaking": template_for(title, category) == "selection", "detected_at": now,
            }
            time.sleep(0.1)

    # Official blog list: date is visible in the link label and the canonical post URL.
    blog_url = BASE + "/s/n46/diary/MEMBER/list?cd=MEMBER&ct=55396"
    try:
        for url, label in links_from(blog_url):
            key = canonical(url)
            if "/s/n46/diary/detail/" not in url or key in known or key in candidates:
                continue
            event_date = extract_date(url, label)
            if not event_date:
                m = re.search(r"(20\d{2})\.(\d{2})\.(\d{2})", label)
                if m:
                    event_date = "-".join(m.groups())
            title = re.sub(r"\s*20\d{2}\.\d{2}\.\d{2}.*$", "", label).strip()
            if not event_date or not title:
                continue
            candidates[key] = {
                "date": event_date, "category": "ブログ", "title": title,
                "detail": "五百城茉央の乃木坂46公式ブログ。",
                "url": url, "source_url": blog_url, "status": "official_blog_auto",
                "auto_added": True, "template": template_for(title, "ブログ"), "breaking": template_for(title, title) == "selection", "detected_at": now,
            }
    except Exception as exc:
        print(f"Official blog list unavailable: {exc}")

    # Publish only dated, official, relevant records; leave ambiguous items for a later check.
    additions = []
    for key, item in candidates.items():
        if key in known:
            continue
        host = urlsplit(item.get("url", "")).netloc.lower()
        if host not in OFFICIAL_HOSTS or not item.get("date") or not item.get("title"):
            continue
        additions.append(item)
    additions.sort(key=lambda x: (x["date"], x["title"]), reverse=True)
    additions = additions[:MAX_NEW_ITEMS]
    if additions:
        data.extend(additions)
        data.sort(key=lambda x: (x.get("date") or "", x.get("title") or ""), reverse=True)
        DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Auto-published official records: {len(additions)}")
    for item in additions:
        print(f'{item["date"]} | {item["category"]} | {item["title"]} | {item["url"]}')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
