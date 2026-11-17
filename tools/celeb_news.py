"""DRESSCODE M 연예인 패션·뷰티 뉴스 후보 수집 (2026-11-17).

네이버 뉴스 검색(NAVER API HUB, /search/v1/news)에서 오늘 보도된 연예인 패션·뷰티 기사를 모아
같은 소식을 여러 매체가 다룬 순서로 후보를 만든다. 결과는 news/YYYY-MM-DD_연예패션후보.txt.

원칙: 공식 보도만. 열애·결별·논란·사건사고·소송 등 사생활·의혹성 기사는 걸러낸다.
기사 문장은 옮기지 않고, 후보 목록의 제목·출처·링크만 남긴다(글은 새로 쓴다).
키: NAVER_CLIENT_ID / NAVER_CLIENT_SECRET (NCP NAVER API HUB Application 인증 정보)
"""
import datetime, email.utils, html, json, os, re, sys, time, urllib.parse, urllib.request

HUB = "https://naverapihub.apigw.ntruss.com"
KST = datetime.timezone(datetime.timedelta(hours=9))
QUERIES = ["연예인 공항패션", "공항패션 착용", "시상식 드레스", "화보 착용 제품", "착용 화제 아이템", "연예인 패딩",
           "배우 뷰티 화보", "광고 모델 발탁 패션", "스타일링 화제", "완판 착용", "데일리룩 배우", "아이돌 공항 패션", "김지원 듀베티카", "김지원 패딩", "듀베티카 착용"]
# 계속 따라갈 인물·브랜드. 두 단어가 함께 나온 기사는 [착용 추적]에 따로 모은다.
WATCH = [("김지원", "듀베티카")]
KEEP = ["패션", "착용", "룩", "화보", "공항", "시상식", "드레스", "패딩", "코트", "가방", "신발", "스니커", "뷰티", "립",
        "메이크업", "광고", "모델", "브랜드", "품절", "완판", "스타일", "헤어", "니트", "재킷", "목도리", "머플러"]
DROP = ["열애", "결별", "이혼", "불륜", "논란", "사망", "사고", "폭로", "의혹", "고소", "소송", "재판", "구속", "마약", "음주",
        "빚투", "갑질", "학폭", "루머", "파경", "임신", "혼전", "사생활", "별세", "부고", "입건", "경찰", "검찰"]


def env(k):
    return os.environ.get(k, "").strip()


def load_env():
    for p in [os.path.join(os.path.dirname(os.path.abspath(__file__)), "keys.env"),
              r"G:\내 드라이브\08.AROHA\blog-automation\.env"]:
        if os.path.exists(p):
            for line in open(p, encoding="utf-8", errors="ignore"):
                m = re.match(r"\s*([A-Z_]+)\s*=\s*(.*)", line)
                v = m.group(2).strip().strip('"').strip("'") if m else ""
                if m and v and not os.environ.get(m.group(1)):
                    os.environ[m.group(1)] = v


LAST_ERR = [""]


def news(q, display=100):
    url = HUB + "/search/v1/news?" + urllib.parse.urlencode({"query": q, "display": display, "sort": "date", "format": "json"})
    req = urllib.request.Request(url, headers={"X-NCP-APIGW-API-KEY-ID": env("NAVER_CLIENT_ID"),
                                               "X-NCP-APIGW-API-KEY": env("NAVER_CLIENT_SECRET"),
                                               "User-Agent": "Mozilla/5.0"})
    try:
        return json.loads(urllib.request.urlopen(req, timeout=20).read().decode("utf-8")).get("items", [])
    except Exception as e:
        body = ""
        try:
            body = e.read().decode("utf-8")[:200]
        except Exception:
            pass
        LAST_ERR[0] = f"{type(e).__name__} {getattr(e, 'code', '')} {body}"
        print(f"[warn] 뉴스 검색 실패 '{q}': {LAST_ERR[0]}")
        return None


def probe(path, params):
    url = HUB + path + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"X-NCP-APIGW-API-KEY-ID": env("NAVER_CLIENT_ID"),
                                               "X-NCP-APIGW-API-KEY": env("NAVER_CLIENT_SECRET"),
                                               "User-Agent": "Mozilla/5.0"})
    try:
        r = urllib.request.urlopen(req, timeout=20)
        d = json.loads(r.read().decode("utf-8"))
        return f"{r.status} OK total={d.get('total')} items={len(d.get('items', []))}"
    except Exception as e:
        b = ""
        try:
            b = e.read().decode("utf-8")[:160]
        except Exception:
            pass
        return f"{getattr(e, 'code', type(e).__name__)} {b}"


