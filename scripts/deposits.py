"""금융감독원 '금융상품 한눈에' 정기예금·적금 공시 → docs/deposit/data.js
은행(020000)·저축은행(030300)의 정기예금과 적금을 모두 받아, 상품×가입기간 한 줄로 편다.
금리는 공시된 세전 금리 그대로 두고(rate=기본, rate2=우대 최고), 세후는 기본금리 × (1−15.4%)로 따로 계산한다.
실패하면 기존 data.js를 그대로 둔다 (exit 0)."""
import os, sys, json, time, datetime as dt, urllib.request, urllib.parse

K = os.environ.get("FSS_KEY", "").strip()
OUT = "docs/deposit/data.js"
API = "https://finlife.fss.or.kr/finlifeapi/"
GROUPS = {"020000": "은행", "030300": "저축은행"}
KINDS = {"deposit": ("정기예금", "depositProductsSearch.json"), "saving": ("적금", "savingProductsSearch.json")}
TERMS = {"1", "3", "6", "12", "24", "36"}
TAX = 0.154

if not K:
    print("FSS_KEY 없음 — data.js 유지"); sys.exit(0)

def get(path, grp, page):
    q = urllib.parse.urlencode(dict(auth=K, topFinGrpNo=grp, pageNo=page))
    req = urllib.request.Request(API + path + "?" + q, headers={"User-Agent": "Mozilla/5.0"})
    for i in range(6):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)["result"]
        except Exception as e:
            print("retry", path, grp, page, e); time.sleep(3 + 3 * i)
    raise SystemExit(1)

def fetch(path, grp):
    base, opt, page = [], [], 1
    while True:
        j = get(path, grp, page)
        if j.get("err_cd") != "000": print("API 오류", j.get("err_msg")); raise SystemExit(1)
        base += j["baseList"]; opt += j["optionList"]
        if page >= int(j["max_page_no"] or 1): break
        page += 1
    return base, opt

clean = lambda s, n: (s or "").replace("\r", "").replace("\n", " ").strip()[:n]

try:
    today = dt.date.today()
    rows, month = [], None
    for kind, (kname, path) in KINDS.items():
        for grp, gname in GROUPS.items():
            base, opt = fetch(path, grp)
            bm = {(b["fin_co_no"], b["fin_prdt_cd"]): b for b in base}
            month = month or (base[0]["dcls_month"] if base else None)
            seen = set()
            # 같은 상품·기간에 단리·복리가 함께 있으면 단리 하나만 (복리는 표시 금리가 같아 비교에 뜻이 없음)
            for o in sorted(opt, key=lambda o: o["intr_rate_type"] != "S"):
                if o["save_trm"] not in TERMS or not o["intr_rate"]: continue
                key = (o["fin_co_no"], o["fin_prdt_cd"], o["save_trm"], o.get("rsrv_type", ""))
                if key in seen: continue
                seen.add(key)
                b = bm.get((o["fin_co_no"], o["fin_prdt_cd"]))
                if not b: continue
                m = int(o["save_trm"]); rate = float(o["intr_rate"]); rate2 = float(o["intr_rate2"] or rate)
                mat = today + dt.timedelta(days=round(m * 365.25 / 12))
                name = clean(b["fin_prdt_nm"], 80)
                rows.append(dict(
                    id=f"{'D' if kind == 'deposit' else 'S'}{b['fin_co_no']}{b['fin_prdt_cd']}T{m}{o.get('rsrv_type', '')}",
                    kind=kname, bank=clean(b["kor_co_nm"], 40).replace("주식회사 ", ""), grp=gname, name=name,
                    term=m, rate=rate, rate2=rate2, after_tax=round(rate * (1 - TAX), 3),
                    maturity=mat.strftime("%Y%m%d"), rate_type=o["intr_rate_type_nm"],
                    rsrv=o.get("rsrv_type_nm", ""), join=clean(b["join_way"], 60), who=clean(b["join_member"], 80),
                    deny=b.get("join_deny", "1"), limit=b["max_limit"], cond=clean(b["spcl_cnd"], 400),
                    after=clean(b["mtrt_int"], 240), note=clean(b["etc_note"], 300), month=b["dcls_month"],
                    rolling=("회전" in name)))
    if not rows: print("자료 없음 — data.js 유지"); sys.exit(0)
    rows.sort(key=lambda r: (-r["rate"], -r["rate2"], r["term"]))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(f'const DEP_MONTH="{month}";const DEP_DATE="{today.strftime("%Y%m%d")}";const DEP='
                + json.dumps(rows, ensure_ascii=False, separators=(",", ":")) + ";")
    print(len(rows), "건, 공시월", month)
except SystemExit:
    print("예금·적금 자료 실패 — 기존 파일 유지")
except Exception as e:
    print("예금·적금 자료 실패 — 기존 파일 유지:", e)
