"""DRESSCODE M · 골라줌 쇼핑 키워드 산정 (2026-11-16).

사용:
  python "G:/내 드라이브/네이버용 블로그 글/패션/_키워드도구/shop_keywords.py" "<제품 폴더>" "한경희 스팀청소기" "스팀청소기" ["핸디스팀청소기" ...]
  - 첫 씨앗 = 브랜드+제품, 나머지 = 카테고리 검색어. 결과는 <제품 폴더>\00_키워드.txt

하는 일
1) 네이버 자동완성(씨앗, 씨앗+공백, 씨앗+ㄱ..ㅎ 일부)으로 지금 많이 치는 검색어를 모은다.  [키 없이 됨]
2) 네이버 검색광고 API 로 월간 검색량(PC+모바일)·경쟁도·연관 키워드를 붙인다.         [NAVER_AD_* 키]
3) 네이버 데이터랩 검색어 트렌드로 상위 키워드의 최근 12개월 추이(오르는 중/내리는 중)를 본다. [NAVER_CLIENT_* 키, 선택]
4) DRESSCODE M(후기·선물) / 골라줌(비교·추천) / 본문 소제목(문제 해결) / 제외(대여·중고)로 나눈다.

키는 이 폴더의 keys.env 에서 읽는다(비어 있으면 08.AROHA\\blog-automation\\.env, 값은 출력하지 않는다):
  NAVER_AD_CUSTOMER_ID, NAVER_AD_API_KEY, NAVER_AD_SECRET   (searchad.naver.com → 도구 → API 사용 관리)
  NAVER_CLIENT_ID, NAVER_CLIENT_SECRET                      (developers.naver.com 앱, 데이터랩 검색어트렌드)
"""
import base64, datetime, hashlib, hmac, json, os, re, sys, time, urllib.parse, urllib.request

# 키 파일: 이 스크립트 옆 keys.env(G 드라이브 — 집·회사 PC 공통)를 먼저 보고, 비어 있으면 아로하 자동화 .env 를 본다.
ENV_FILES = [os.path.join(os.path.dirname(os.path.abspath(__file__)), "keys.env"),
             r"G:\내 드라이브\08.AROHA\blog-automation\.env"]
UA = {"User-Agent": "Mozilla/5.0"}

EXCLUDE = ["대여", "렌탈", "렌트", "중고", "당근", "부품", "수리점", "고장", "리콜", "가격비교사이트",
           "도매", "업소용", "판매점", "매장위치", "주가", "채용", "주식"]
GOLLA = ["추천", "비교", "vs", "순위", "차이", "가성비", "브랜드", "best", "베스트", "고르는", "종류", "1위", "어떤"]
DCM = ["후기", "내돈내산", "선물", "엄마", "부모님", "사용법", "사용후기", "리뷰", "단점", "장점", "솔직", "효과", "쓰는법"]
GOLLA += ["가격", "할인", "최저가"]
# '청소'는 '청소기'에도 걸려서 넣지 않는다
FIX = ["as", "a/s", "조립", "방법", "안됨", "안나옴", "물이", "세척", "교체", "고압", "무선", "유선", "패드", "필터", "물통", "뚜껑",
       "매트", "버튼", "충전", "배터리", "소음", "냄새", "사이즈", "치수", "세탁"]


def load_env():
    for path in ENV_FILES:
        if not os.path.exists(path):
            continue
        for line in open(path, encoding="utf-8", errors="ignore"):
            m = re.match(r"\s*([A-Z_]+)\s*=\s*(.*)", line)
            val = m.group(2).strip().strip('"').strip("'") if m else ""
            if m and val and not os.environ.get(m.group(1)):
                os.environ[m.group(1)] = val


def env(name):
    return os.environ.get(name, "").strip()


def get_json(url, headers=None, data=None):
    req = urllib.request.Request(url, headers={**UA, **(headers or {})}, data=data)
    return json.loads(urllib.request.urlopen(req, timeout=20).read().decode("utf-8"))


