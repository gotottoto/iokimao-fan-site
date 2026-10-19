#!/usr/bin/env python3
"""Generate free, ready-to-copy X drafts for new breaking news; does not call X API."""
import json, re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/"data.json"
STATE=ROOT/"monitor-state"/"x-drafts.json"
OUT=ROOT/"x-drafts.md"

def main():
    data=json.loads(DATA.read_text(encoding="utf-8"))
    known=set(json.loads(STATE.read_text(encoding="utf-8"))) if STATE.exists() else set()
    items=[x for x in data if isinstance(x,dict) and x.get("breaking") is True and x.get("url") and x.get("title")]
    fresh=[x for x in items if x["url"] not in known]
    # Seed existing news on first run to avoid drafting old items as new announcements.
    if not STATE.exists():
        STATE.parent.mkdir(parents=True,exist_ok=True)
        STATE.write_text(json.dumps(sorted({x["url"] for x in items}),ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        OUT.write_text("# X投稿文（自動生成）\n\n初回設定：既存の速報は下書きにせず、次回以降の新着速報から作成します。\n",encoding="utf-8")
        print("Initialized X draft baseline; no old news drafted.")
        return 0
    if not fresh:
        print("No new breaking news for X drafts.")
        return 0
    fresh.sort(key=lambda x:(x.get("detected_at",""),x.get("date","")),reverse=True)
    existing=OUT.read_text(encoding="utf-8") if OUT.exists() else "# X投稿文（自動生成）\n\n"
    chunks=[]
    for item in fresh:
        title=re.sub(r"\s+"," ",item["title"]).strip()
        url=item["url"]
        category=item.get("category","速報")
        draft=f"【{category}】{title}\n{url}\n\n#五百城茉央 #乃木坂46"
        if len(draft)>280:
            draft=f"【{category}】{title[:max(35,245-len(url))]}…\n{url}\n\n#五百城茉央 #乃木坂46"
        chunks.append(f"## {title}\n\n{draft}\n")
        known.add(url)
    OUT.write_text(existing.rstrip()+"\n\n"+"\n".join(chunks)+"\n",encoding="utf-8")
    STATE.parent.mkdir(parents=True,exist_ok=True)
    STATE.write_text(json.dumps(sorted(known),ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"Generated {len(fresh)} X draft(s) in x-drafts.md; no API or paid service used.")
    return 0
if __name__=="__main__": raise SystemExit(main())
