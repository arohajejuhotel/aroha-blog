"""네이버 쇼핑 시장 스냅샷 (2026-11-21).

사용: python tools/naver_market.py <결과 폴더> <키워드1> [키워드2 ...]
요청 파일 첫 줄을 "#시장" 으로 쓰면 shop-keywords 작업이 이 스크립트를 돌린다.

1) 쇼핑 검색 API(/search/v1/shop): 키워드별 등록 상품 수, 상위 100개 가격대, 판매처·브랜드 분포
2) 데이터랩 쇼핑인사이트: 키워드 클릭의 연령·성별 비중 (생활/건강, 출산/육아 분야)
판매량(구매 건수)은 API 가 주지 않는다.
"""
import datetime, json, os, re, statistics, sys, urllib.error, urllib.parse, urllib.request
from collections import Counter

HUB = "https://naverapihub.apigw.ntruss.com"
UA = {"User-Agent": "Mozilla/5.0"}
CATS = {"50000008": "생활/건강", "50000005": "출산/육아"}
INSIGHT_PATHS = ["/shopping-insight/v1/category/keyword", "/datalab/v1/shopping/category/keyword"]


def env(n):
    return os.environ.get(n, "").strip()


def headers(json_body=False):
    h = {**UA, "X-NCP-APIGW-API-KEY-ID": env("NAVER_CLIENT_ID"), "X-NCP-APIGW-API-KEY": env("NAVER_CLIENT_SECRET")}
    if json_body:
        h["Content-Type"] = "application/json"
    return h


def call(path, params=None, body=None):
    url = HUB + path + ("?" + urllib.parse.urlencode(params) if params else "")
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, headers=headers(body is not None), data=data)
    return json.loads(urllib.request.urlopen(req, timeout=20).read().decode("utf-8"))


def err(e):
    try:
        return f"{getattr(e, 'code', '')} {e.read().decode('utf-8')[:200]}"
    except Exception:
        return type(e).__name__


def clean(s):
    return re.sub(r"<[^>]+>", "", s or "")


def shop(kw):
    try:
        d = call("/search/v1/shop", {"query": kw, "display": 100, "sort": "sim"})
    except Exception as e:
        return f"  [실패] {err(e)}"
    items = d.get("items", [])
    prices = [int(i["lprice"]) for i in items if str(i.get("lprice", "")).isdigit() and int(i["lprice"]) > 0]
    malls = Counter(i.get("mallName", "") for i in items)
    brands = Counter((i.get("brand") or i.get("maker") or "").strip() for i in items)
    brands.pop("", None)
    cats = Counter(" > ".join(x for x in (i.get("category1"), i.get("category2"), i.get("category3")) if x) for i in items)
    out = [f"  등록 상품 수(total): {d.get('total', 0):,}"]
    if prices:
        q = statistics.quantiles(prices, n=4) if len(prices) >= 4 else [min(prices), statistics.median(prices), max(prices)]
        out.append(f"  상위 {len(prices)}개 최저가: 최소 {min(prices):,} · 25% {int(q[0]):,} · 중앙 {int(statistics.median(prices)):,} · 75% {int(q[-1]):,} · 최대 {max(prices):,}")
    out.append("  판매처 상위: " + ", ".join(f"{m}({n})" for m, n in malls.most_common(8)))
    out.append("  브랜드 상위: " + ", ".join(f"{b}({n})" for b, n in brands.most_common(10)))
    out.append("  분류 상위: " + ", ".join(f"{c}({n})" for c, n in cats.most_common(4)))
    out.append("  상위 10개 상품:")
    for i in items[:10]:
        out.append(f"    - {clean(i.get('title'))[:60]} | {int(i.get('lprice') or 0):,}원 | {i.get('mallName')}")
    return "\n".join(out)


def insight(kw, cat, kind):
    end = datetime.date.today()
    start = end.replace(year=end.year - 1)
    body = {"startDate": str(start), "endDate": str(end), "timeUnit": "month", "category": cat, "keyword": kw}
    last = ""
    for p in INSIGHT_PATHS:
        try:
            d = call(f"{p}/{kind}", body=body)
        except Exception as e:
            last = f"{p}: {err(e)}"
            continue
        agg = Counter()
        for r in d.get("results", []):
            for row in r.get("data", []):
                agg[row.get("group", "")] += float(row.get("ratio", 0))
        tot = sum(agg.values())
        if not tot:
            return f"    {kind}: 데이터 없음"
        return f"    {kind}: " + ", ".join(f"{g} {v / tot * 100:.0f}%" for g, v in sorted(agg.items()))
    return f"    {kind}: [실패] {last}"


def main():
    folder, kws = sys.argv[1], sys.argv[2:]
    os.makedirs(folder, exist_ok=True)
    lines = [f"[네이버 쇼핑 시장 스냅샷] {' / '.join(kws)}", f"{datetime.date.today()} 기준 · 판매량은 API 미제공", ""]
    lines.append("■ 쇼핑 검색 (상품 수·가격·판매처·브랜드)")
    for k in kws:
        lines += [f"[{k}]", shop(k), ""]
    lines.append("■ 데이터랩 쇼핑인사이트 (클릭 비중, 최근 12개월)")
    for k in kws:
        for cat, name in CATS.items():
            lines.append(f"[{k} · {name}]")
            lines.append(insight(k, cat, "age"))
            lines.append(insight(k, cat, "gender"))
    text = "\n".join(lines)
    with open(os.path.join(folder, "00_시장.txt"), "w", encoding="utf-8") as f:
        f.write(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