def suggest(q):
    url = "https://ac.search.naver.com/nx/ac?" + urllib.parse.urlencode({
        "q": q, "con": "1", "frm": "nv", "ans": "2", "r_format": "json", "r_enc": "UTF-8",
        "r_unicode": "0", "t_koreng": "1", "run": "2", "rev": "4", "q_enc": "UTF-8", "st": "100"})
    try:
        return [i[0] for i in get_json(url).get("items", [[]])[0]]
    except Exception:
        return []


def collect(seeds):
    score = {}
    for s in seeds:
        for q in [s, s + " "] + [s + " " + c for c in "가나다라마바사아자차카타파하"]:
            for rank, k in enumerate(suggest(q)[:10]):
                k = re.sub(r"\s+", " ", k).strip()
                if len(k) >= 2:
                    score[k] = score.get(k, 0) + (10 - rank) / 10
            time.sleep(0.05)
    return score


def _n(v):
    return int(v) if str(v).isdigit() else 5  # "< 10" 은 5 로


def ad_volumes(keywords):
    """{키워드(공백제거): {vol, comp, rel}} + 연관 키워드. 키 없으면 {}."""
    cid, key, sec = env("NAVER_AD_CUSTOMER_ID"), env("NAVER_AD_API_KEY"), env("NAVER_AD_SECRET")
    if not (cid and key and sec):
        return None
    out = {}
    hints = list(dict.fromkeys(k.replace(" ", "") for k in keywords))
    for i in range(0, len(hints), 5):
        batch = hints[i:i + 5]
        ts = str(int(time.time() * 1000))
        sig = base64.b64encode(hmac.new(sec.encode(), f"{ts}.GET./keywordstool".encode(), hashlib.sha256).digest()).decode()
        url = "https://api.searchad.naver.com/keywordstool?" + urllib.parse.urlencode({"hintKeywords": ",".join(batch), "showDetail": "1"})
        try:
            data = get_json(url, {"X-Timestamp": ts, "X-API-KEY": key, "X-Customer": cid, "X-Signature": sig})
        except Exception as e:
            print(f"[warn] 검색광고 API 실패 ({type(e).__name__} {getattr(e, 'code', '')})")
            break
        for row in data.get("keywordList", []):
            k = row["relKeyword"]
            out[k] = {"vol": _n(row.get("monthlyPcQcCnt")) + _n(row.get("monthlyMobileQcCnt")),
                      "comp": row.get("compIdx", ""), "hint": k in batch}
        time.sleep(0.25)
    return out


def trend(keywords):
    """데이터랩 검색어 트렌드: 최근 3개월 평균 / 이전 9개월 평균. 키 없으면 {}."""
    cid, sec = env("NAVER_CLIENT_ID"), env("NAVER_CLIENT_SECRET")
    if not (cid and sec) or not keywords:
        return {}
    end = datetime.date.today()
    start = end.replace(year=end.year - 1)
    res = {}
    for i in range(0, len(keywords), 5):
        groups = [{"groupName": k, "keywords": [k]} for k in keywords[i:i + 5]]
        body = json.dumps({"startDate": str(start), "endDate": str(end), "timeUnit": "month",
                           "keywordGroups": groups}).encode()
        try:
            data = get_json("https://openapi.naver.com/v1/datalab/search",
                            {"X-Naver-Client-Id": cid, "X-Naver-Client-Secret": sec,
                             "Content-Type": "application/json"}, body)
        except Exception as e:
            print(f"[warn] 데이터랩 실패 ({type(e).__name__} {getattr(e, 'code', '')})")
            break
        for r in data.get("results", []):
            v = [d["ratio"] for d in r.get("data", [])]
            if len(v) >= 6:
                recent, before = sum(v[-3:]) / 3, sum(v[:-3]) / max(1, len(v) - 3)
                res[r["title"]] = round(recent / before, 2) if before else None
    return res


def bucket(k):
    lk = k.lower().replace(" ", "")
    # '40대여성'처럼 나이+대+여성 이 '대여'로 걸리지 않게 나이 표기를 먼저 지운다
    lk_ex = re.sub(r"\d+대", "", lk)
    if any(x in lk_ex for x in EXCLUDE):
        return "제외"
    if any(x in lk for x in GOLLA):
        return "골라줌"
    if any(x in lk for x in DCM):
        return "DRESSCODE M"
    if any(x in lk for x in FIX):
        return "본문"
    return "공통"