def clean(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", s or ""))).strip()


def tokens(t):
    return set(w for w in re.findall(r"[가-힣A-Za-z0-9]{2,}", t))


def main(hours=30):
    load_env()
    if not (env("NAVER_CLIENT_ID") and env("NAVER_CLIENT_SECRET")):
        print("키 없음"); sys.exit(1)
    now = datetime.datetime.now(KST)
    seen, items, stats = set(), [], []
    for q in QUERIES:
        res = news(q)
        time.sleep(0.15)
        if res is None:
            stats.append(f"{q}: API 실패 · {LAST_ERR[0]}")
            continue
        st = {"n": len(res), "old": 0, "dup": 0, "filtered": 0, "bad_date": 0}
        newest = ""
        for it in res:
            try:
                dt = email.utils.parsedate_to_datetime(it["pubDate"]).astimezone(KST)
            except Exception:
                st["bad_date"] += 1
                continue
            newest = newest or dt.strftime("%m-%d %H:%M")
            if (now - dt).total_seconds() > hours * 3600:
                st["old"] += 1
                continue
            title, desc = clean(it.get("title")), clean(it.get("description"))
            link = it.get("originallink") or it.get("link")
            if link in seen:
                st["dup"] += 1
                continue
            seen.add(link)
            text = title + " " + desc
            if any(w in text for w in DROP) or not any(w in text for w in KEEP):
                st["filtered"] += 1
                continue
            host = urllib.parse.urlparse(link).netloc.replace("www.", "")
            st["ok"] = st.get("ok", 0) + 1
            items.append({"title": title, "desc": desc, "link": link, "naver": it.get("link"), "host": host, "dt": dt, "tok": tokens(title)})
        stats.append(f"{q}: 받음 {st['n']} · 최신 {newest or '-'} · 오래됨 {st['old']} · 중복 {st['dup']} · 걸러짐 {st['filtered']} · 통과 {st.get('ok', 0)}")
    # 같은 소식을 다룬 기사 묶기(제목 단어 겹침)
    clusters = []
    for it in sorted(items, key=lambda x: x["dt"], reverse=True):
        for c in clusters:
            a, b = it["tok"], c[0]["tok"]
            if a and b and len(a & b) / max(1, len(a | b)) >= 0.35:
                c.append(it); break
        else:
            clusters.append([it])
    clusters.sort(key=lambda c: (-len({i["host"] for i in c}), -c[0]["dt"].timestamp()))
    today = now.strftime("%Y-%m-%d")
    lines = [f"[연예인 패션·뷰티 뉴스 후보] {today} {now.strftime('%H:%M')} 기준, 최근 {hours}시간 · 네이버 뉴스 검색",
             f"수집 기사 {len(items)}건 → 소식 {len(clusters)}묶음 (여러 매체가 다룬 순)", ""]
    for who, brand in WATCH:
        hits = [i for i in items if who in (i["title"] + i["desc"]) and brand in (i["title"] + i["desc"])]
        lines += [f"[착용 추적] {who} × {brand}: 최근 {hours}시간 기사 {len(hits)}건"]
        for i in sorted(hits, key=lambda x: x["dt"], reverse=True)[:6]:
            lines += [f"  - {i['dt'].strftime('%m-%d %H:%M')} {i['host']} · {i['title']}", f"    {i['link']}"]
        lines += [""]
    for n, c in enumerate(clusters[:15], 1):
        hosts = sorted({i["host"] for i in c})
        lead = c[0]
        lines += [f"{n}. {lead['title']}", f"   매체 {len(hosts)}곳({', '.join(hosts[:5])}) · {lead['dt'].strftime('%m-%d %H:%M')}",
                  f"   요약 단서: {lead['desc'][:140]}", f"   링크: {lead['link']}", ""]
    diag = ["[API 진단] 같은 키로 호출한 결과",
            "  블로그 /search/v1/blog : " + probe("/search/v1/blog", {"query": "패딩", "display": 3}),
            "  뉴스 /search/v1/news (기본) : " + probe("/search/v1/news", {"query": "패딩", "display": 3}),
            "  뉴스 sort=date : " + probe("/search/v1/news", {"query": "패딩", "display": 3, "sort": "date", "format": "json"}),
            "  지역 /search/v1/local : " + probe("/search/v1/local", {"query": "카페", "display": 3}),
            "  검색어트렌드 key 점검은 shop_keywords 쪽", ""]
    lines += diag
    lines += ["[수집 점검]"] + ["  " + s for s in stats] + [""]
    lines += ["※ 사생활·의혹·사건사고성 기사는 제외했습니다. 기사 문장은 옮기지 않고 사실만 확인해 새로 씁니다.",
              "※ 본문에는 출처 매체와 기사 링크를 밝히고, 연예인 사진은 쓰지 않습니다."]
    os.makedirs("news", exist_ok=True)
    out = f"news/{today}_연예패션후보.txt"
    open(out, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 30)
