"""Cloudflare Web Analytics → data/visits.csv (날짜·사이트별 조회수·방문수), data/referers.csv (유입 출처), data/pages.csv (날짜·사이트·페이지 경로별 조회수·방문수, 2026-10-24 추가)
사이트 구분은 방문자가 연 주소(requestHost)로 한다. 실패하면 기존 파일을 그대로 둔다 (exit 0)."""
import os, re, sys, json, csv, datetime as dt, urllib.request, urllib.error

TOK = re.sub(r"\s+", "", os.environ.get("CF_ANALYTICS_TOKEN", ""))   # 붙여 넣을 때 섞인 줄바꿈·공백 제거
ACC = "700aff14424b342ff0d7ccbd1743ca52"
V, R, P = "data/visits.csv", "data/referers.csv", "data/pages.csv"
if not TOK:
    print("CF_ANALYTICS_TOKEN 없음 — 방문 기록 유지"); sys.exit(0)

def site_of(host):
    h = (host or "").lower()
    if h in ("clisa.ai", "www.clisa.ai", "geo.clisa.ai"): return "clisa.ai"
    if h.endswith(".clisa.ai"): return h
    return None   # 미리보기·기타 주소는 제외

Q = """query($acc:string!,$day:Date!){ viewer{ accounts(filter:{accountTag:$acc}){
 daily: rumPageloadEventsAdaptiveGroups(limit:500,filter:{date:$day}){ count sum{visits} dimensions{date requestHost} }
 ref: rumPageloadEventsAdaptiveGroups(limit:2000,filter:{date:$day}){ count dimensions{date requestHost refererHost} }
 pages: rumPageloadEventsAdaptiveGroups(limit:5000,filter:{date:$day}){ count sum{visits} dimensions{date requestHost requestPath} }
}}}"""

def gql(v):
    req = urllib.request.Request("https://api.cloudflare.com/client/v4/graphql", data=json.dumps({"query": Q, "variables": v}).encode(),
                                 headers={"Authorization": "Bearer " + TOK, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r: j = json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read().decode('utf-8','replace')[:600]}")
    if j.get("errors"): raise RuntimeError(j["errors"])
    return j["data"]["viewer"]["accounts"][0]

def load(path, key):
    rows = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for r in csv.DictReader(f): rows[tuple(r[k] for k in key)] = r
    return rows

try:
    until = dt.date.today() - dt.timedelta(days=1)
    vis = load(V, ("date", "site")); ref = load(R, ("date", "site", "referer")); pag = load(P, ("date", "site", "path"))
    since = until - dt.timedelta(days=3 if (vis and pag) else 30)      # 처음이면 30일 소급(페이지 기록이 처음 생길 때도)
    # 하루씩 따로 묻는다 — 기간을 길게 잡으면 Cloudflare가 표본 추정치(10 단위)로 답해 작은 사이트가 사라진다
    agg, ragg, pagg, n = {}, {}, {}, 0
    day = since
    while day <= until:
        d = gql(dict(acc=ACC, day=day.isoformat())); n += len(d["daily"])
        for g in d["daily"]:
            site = site_of(g["dimensions"]["requestHost"])
            if not site: continue
            k = (g["dimensions"]["date"], site); a = agg.setdefault(k, [0, 0]); a[0] += g["count"]; a[1] += g["sum"]["visits"]
        for g in d["ref"]:
            site = site_of(g["dimensions"]["requestHost"])
            if not site: continue
            k = (g["dimensions"]["date"], site, g["dimensions"]["refererHost"] or "(직접)"); ragg[k] = ragg.get(k, 0) + g["count"]
        for g in d["pages"]:
            site = site_of(g["dimensions"]["requestHost"])
            if not site: continue
            path = (g["dimensions"]["requestPath"] or "/").split("?")[0]
            k = (g["dimensions"]["date"], site, path); a = pagg.setdefault(k, [0, 0]); a[0] += g["count"]; a[1] += g["sum"]["visits"]
        day += dt.timedelta(days=1)
    for k, (p, v) in agg.items(): vis[k] = dict(date=k[0], site=k[1], pageviews=p, visits=v)
    for k, p in ragg.items(): ref[k] = dict(date=k[0], site=k[1], referer=k[2], pageviews=p)
    for k, (p, v) in pagg.items(): pag[k] = dict(date=k[0], site=k[1], path=k[2], pageviews=p, visits=v)
    for path, rows, cols in [(V, vis, ["date", "site", "pageviews", "visits"]), (R, ref, ["date", "site", "referer", "pageviews"]), (P, pag, ["date", "site", "path", "pageviews", "visits"])]:
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=cols); w.writeheader()
            for k in sorted(rows): w.writerow(rows[k])
    print("방문 기록", len(vis), "행, 유입 출처", len(ref), "행, 페이지", len(pag), "행 (", since, "~", until, ")", "원자료", n, "묶음")
except Exception as e:
    print("방문 기록 실패 — 기존 파일 유지:", e)
