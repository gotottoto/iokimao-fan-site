#!/usr/bin/env python3
"""Daily change monitor for official Mao Ioki information sources.

Safety-first stage: detects source changes and writes a report; it does not
rewrite the existing hand-curated HTML or publish unverified scraped content.
"""
from __future__ import annotations
import hashlib, json, os, re, sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from html.parser import HTMLParser

ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = ROOT / "monitor-state"
STATE_FILE = STATE_DIR / "source-hashes.json"
REPORT = ROOT / "monitor-report.md"
SOURCES = [
    ("乃木坂46公式ブログ一覧", "https://www.nogizaka46.com/s/n46/diary/MEMBER/list?cd=MEMBER&ct=55396"),
    ("乃木坂46公式メディア情報", "https://www.nogizaka46.com/s/n46/media/list"),
    ("乃木坂46公式ニュース", "https://www.nogizaka46.com/s/n46/news/list"),
]

class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts=[]; self.skip=0
    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"): self.skip += 1
    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript") and self.skip: self.skip -= 1
    def handle_data(self, data):
        if not self.skip:
            s = re.sub(r"\s+", " ", data).strip()
            if s: self.parts.append(s)

def fetch(url: str) -> tuple[str, str]:
    req = Request(url, headers={"User-Agent": "MaoIokiFanSiteSourceMonitor/1.0 (GitHub Actions)"})
    with urlopen(req, timeout=25) as resp:
        raw = resp.read()
        charset = resp.headers.get_content_charset() or "utf-8"
    text = raw.decode(charset, errors="replace")
    parser = TextExtractor(); parser.feed(text)
    normalized = "\n".join(parser.parts)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest(), normalized[:1200]

def main() -> int:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        previous = json.loads(STATE_FILE.read_text(encoding="utf-8")) if STATE_FILE.exists() else {}
    except Exception:
        previous = {}
    current = {}; results=[]; failures=0
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    for label, url in SOURCES:
        try:
            digest, preview = fetch(url)
            old = previous.get(url, {}).get("sha256")
            status = "初回記録" if not old else ("変更あり" if old != digest else "変更なし")
            current[url] = {"label": label, "sha256": digest, "checked_at": now, "preview": preview}
            results.append((label, url, status, preview))
        except Exception as e:
            failures += 1
            results.append((label, url, f"取得失敗: {type(e).__name__}: {e}", "取得できなかったため、サイト内容は変更しません。"))
            if url in previous: current[url] = previous[url]
    STATE_FILE.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines=["# 五百城茉央ファンサイト：公式情報チェック", "", f"最終確認: {now}", "", "> この処理は公式ソースの変化を検知するだけです。内容を誤って自動掲載しないよう、HTMLや公開データは自動変更しません。", ""]
    for label,url,status,preview in results:
        lines += [f"## {label}", f"- URL: {url}", f"- 判定: **{status}**", f"- ページ冒頭の抜粋: {preview[:400]}", ""]
    lines += ["## 次の対応", "変更ありのソースは公式ページで新着記事・放送日・媒体・個別URLを確認してからサイトへ反映してください。取得失敗はリンク切れと断定しないでください。", ""]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    return 1 if failures == len(SOURCES) else 0

if __name__ == "__main__":
    sys.exit(main())
