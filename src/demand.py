"""한국어 글 주제를 그날 네이버 검색량 기준으로 고른다 (2026-10-16).

1) 제주·성산 여행 씨앗 키워드로 네이버·구글 자동완성을 모은다 (지금 많이 입력되는 검색어).
2) 상위 후보의 네이버 월간 검색량(PC+모바일)을 네이버 검색광고 API 로 조회해 정렬한다.
3) Claude 가 검색량·시기·호텔 연결성을 보고 오늘 쓸 주제 1개를 고르고,
   주제 풀과 같은 형식(id, ko, kw_ko, q, img, place...)으로 만들어 돌려준다.

키가 없거나 실패하면 None 을 돌려주고, 호출 쪽이 기존 주제 풀 순서로 넘어간다.
"""

import base64
import hashlib
import hmac
import json
import os
import re
import time
import urllib.parse
import urllib.request

UA = {"User-Agent": "Mozilla/5.0"}

SEEDS = [
    "제주 여행", "제주도 여행", "제주 가볼만한곳", "제주 맛집", "제주 숙소", "제주 동쪽",
    "제주 서쪽", "제주 10월", "제주 11월", "제주 12월", "제주 가을", "제주 겨울",
    "성산", "성산일출봉", "성산 맛집", "성산 숙소", "우도", "우도 배", "광치기해변",
    "섭지코지", "한라산", "서귀포", "제주시", "협재", "애월", "제주 오름", "제주 올레길",
    "제주 렌터카", "제주 버스", "제주공항", "제주 아이랑", "제주 비오는날", "제주 축제",
    "제주 일출", "제주 감귤", "제주 흑돼지", "제주 카페", "제주 2박3일", "제주 여행코스",
]

BLOCK = [
    "항공권", "비행기표", "특가", "날씨", "실시간", "cctv", "부동산", "아파트", "매매",
    "채용", "알바", "구인", "사건", "사고", "뉴스", "드라마", "영화", "가사", "노래",
    "주식", "로또", "선거", "영어로", "뜻",
]


def _get_json(url: str):
    req = urllib.request.Request(url, headers=UA)
    return json.loads(urllib.request.urlopen(req, timeout=15).read().decode("utf-8"))


def _naver_suggest(q: str) -> list:
    url = "https://ac.search.naver.com/nx/ac?" + urllib.parse.urlencode({
        "q": q, "con": "1", "frm": "nv", "ans": "2", "r_format": "json", "r_enc": "UTF-8",
        "r_unicode": "0", "t_koreng": "1", "run": "2", "rev": "4", "q_enc": "UTF-8", "st": "100"})
    try:
        return [i[0] for i in _get_json(url).get("items", [[]])[0]]
    except Exception:
        return []


def _google_suggest(q: str) -> list:
    url = "https://suggestqueries.google.com/complete/search?" + urllib.parse.urlencode(
        {"client": "firefox", "hl": "ko", "q": q})
    try:
        return _get_json(url)[1]
    except Exception:
        return []


def naver_volumes(queries: list) -> dict:
    """네이버 검색광고 API 월간 검색량. 키가 없거나 실패하면 빈 dict."""
    def _clean(name):
        return os.environ.get(name, "").strip().strip('"').strip("'").strip()
    cid, key, secret = _clean("NAVER_AD_CUSTOMER_ID"), _clean("NAVER_AD_API_KEY"), _clean("NAVER_AD_SECRET")
    if not (cid and key and secret):
        print("[info] 네이버 검색량 키 없음 — 자동완성 순위로 고른다")
        return {}

    def _n(v):
        return int(v) if str(v).isdigit() else 5

    vols = {}
    hints = list(dict.fromkeys(q.replace(" ", "") for q in queries))
    for i in range(0, len(hints), 5):
        batch = hints[i:i + 5]
        ts = str(int(time.time() * 1000))
        sig = base64.b64encode(hmac.new(secret.encode(), f"{ts}.GET./keywordstool".encode(),
                                        hashlib.sha256).digest()).decode()
        url = "https://api.searchad.naver.com/keywordstool?" + urllib.parse.urlencode(
            {"hintKeywords": ",".join(batch), "showDetail": "1"})
        req = urllib.request.Request(url, headers={
            "X-Timestamp": ts, "X-API-KEY": key, "X-Customer": cid, "X-Signature": sig})
        try:
            data = json.loads(urllib.request.urlopen(req, timeout=20).read().decode("utf-8"))
        except Exception as exc:
            # 오류 본문에 키 일부가 들어 있어 종류와 코드만 남긴다
            print(f"[warn] 네이버 검색량 조회 실패 ({type(exc).__name__} {getattr(exc, 'code', '')})")
            return vols
        for row in data.get("keywordList", []):
            if row["relKeyword"] in batch:
                vols[row["relKeyword"]] = _n(row.get("monthlyPcQcCnt")) + _n(row.get("monthlyMobileQcCnt"))
        time.sleep(0.2)
    return vols


