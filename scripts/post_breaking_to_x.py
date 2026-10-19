#!/usr/bin/env python3
"""Post newly added breaking news to the authorized X account."""
import json, os, re
from pathlib import Path
from requests_oauthlib import OAuth1Session
ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/"data.json"; STATE=ROOT/"monitor-state"/"x-posted.json"
API_URL="https://api.x.com/2/tweets"
def main():
    names=("X_API_KEY","X_API_SECRET","X_ACCESS_TOKEN","X_ACCESS_TOKEN_SECRET")
    creds={n:os.environ.get(n,"").strip() for n in names}
    if not all(creds.values()):
        print("X auto-post skipped: configure X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET as GitHub Actions secrets."); return 0
    data=json.loads(DATA.read_text(encoding="utf-8"))
    if not STATE.exists():
        baseline=[x.get("url") for x in data if isinstance(x,dict) and x.get("breaking") is True and x.get("url")]
        STATE.parent.mkdir(parents=True,exist_ok=True)
        STATE.write_text(json.dumps(sorted(set(baseline)),ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        print(f"X baseline initialized ({len(baseline)} current breaking items); no old item posted."); return 0
    posted=set(json.loads(STATE.read_text(encoding="utf-8")))
    pending=[x for x in data if isinstance(x,dict) and x.get("breaking") is True and x.get("url") and x.get("url") not in posted]
    if not pending: print("No new breaking news to post to X."); return 0
    item=sorted(pending,key=lambda x:(x.get("detected_at",""),x.get("date","")),reverse=True)[0]
    title=re.sub(r"\s+"," ",item.get("title","")).strip(); url=item["url"]
    text=f'【{item.get("category","速報")}】{title}\n{url}\n\n#五百城茉央 #乃木坂46'
    if len(text)>280: text=f'【{item.get("category","速報")}】{title[:max(40,245-len(url))]}…\n{url}\n\n#五百城茉央 #乃木坂46'
    session=OAuth1Session(creds["X_API_KEY"],client_secret=creds["X_API_SECRET"],resource_owner_key=creds["X_ACCESS_TOKEN"],resource_owner_secret=creds["X_ACCESS_TOKEN_SECRET"])
    response=session.post(API_URL,json={"text":text},timeout=30)
    if response.status_code not in (200,201): raise SystemExit(f"X API post failed ({response.status_code}): {response.text[:800]}")
    post_id=response.json().get("data",{}).get("id")
    posted.add(url); STATE.parent.mkdir(parents=True,exist_ok=True)
    STATE.write_text(json.dumps(sorted(posted),ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"Posted to X: https://x.com/i/web/status/{post_id}")
    return 0
if __name__=="__main__": raise SystemExit(main())
