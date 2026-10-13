"""Cloudflare Web Analytics → data/visits.csv (날짜·사이트별 조회수·방문수), data/referers.csv (유입 출처)
토큰이 없거나 실패하면 기존 파일을 그대로 둔다 (exit 0)."""
import os, sys, json, csv, datetime as dt, urllib.request

TOK = os.environ.get("CF_ANALYTICS_TOKEN", "").strip()
ACC = "700aff14424b342ff0d7ccbd1743ca52"
SITES = {  # Web Analytics 사이트 태그(측정 코드의 token) → 이름
    "58e343ace23448bcb4d24c4bde3a2dd9": "clisa.ai",
    "62257318a7f94d94b8fe70feffdce004": "korea.clisa.ai",
    "67d6f341d17b4be0ba6c96a863294b4b": "bond.clisa.ai",
}
V, R = "data/visits.csv", "data/referers.csv"
if not TOK:
    print("CF_ANALYTICS_TOKEN 없음 — 방문 기록 유지"); sys.exit(0)

Q = """query($acc:String!,$since:Date!,$until:Date!,$tags:[String!]){ viewer{ accounts(filter:{accountTag:$acc}){
 daily: rumPageloadEventsAdaptiveGroups(limit:1000,filter:{date_geq:$since,date_leq:$until,siteTag_in:$tags}){ count sum{visits} dimensions{date siteTag} }
 ref: rumPageloadEventsAdaptiveGroups(limit:1000,filter:{date_geq:$since,date_leq:$until,siteTag_in:$tags}){ count dimensions{date siteTag refererHost} }
}}}"""

def gql(v):
    req = urllib.request.Request("https://api.cloudflare.com/client/v4/graphql", data=json.dumps({"query": Q, "variables": v}).encode(),
                                 headers={"Authorization": "Bearer " + TOK, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r: j = json.load(r)
    if j.get("errors"): raise RuntimeError(j["errors"])
    return j["data"]["viewer"]["accounts"][0]

def load(path, key):
    rows = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for r in csv.DictReader(f): rows[tuple(r[k] for k in key)] = r
    return rows

try:
    # 어제까지(UTC 기준 일자; 한국 시간 아침 실행이면 전날 자료가 거의 다 들어옴). 처음이면 30일 소급.
    until = dt.date.today() - dt.timedelta(days=1)
    since = until - dt.timedelta(days=30 if not os.path.exists(V) else 3)
    d = gql(dict(acc=ACC, since=since.isoformat(), until=until.isoformat(), tags=list(SITES)))
    vis = load(V, ("date", "site")); ref = load(R, ("date", "site", "referer"))
    for g in d["daily"]:
        k = (g["dimensions"]["date"], SITES[g["dimensions"]["siteTag"]])
        vis[k] = dict(date=k[0], site=k[1], pageviews=g["count"], visits=g["sum"]["visits"])
    for g in d["ref"]:
        k = (g["dimensions"]["date"], SITES[g["dimensions"]["siteTag"]], g["dimensions"]["refererHost"] or "(직접)")
        ref[k] = dict(date=k[0], site=k[1], referer=k[2], pageviews=g["count"])
    for path, rows, cols in [(V, vis, ["date", "site", "pageviews", "visits"]), (R, ref, ["date", "site", "referer", "pageviews"])]:
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=cols); w.writeheader()
            for k in sorted(rows): w.writerow(rows[k])
    print("방문 기록", len(vis), "행, 유입 출처", len(ref), "행 (", since, "~", until, ")")
except Exception as e:
    print("방문 기록 실패 — 기존 파일 유지:", e)