def collect() -> list:
    score = {}
    for seed in SEEDS:
        for source in (_naver_suggest, _google_suggest):
            for rank, q in enumerate(source(seed + " ")[:10]):
                q = re.sub(r"\s+", " ", q).strip()
                if len(q) < 4 or q == seed or any(b in q.lower() for b in BLOCK):
                    continue
                score[q] = score.get(q, 0) + (10 - rank) / 10
    cands = [{"query": q, "score": round(s, 2)} for q, s in sorted(score.items(), key=lambda kv: -kv[1])]
    top = cands[:120]
    vols = naver_volumes([c["query"] for c in top])
    if vols:
        for c in top:
            c["volume"] = vols.get(c["query"].replace(" ", ""), 0)
        top.sort(key=lambda c: -c["volume"])
        return top
    return cands


PROMPT = """너는 제주 성산의 호텔아로하 블로그 편집장이다. 오늘은 {today}이다.
독자는 제주 여행을 준비하는 한국인이다. 블로그 목적은 검색 유입과 호텔아로하 노출이다.

아래는 오늘 네이버·구글에서 실제로 많이 검색되는 제주 여행 검색어 후보다.
{candidates}

이미 다룬 주제 (비슷한 건 피한다):
{used}

오늘 쓸 글 주제 1개를 고른다.
- 검색량이 많고, 지금 시기(계절·축제·행사)에 맞는 것을 우선한다.
- 성산·제주 동부 주제면 좋지만, 제주 전역 주제도 된다 (호텔은 동쪽 거점으로 자연스럽게 연결).
- 항공권·날씨·부동산처럼 블로그 글로 답하기 어려운 검색어는 피한다.
- search_keyword 는 후보 검색어를 그대로 쓴다.

다음 JSON 하나만 출력한다:
{{"search_keyword": "후보 검색어 그대로", "cat": "{cats}", "ko": "글 방향 한 문장",
  "kw_ko": "핵심 키워드(제목 앞 10자 안에 넣을 것)", "kw_en": "영문 키워드 (주소용, 3~5단어)",
  "q": ["검색 질문 3~4개"], "img": ["사진 태그 2~3개: {tags}"],
  "place": ["관광공사 사진 검색용 장소명 1~3개 (예: 성산일출봉, 우도)"], "why": "고른 이유 한 줄"}}"""

TAGS = ("exterior, room, oceanview, family, kitchen, lobby, surroundings, sunrise-peak, udo, "
        "seopjikoji, gwangchigi, convenience-store, night")


def pick_topic(env, seo, pool: list, done: set, today: str):
    """오늘의 한국어 주제 하나. 실패하면 None."""
    try:
        cands = collect()
    except Exception as exc:
        print(f"[warn] 검색어 수집 실패: {exc}")
        return None
    if len(cands) < 10:
        return None
    has_vol = "volume" in cands[0]
    print(f"[info] 검색어 후보 {len(cands)}개" + (" (네이버 검색량 반영)" if has_vol else ""))

    used = [t.get("ko", "") for t in pool if t["id"] in done][-60:]
    import anthropic
    client = anthropic.Anthropic(api_key=env.anthropic_key, max_retries=3, timeout=120.0)
    prompt = PROMPT.format(
        today=today,
        candidates="\n".join(
            f"- {c['query']} (월 {c['volume']:,}회)" if has_vol else f"- {c['query']} ({c['score']})"
            for c in cands[:80]),
        used="\n".join(f"- {u}" for u in used) or "(없음)",
        cats=" | ".join(seo["categories"].keys()),
        tags=TAGS,
    )
    try:
        resp = client.messages.create(model=env.model, max_tokens=4000,
                                      messages=[{"role": "user", "content": prompt}])
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        t = json.loads(text[text.index("{"): text.rindex("}") + 1], strict=False)
    except Exception as exc:
        print(f"[warn] 검색량 주제 선정 실패: {exc} / 응답 앞부분: {text[:200]!r}"
              if "text" in locals() else f"[warn] 검색량 주제 선정 실패: {exc}")
        return None

    if t.get("cat") not in seo["categories"]:
        t["cat"] = "제주전역여행"
    t["id"] = "d" + today.replace("-", "")[2:]
    t["track"] = "demand"
    vol = next((c.get("volume") for c in cands if c["query"] == t.get("search_keyword")), None)
    print(f"[info] 검색량 주제: [{t.get('search_keyword')}]"
          + (f" 월 {vol:,}회" if vol else "") + f" — {t.get('why', '')}")
    return t