def main():
    if len(sys.argv) < 3:
        print(__doc__); sys.exit(1)
    folder, seeds = sys.argv[1], sys.argv[2:]
    load_env()
    tokens = set(t for s in seeds for t in s.replace(" ", " ").split())
    sc = collect(seeds)
    cands = sorted(sc, key=lambda k: -sc[k])[:150]
    vols = ad_volumes(cands + seeds)
    rows = {}
    for k in cands:
        rows[k.replace(" ", "")] = {"kw": k, "auto": round(sc[k], 1), "vol": None, "comp": ""}
    if vols is not None:
        for k, v in vols.items():
            # 연관 키워드는 씨앗 단어가 들어간 것만
            if k in rows or any(t in k for t in tokens):
                r = rows.setdefault(k, {"kw": k, "auto": 0, "vol": None, "comp": ""})
                r["vol"], r["comp"] = v["vol"], v["comp"]
    lst = list(rows.values())
    has_vol = vols is not None and any(r["vol"] for r in lst)
    lst.sort(key=lambda r: (-(r["vol"] or 0), -r["auto"]) if has_vol else (-r["auto"],))
    top_for_trend = [r["kw"] for r in lst if bucket(r["kw"]) != "제외"][:15]
    tr = trend(top_for_trend)
    for r in lst:
        r["b"] = bucket(r["kw"])
        r["tr"] = tr.get(r["kw"])

    def fmt(r):
        s = f"{r['kw']}"
        if r["vol"] is not None:
            s += f"  월 {r['vol']:,}회"
            if r["comp"]:
                s += f" · 경쟁 {r['comp']}"
        else:
            s += f"  (자동완성 점수 {r['auto']})"
        if r["tr"]:
            s += "  ↑ 오르는 중" if r["tr"] >= 1.2 else ("  ↓ 내리는 중" if r["tr"] <= 0.8 else "  → 보합")
        return s

    today = datetime.date.today().isoformat()
    src = "자동완성 + 검색광고 월간 검색량" if has_vol else "자동완성만 (검색량 키 없음 — 순위는 자동완성 점수)"
    if tr:
        src += " + 데이터랩 12개월 추이"
    lines = [f"[쇼핑 키워드] {' / '.join(seeds)}", f"{today} 기준 · {src}", ""]
    use = [r for r in lst if r["b"] != "제외"]
    brand = [r for r in use if seeds[0].replace(" ", "") in r["kw"].replace(" ", "")]
    lines += ["■ 제목 맨 앞 후보 (검색량 많은 순)"]
    for r in (brand[:3] + [r for r in use if r not in brand][:3]):
        lines.append("  - " + fmt(r))
    for name, label in [("DRESSCODE M", "■ DRESSCODE M (후기·선물·사용법)"),
                        ("골라줌", "■ 골라줌 (추천·비교·순위)"),
                        ("본문", "■ 본문 소제목·Q&A (쓰는 사람이 막히는 곳)"),
                        ("공통", "■ 공통 (제품·카테고리)")]:
        part = [r for r in use if r["b"] == name][:12]
        if part:
            lines += ["", label] + ["  - " + fmt(r) for r in part]
    ex = [r["kw"] for r in lst if r["b"] == "제외"][:10]
    if ex:
        lines += ["", "■ 쓰지 않음 (구매 의도 아님): " + ", ".join(ex)]
    tags = []
    for r in use:
        t = "#" + r["kw"].replace(" ", "")
        if t not in tags and len(t) <= 16:
            tags.append(t)
        if len(tags) >= 12:
            break
    lines += ["", "■ 해시태그 후보", "  " + " ".join(tags), "",
              "※ 검색량은 네이버 검색광고 기준 최근 30일 PC+모바일. '< 10'은 5로 계산."]
    text = "\n".join(lines)
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "00_키워드.txt"), "w", encoding="utf-8") as f:
        f.write(text + "\n")
    print(text)


