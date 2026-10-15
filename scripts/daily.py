"""매일 실행: 최근 5영업일 거래 채권을 받아 docs/data.js 를 다시 만든다.
키는 환경변수 DATA_GO_KR_KEY 로만 받는다."""
import os, sys, json, time, re, csv, datetime as dt, urllib.request, statistics, pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent
K = os.environ["DATA_GO_KR_KEY"].strip()
PRICE = "https://apis.data.go.kr/1160100/GetBondSecuritiesInfoService_V2/getBondPriceInfo_V2"
BASIC = "https://apis.data.go.kr/1160100/GetBondIssuInfoService_V2/getBondBasiInfo_V2"
SCALE = ['AAA','AA+','AA','AA-','A+','A','A-','BBB+','BBB','BBB-','BB+','BB','BB-','B+','B','B-']
def resolve(entry, sub):
    """entry: 등급표 항목(str 또는 dict), sub: 0 선순위 / 1 후순위 / 2 신종. (등급, 등급출처) 반환, 없으면 (None, None)"""
    if entry is None: return None, None
    if isinstance(entry, str): entry = {'senior': entry}
    key = {0: 'senior', 1: 'sub', 2: 'hybrid'}[sub]
    if entry.get(key): return entry[key], '공시'
    s = entry.get('senior')
    if not s: return None, None
    if s == '국채': return '국채', '공시'
    return SCALE[min(SCALE.index(s) + sub, len(SCALE) - 1)], '추정'

def get(url, tries=12):
    for i in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=120) as r:
                t = r.read().decode("utf-8")
                if t.strip(): return json.loads(t)
        except Exception as e:
            err = e
        time.sleep(3 + i)
    raise SystemExit(f"API 실패: {url[:80]} {err}")

def fetch(base, basDt):
    rows, page = [], 1
    while True:
        j = get(f"{base}?serviceKey={K}&resultType=json&numOfRows=1000&pageNo={page}&basDt={basDt}")
        b = j["response"]["body"]; it = b["items"]["item"] if b["items"] else []
        if isinstance(it, dict): it = [it]
        rows += it; tot = int(b["totalCount"])
        if page * 1000 >= tot or not it: break
        page += 1; time.sleep(0.3)
    return rows

# 1) 기준일 = 자료가 있는 가장 최근 날짜(오늘부터 거꾸로 10일)
today = dt.date.today()
days = []
d = today
while len(days) < 5 and (today - d).days < 15:
    if d.weekday() < 5:
        s = d.strftime("%Y%m%d"); p = fetch(PRICE, s)
        if p: days.append((s, p)); print(s, len(p), "건", flush=True)
    d -= dt.timedelta(days=1)
if not days: raise SystemExit("최근 15일 안에 거래 자료가 없습니다.")
D = days[0][0]
# 기본정보는 시세보다 늦게 올라오는 날이 있다. 기준일 것이 비어 있으면 그 전 거래일 것을 쓴다(종목 속성은 날마다 거의 같다).
basic = []
for s, _ in days:
    basic = fetch(BASIC, s); print("기본정보", s, len(basic), "건", flush=True)
    if basic: break
if not basic: raise SystemExit("기본정보가 비어 있습니다 — 기존 자료 유지")

# 2) 합치기 (최근 거래 우선)
P, seen = [], set()
for s, rows in days:
    for p in rows:
        if p["isinCd"] not in seen: seen.add(p["isinCd"]); P.append(p)
pm = {p["isinCd"]: p for p in P}
R = json.load(open(ROOT / "data" / "issuer_ratings.json", encoding="utf-8")); R.pop("_note", None)
base_day = dt.date(int(D[:4]), int(D[4:6]), int(D[6:]))
out = []
for x in basic:
    p = pm.get(x["isinCd"])
    if not p: continue
    nm = x["isinCdNm"]
    if x["bondIssuCurCd"] != "KRW" or x["bondOffrMcdNm"] != "공모": continue
    if re.search(r"전환|신주|분리신|교환", nm): continue
    y = float(p["clprBnfRt"] or 0)
    if y <= 0 or y > 20: continue
    sub, cls = 0, x["scrsItmsKcdNm"]
    if re.search(r"신종|영구|조건부자본|조건상각", nm): sub, cls = 2, "신종·조건부자본증권"
    elif re.search(r"\(후\)|후순위", nm): sub, cls = 1, "후순위채"
    rating, rsrc = resolve(R.get(x["bondIsurNm"]), sub)
    if rating is None: continue
    ent = R.get(x["bondIsurNm"]); base = ent["senior"] if isinstance(ent, dict) else ent
    perp = x["bondExprDt"] == "99991231"
    yrs = None
    if not perp:
        e = dt.date(int(x["bondExprDt"][:4]), int(x["bondExprDt"][4:6]), int(x["bondExprDt"][6:]))
        yrs = round((e - base_day).days / 365.25, 2)
        if yrs < 0.25: continue
    coupon = float(x["bondSrfcInrt"] or 0)
    out.append(dict(isin=x["isinCd"], srtn=p["srtnCd"], name=nm, issuer=x["bondIsurNm"], kind=x["scrsItmsKcdNm"], cls=cls,
        rating=rating, rating_src=rsrc, base_rating=base or "-", ytm=y, coupon=coupon,
        after_tax=round(y - coupon * 0.154, 3), years=yrs, perp=perp, maturity=x["bondExprDt"], price=p["clprPrc"],
        volume=int(p["trqu"] or 0), amt=int(p["trPrc"] or 0), market=p["mrktCtg"], taxed=x["txtnDcdNm"], issue_dt=x["bondIssuDt"],
        int_type=x["bondIntTcdNm"], int_cycle=x["intPayCyclCtt"], guarantee=x["grnDcdNm"], rank=x["bondRnknDcdNm"], trade_dt=p["basDt"]))
out.sort(key=lambda r: -r["after_tax"])
if len(out) < 50: raise SystemExit(f"종목이 {len(out)}개뿐입니다 — 자료 이상으로 보고 기존 자료 유지")
ktb_l = [r["ytm"] for r in out if r["rating"] == "국채" and r["years"] and 2 <= r["years"] <= 4]
ktb = round(statistics.median(ktb_l), 3) if ktb_l else None
missing = sorted({x["bondIsurNm"] for x in basic if x["isinCd"] in pm and x["bondIsurNm"] not in R and x["bondOffrMcdNm"] == "공모"})
(ROOT / "docs" / "data.js").write_text(
    f'const BASDT="{D}";const DAYS={json.dumps([s for s,_ in days])};const KTB={ktb};const DATA=' +
    json.dumps(out, ensure_ascii=False, separators=(",", ":")) + ";", encoding="utf-8")
(ROOT / "data" / "missing_issuers.txt").write_text("\n".join(missing), encoding="utf-8")
with open(ROOT / "docs" / f"bonds_latest.csv", "w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=list(out[0].keys())); w.writeheader(); w.writerows(out)
print(f"기준일 {D} · {len(out)}종목 · 국고채 2~4년 {ktb} · 등급표 없는 발행사 {len(missing)}곳")
