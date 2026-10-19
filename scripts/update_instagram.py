#!/usr/bin/env python3
"""Conservatively detect new public posts on Mao Ioki's official Instagram profile."""
import html, json, re
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/"data.json"
STATE=ROOT/"monitor-state"/"instagram-posts.json"
PROFILE="https://www.instagram.com/mao.ioki.official/"
UA="Mozilla/5.0 (compatible; MaoIokiFanSiteInstagramMonitor/1.0)"

class Parser(HTMLParser):
    def __init__(self):
        super().__init__(); self.meta={}; self.links=[]; self.times=[]
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=="meta":
            k=a.get("property") or a.get("name")
            if k and a.get("content"): self.meta[k.lower()]=html.unescape(a["content"])
        elif tag=="a" and a.get("href"): self.links.append(a["href"])
        elif tag=="time" and a.get("datetime"): self.times.append(a["datetime"])

def fetch(url):
    req=Request(url,headers={"User-Agent":UA,"Accept-Language":"ja,en-US;q=0.8"})
    with urlopen(req,timeout=25) as r: return r.read().decode(r.headers.get_content_charset() or "utf-8",errors="replace")
def canonical(url): return url.split("?")[0].rstrip("/")

def main():
    try: page=fetch(PROFILE)
    except (URLError,TimeoutError,OSError) as exc:
        print(f"Instagram unavailable; no data changed: {exc}"); return 0
    p=Parser(); p.feed(page); posts=[]
    for href in p.links:
        m=re.match(r"^/(p|reel|tv)/([A-Za-z0-9_-]+)/?",href)
        if m:
            u=f"https://www.instagram.com/{m.group(1)}/{m.group(2)}/"
            if u not in posts: posts.append(u)
    if not posts:
        print("Instagram page did not expose public post links (possibly login/JS protected); no data changed."); return 0
    if not STATE.exists():
        STATE.parent.mkdir(parents=True,exist_ok=True)
        STATE.write_text(json.dumps([canonical(u) for u in posts],indent=2)+"\n",encoding="utf-8")
        print(f"Instagram baseline saved ({len(posts)} visible posts); existing posts not announced."); return 0
    known=set(json.loads(STATE.read_text(encoding="utf-8")))
    data=json.loads(DATA.read_text(encoding="utf-8"))
    existing={canonical(x.get("url","")) for x in data if isinstance(x,dict)}
    now=datetime.now(timezone.utc); added=0
    for url in posts:
        key=canonical(url)
        if key in known or key in existing: continue
        try:
            detail=Parser(); detail.feed(fetch(url))
        except (URLError,TimeoutError,OSError) as exc:
            print(f"Instagram post unavailable; skipped: {url}: {exc}"); continue
        title=(detail.meta.get("og:title") or "").strip()
        description=(detail.meta.get("og:description") or detail.meta.get("description") or "").strip()
        if not title and not description:
            print(f"Caption not available; skipped instead of guessing: {url}"); continue
        post_date=now.date().isoformat()
        for value in detail.times:
            try: post_date=datetime.fromisoformat(value.replace("Z","+00:00")).date().isoformat(); break
            except ValueError: pass
        data.append({"date":post_date,"category":"Instagram","title":re.sub(r"\s+"," ",title or "五百城茉央 公式Instagram 新着投稿")[:180],"detail":re.sub(r"\s+"," ",description)[:260] or "五百城茉央の公式Instagram新着投稿。","url":url,"source_url":PROFILE,"publisher":"五百城茉央公式Instagram","status":"official_instagram_auto","auto_added":True,"template":"blog","breaking":True,"detected_at":now.isoformat()})
        known.add(key); existing.add(key); added+=1
    STATE.parent.mkdir(parents=True,exist_ok=True)
    STATE.write_text(json.dumps(sorted(known|{canonical(u) for u in posts}),ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    if added:
        data.sort(key=lambda x:(x.get("detected_at",""),x.get("date","")),reverse=True)
        DATA.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"New Instagram posts added as breaking news: {added}")
    return 0
if __name__=="__main__": raise SystemExit(main())