# ---------------------------------------------------------------- 주제 추천 모드
# DRESSCODE M(패션·뷰티·엄마랑 살림) / 골라줌(생활가전·골프·선물 비교) 이 다룰 수 있는 쇼핑 씨앗.
# 계절 씨앗은 달마다 바꿔 끼운다. 요청 파일 첫 줄이 "#추천" 이면 이 모드.
DISCOVER_SEEDS = {
    "겨울 패션": ["롱패딩", "숏패딩", "경량패딩", "니트", "기모레깅스", "어그부츠", "목도리", "히트텍", "코트", "골프스타킹"],
    "뷰티": ["수분크림", "핸드크림", "립밤", "바디로션", "앰플", "선크림", "클렌징폼", "헤어오일"],
    "생활가전": ["가습기", "전기요", "온수매트", "전기히터", "스팀청소기", "무선청소기", "음식물처리기", "에어프라이어", "제습기"],
    "살림·먹거리": ["김장김치", "밀폐용기", "프라이팬", "보온병", "텀블러", "귤"],
    "운동·골프": ["런닝화", "운동화", "러닝복", "필라테스양말", "요가매트", "골프장갑", "골프공", "홈트", "치닝디핑"],
    "선물": ["크리스마스선물", "남자친구선물", "여자친구선물", "부모님선물", "집들이선물", "연말선물"],
}


def discover(folder, extra):
    groups = dict(DISCOVER_SEEDS)
    if extra:
        groups = {"요청 씨앗": extra, **groups}
    seeds = [s for v in groups.values() for s in v]
    vols = ad_volumes(seeds)
    has_vol = bool(vols)
    sc = {} if has_vol else collect(seeds)
    today = datetime.date.today().isoformat()
    lines = [f"[주제 추천용 쇼핑 검색어] {today} 기준 · "
             + ("검색광고 월간 검색량(최근 30일)" if has_vol else "자동완성만 (검색량 키 없음)"), ""]
    pool = []
    for gname, gseeds in groups.items():
        lines.append(f"■ {gname}")
        for s in gseeds:
            key = s.replace(" ", "")
            if has_vol:
                rel = [(k, v) for k, v in vols.items() if key in k and k != key and bucket(k) != "제외"]
                rel.sort(key=lambda kv: -kv[1]["vol"])
                head = vols.get(key, {}).get("vol")
                tail = ", ".join(f"{k} {v['vol']:,}" for k, v in rel[:6])
                lines.append(f"  - {s}: 월 {head:,}회" if head else f"  - {s}: (검색량 없음)")
                if tail:
                    lines.append(f"      연관: {tail}")
                pool += [(gname, k, v["vol"]) for k, v in rel[:15]]
                if head:
                    pool.append((gname, key, head))
            else:
                rel = [k for k in sc if s in k.replace(" ", "") or key in k.replace(" ", "")]
                rel.sort(key=lambda k: -sc[k])
                lines.append(f"  - {s}: " + ", ".join(rel[:6]))
        lines.append("")
    if has_vol:
        pool = sorted({(g, k, v) for g, k, v in pool}, key=lambda x: -x[2])
        lines.append("■ 전체 검색량 상위 40 (구매 의도 키워드)")
        for g, k, v in pool[:40]:
            lines.append(f"  - {k}  월 {v:,}회  [{g}] {bucket(k)}")
        tr = trend([k for _, k, _ in pool[:20]])
        if tr:
            up = [k for k, r in tr.items() if r and r >= 1.2]
            if up:
                lines += ["", "■ 최근 3개월 오르는 중: " + ", ".join(up)]
    lines += ["", "※ 브랜드명이 붙은 연관어(예: 한경희 스팀청소기)가 크면 그 제품을 글 주제로 고른다."]
    text = "\n".join(lines)
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "00_주제추천.txt"), "w", encoding="utf-8") as f:
        f.write(text + "\n")
    print(text)


