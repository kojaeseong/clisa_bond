"""금융감독원 '금융상품 한눈에' 정기예금 공시 → docs/deposits.js
은행(020000)·저축은행(030300) 정기예금을 받아, 기간(6·12·24·36개월)별로 기본금리 상위만 남긴다.
실패하면 기존 deposits.js를 그대로 둔다 (exit 0)."""
import os, sys, json, time, datetime as dt, urllib.request, urllib.parse

K = os.environ.get("FSS_KEY", "").strip()
OUT = "docs/deposits.js"
if not K:
    print("FSS_KEY 없음 — deposits.js 유지"); sys.exit(0)

def get(grp, page):
    q = urllib.parse.urlencode(dict(auth=K, topFinGrpNo=grp, pageNo=page))
    req = urllib.request.Request("https://finlife.fss.or.kr/finlifeapi/depositProductsSearch.json?" + q,
                                 headers={"User-Agent": "Mozilla/5.0"})
    for i in range(6):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)["result"]
        except Exception as e:
            print("retry", grp, page, e); time.sleep(3 + 3 * i)
    raise SystemExit(1)

def fetch(grp):
    base, opt, page = [], [], 1
    while True:
        j = get(grp, page)
        if j.get("err_cd") != "000": print("API 오류", j.get("err_msg")); raise SystemExit(1)
        base += j["baseList"]; opt += j["optionList"]
        if page >= int(j["max_page_no"]): break
        page += 1
    return base, opt

try:
    today = dt.date.today()
    TERMS = ["6", "12", "24", "36"]
    KEEP = {"020000": ("은행", 6), "030300": ("저축은행", 10)}
    rows, month = [], None
    for grp, (gname, n) in KEEP.items():
        base, opt = fetch(grp)
        bm = {(b["fin_co_no"], b["fin_prdt_cd"]): b for b in base}
        month = month or (base[0]["dcls_month"] if base else None)
        for t in TERMS:
            seen, cand = set(), []
            # 같은 상품에 단리·복리가 함께 있으면 단리 하나만
            for o in sorted([o for o in opt if o["save_trm"] == t and o["intr_rate"]], key=lambda o: (o["intr_rate_type"] != "S")):
                key = (o["fin_co_no"], o["fin_prdt_cd"])
                if key in seen: continue
                seen.add(key); cand.append(o)
            cand.sort(key=lambda o: -float(o["intr_rate"]))
            banks, picked = set(), []
            for o in cand:                                   # 은행마다 가장 높은 상품 하나
                if o["fin_co_no"] in banks: continue
                banks.add(o["fin_co_no"]); picked.append(o)
            for o in picked[:n]:
                b = bm[(o["fin_co_no"], o["fin_prdt_cd"])]
                rate, rate2 = float(o["intr_rate"]), float(o["intr_rate2"] or o["intr_rate"])
                m = int(t); mat = today + dt.timedelta(days=round(m * 365.25 / 12))
                name = b["fin_prdt_nm"].replace("\n", " ").strip()
                rows.append(dict(
                    id=f"D{b['fin_co_no']}{b['fin_prdt_cd']}T{t}", bank=b["kor_co_nm"].replace("주식회사 ", ""), grp=gname,
                    name=name, term=m, rate=rate, rate2=rate2, after_tax=round(rate * (1 - 0.154), 3),
                    years=round(m / 12, 2), maturity=mat.strftime("%Y%m%d"), rate_type=o["intr_rate_type_nm"],
                    join=b["join_way"], cond=(b["spcl_cnd"] or "").replace("\n", " ").strip()[:300],
                    limit=b["max_limit"], after=(b["mtrt_int"] or "").replace("\n", " ").strip()[:200],
                    rolling=("회전" in name), month=b["dcls_month"]))
    rows.sort(key=lambda r: -r["after_tax"])
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(f'const DEP_MONTH="{month}";const DEP_DATE="{today.strftime("%Y%m%d")}";const DEP=' + json.dumps(rows, ensure_ascii=False) + ";")
    print(len(rows), "건, 공시월", month)
except SystemExit:
    print("예금 자료 실패 — 기존 파일 유지")
except Exception as e:
    print("예금 자료 실패 — 기존 파일 유지:", e)