# ---------------------------------------------------------------- 틈새 모드
# 검색량은 최고치가 아니어도 글이 적어서 상위를 잡기 쉬운 키워드를 찾는다.
# 요청 파일 첫 줄이 "#틈새" 이면 이 모드. 둘째 줄부터 넓은 씨앗(예: 원룸, 1인용, 접이식).
# 지표: 월 검색량(검색광고) / 블로그 문서 수(검색 API total) / 최근 글 100개가 쌓인 기간(활발도).
def blog_stats(kw):
    cid, sec = env("NAVER_CLIENT_ID"), env("NAVER_CLIENT_SECRET")
    if not (cid and sec):
        return None
    url = "https://openapi.naver.com/v1/search/blog.json?" + urllib.parse.urlencode(
        {"query": kw, "display": 100, "sort": "date"})
    try:
        d = get_json(url, {"X-Naver-Client-Id": cid, "X-Naver-Client-Secret": sec})
    except Exception as e:
        return {"err": f"{type(e).__name__} {getattr(e, 'code', '')}"}
    items = d.get("items", [])
    span = None
    if items:
        try:
            last = datetime.datetime.strptime(items[-1]["postdate"], "%Y%m%d").date()
            span = max(1, (datetime.date.today() - last).days)
        except Exception:
            span = None
    return {"total": d.get("total", 0), "span": span, "n": len(items)}


def niche(folder, seeds, vmin=700, vmax=30000, topn=70):
    load_env()
    seeds = seeds or ["1인용", "원룸", "자취", "미니", "소형", "접이식", "다용도", "침대", "책상", "욕실", "주방", "빨래"]
    vols = ad_volumes(seeds)
    today = datetime.date.today().isoformat()
    lines = [f"[틈새 키워드] {' / '.join(seeds)}", f"{today} 기준 · 검색량 {vmin:,}~{vmax:,} 구간", ""]
    if not vols:
        lines.append("검색광고 키가 없어 검색량을 가져오지 못했습니다.")
        text = "\n".join(lines)
    else:
        pool = [(k, v["vol"], v["comp"]) for k, v in vols.items()
                if vmin <= v["vol"] <= vmax and bucket(k) != "제외"]
        pool.sort(key=lambda x: -x[1])
        pool = pool[:topn]
        rows, err = [], None
        for k, vol, comp in pool:
            st = blog_stats(k)
            time.sleep(0.12)
            if st is None:
                err = "검색 API 키 없음"; break
            if "err" in st:
                err = f"검색 API 실패 ({st['err']}) — developers.naver.com 앱에 '검색' API 권한 추가 필요"; break
            rows.append({"kw": k, "vol": vol, "comp": comp, "total": st["total"], "span": st["span"]})
        if err:
            lines.append("※ " + err)
            lines += ["", "■ 검색량 순 (문서 수 없음)"] + [f"  - {k}  월 {vol:,}회" for k, vol, c in pool[:40]]
        else:
            for r in rows:
                r["ratio"] = r["total"] / max(1, r["vol"])
            # 포화도(문서 수 / 월 검색량)가 낮고, 최근 글 100개가 오래 걸려 쌓인(=새 글이 적은) 키워드가 위
            rows.sort(key=lambda r: (r["ratio"], -(r["span"] or 0)))
            lines.append("■ 틈새 후보 (포화도 낮은 순) — 포화도 = 블로그 문서 수 ÷ 월 검색량")
            for r in rows[:30]:
                sp = f" · 최근 100글 {r['span']}일에 걸쳐 작성" if r["span"] else ""
                lines.append(f"  - {r['kw']}  월 {r['vol']:,}회 · 문서 {r['total']:,}건 · 포화도 {r['ratio']:.1f}{sp}")
            lines += ["", "■ 검색량 큰 순 (참고)"]
            for r in sorted(rows, key=lambda r: -r["vol"])[:15]:
                lines.append(f"  - {r['kw']}  월 {r['vol']:,}회 · 문서 {r['total']:,}건 · 포화도 {r['ratio']:.1f}")
        lines += ["", "※ 포화도가 낮을수록 글이 적어 상위를 잡기 쉽고, '최근 100글 N일'이 클수록 새 글이 드물다는 뜻입니다.",
                  "※ 검색량은 검색광고 최근 30일 PC+모바일, 문서 수는 네이버 블로그 검색 API 기준입니다. 쇼핑 의도가 없는 키워드가 섞이면 걸러서 고릅니다."]
        text = "\n".join(lines)
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "00_틈새추천.txt"), "w", encoding="utf-8") as f:
        f.write(text + "\n")
    print(text)


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[2] == "--niche":
        niche(sys.argv[1], sys.argv[3:])
    elif len(sys.argv) >= 3 and sys.argv[2] == "--discover":
        load_env()
        discover(sys.argv[1], sys.argv[3:])
    else:
        main()
