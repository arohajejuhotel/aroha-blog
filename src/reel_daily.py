# -*- coding: utf-8 -*-
"""매일 훅 릴스 1편 (인스타 릴스 + 네이버 클립) 을 만들어 구글 드라이브에 저장한다 (2026-10-23).

1) 훅 씨앗 키워드(가을·억새·돌고래·숨은 명소·현지인 추천 …)로 네이버·구글 자동완성을 모아
   네이버 월간 검색량으로 정렬한다.
2) Claude 가 검색량·시기·호텔 거리를 보고 오늘 다룰 장소 후보를 고른다.
3) 후보마다 관광공사 사진(공공누리 1유형만, 글자를 얹으므로)이 5장 이상이고
   소개문이 키워드를 뒷받침하면, Claude 가 사진을 보고 장면별 자막을 쓴다 (내레이션 없음, 음원은 앱에서).
4) src.reels 로 영상 두 편을 만들고 '인스타그램 게시물/아로하 릴스/날짜 [릴스] 제목' 에 저장.

사용:
    python -m src.reel_daily                 # 자동 (드라이브 저장 + state/reels.json 기록)
    python -m src.reel_daily --place 따라비오름 --keyword "제주 억새 명소"
    python -m src.reel_daily --out out/reel  # 드라이브 대신 로컬 폴더에 저장, 기록하지 않음
"""
import argparse
import base64
import io
import json
import math
import re
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from PIL import Image

from src import cliche, demand, gdrive, reels, settings, tour_photos

KST = timezone(timedelta(hours=9))
STATE = settings.ROOT / "state" / "reels.json"
HOTEL = (33.46647, 126.9310441)
MIN_PHOTOS = 5
UA = {"User-Agent": "Mozilla/5.0"}

# 사람들이 끌리는 훅 키워드 씨앗 (2026-10-23 조사: 감귤체험·핑크뮬리·억새·돌고래·일몰·동백·오름이 검색량 상위)
SEEDS = [
    "제주 숨은 명소", "제주 숨은 여행지", "제주 현지인 추천", "제주 가을", "제주 가을 여행",
    "제주 억새", "제주 억새 명소", "제주 핑크뮬리", "제주 돌고래", "제주 돌고래 스팟",
    "제주 일몰 명소", "제주 노을 명소", "제주 동백", "제주 단풍", "제주 오름 추천",
    "제주 동쪽 가볼만한곳", "성산 가볼만한곳", "우도 가볼만한곳", "제주 감귤체험",
    "제주 핫플", "요즘 제주도 핫플", "제주 꼭 가야할 곳", "제주 사진 명소", "제주 인생샷",
    "제주 산책", "제주 해녀", "제주 겨울", "제주 12월", "제주 11월 가볼만한곳",
]


# 계절 소재와 제주에서 볼 수 있는 달 (2026-10-26: 10월에 동백 릴스가 '이번 가을 꼭' 으로 나가서 추가)
SEASONS = {
    "억새": (9, 10, 11), "핑크뮬리": (9, 10, 11), "단풍": (10, 11), "감귤": (10, 11, 12, 1),
    "동백": (11, 12, 1, 2, 3), "수선화": (12, 1, 2), "매화": (1, 2, 3), "유채": (2, 3, 4),
    "벚꽃": (3, 4), "청보리": (4, 5), "메밀": (5, 6, 9, 10), "수국": (6, 7), "해바라기": (7, 8),
}

# 호텔 소개에 붙는 '성산' 은 장소가 멀어도 쓸 수 있다
HOTEL_SEONGSAN = ("성산 호텔아로하", "성산 현지 호텔", "성산일출봉", "성산숙소")


def now() -> datetime:
    return datetime.now(KST)


def area_of(addr: str) -> str:
    """주소에서 자막에 쓸 동네 이름. '서귀포시 남원읍 …' → '남원', 읍면이 없으면 시 이름."""
    m = re.search(r"(\S+?)[읍면]\s", addr + " ")
    if m:
        return m.group(1)
    m = re.search(r"(제주|서귀포)시", addr)
    return m.group(1) if m else "제주"


def season_of(text: str) -> list:
    """글자에 든 계절 소재와 제철 달 [(소재, 달들)]."""
    return [(k, months) for k, months in SEASONS.items() if k in text]


def season_note(keyword: str, month: int) -> str:
    notes = []
    for k, months in season_of(keyword):
        span = f"{months[0]}~{months[-1]}월"
        if month in months:
            notes.append(f"'{k}' 제철: {span}. 오늘({month}월)은 제철이다.")
        else:
            notes.append(f"'{k}' 제철: {span}. 오늘({month}월)은 제철이 아니다. 지금 볼 수 있다고 하지 말고, "
                         f"언제 볼 수 있는지 알려 주며 '그때 가려고 저장' 하게 만든다.")
    return "\n".join(notes) or "계절 소재 없음. 계절 표현은 오늘 날짜에 맞게만 쓴다."


def km_from_hotel(lat: float, lng: float) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (*HOTEL, lat, lng))
    a = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(a))


def dist_phrase(km: float) -> str:
    """자막에 쓸 거리 문구. 직선거리라 가까운 곳만 숫자로 말한다."""
    if km <= 2:
        return f"호텔아로하에서 {max(1, round(km))}km 남짓"
    if km <= 10:
        return f"호텔아로하에서 약 {round(km)}km"
    return "성산 호텔아로하에서 출발하는 제주 여행 (km 숫자와 방향은 쓰지 않는다)"


def load_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"reels": []}


def collect_keywords() -> list:
    score = {}
    for seed in SEEDS:
        for source in (demand._naver_suggest, demand._google_suggest):
            for rank, q in enumerate(source(seed + " ")[:10]):
                q = re.sub(r"\s+", " ", q).strip()
                if len(q) < 4 or any(b in q.lower() for b in demand.BLOCK):
                    continue
                score[q] = score.get(q, 0) + (10 - rank) / 10
    qs = list(dict.fromkeys(SEEDS + sorted(score, key=lambda q: -score[q])[:120]))
    vols = demand.naver_volumes(qs)
    rows = [{"query": q, "volume": vols.get(q.replace(" ", ""), 0), "score": round(score.get(q, 0), 2)}
            for q in qs]
    rows.sort(key=lambda r: (-r["volume"], -r["score"]))
    return rows


def _ask(client, model: str, content, max_tokens: int = 6000) -> dict:
    resp = client.messages.create(model=model, max_tokens=max_tokens,
                                  messages=[{"role": "user", "content": content}])
    text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    return json.loads(text[text.index("{"): text.rindex("}") + 1], strict=False)


PICK = """너는 제주 성산 호텔아로하의 인스타 릴스·네이버 클립 기획자다. 오늘은 {today}이다.
목표: 사람들이 끌리는 제주 키워드로 장소 하나를 소개하는 30초 안팎 릴스. 끝에서 호텔아로하를 자연스럽게 알린다.

오늘 네이버·구글에서 실제로 검색되는 키워드 (네이버 월간 검색량):
{keywords}

최근 다룬 장소 (다시 고르지 않는다): {used}

장소 후보 8개를 고른다.
- 검색량이 많고 지금 시기(계절·꽃·축제)에 맞는 키워드를 우선한다.
  꽃·억새 같은 계절 소재는 이번 달에 실제로 볼 수 있는 것만 고른다. 제주 제철: {seasons}
- 제주 동쪽(성산·구좌·표선·우도·남원)에 있으면 더 좋다. 호텔은 성산일출봉 앞이다.
- 장소는 한국관광공사 관광정보에 등록된 관광지 이름으로 쓴다 (예: 따라비오름, 비자림, 휴애리자연생활공원, 혼인지).
  가게·식당·카페·숙소는 고르지 않는다.
- hook 은 첫 장면에 쓸 끌림 방식: 숨은명소 | 현지인추천 | 요즘핫플 | 계절한정 | 저장각 중 하나.

JSON 하나만 출력한다:
{{"candidates": [{{"keyword": "키워드 그대로", "place": "관광지 이름", "hook": "…", "why": "한 줄"}}]}}"""


SCRIPT = """너는 제주 성산 호텔아로하의 릴스 대본 작가다. 오늘은 {today}이다.
위 사진 {n}장(번호 0 ~ {last})은 '{place}'의 한국관광공사 사진이다.

이번 릴스: 키워드 '{keyword}' (네이버 월 {volume}회), 끌림 방식 '{hook}'
장소 소개문 (한국관광공사, 이 내용 안에서만 사실을 쓴다):
{overview}
장소 주소: {addr}
장소 동네: {area} ({area_rule})
호텔아로하에서 직선거리: 약 {km}km
호텔 사실: 성산일출봉 걸어서 5분, 광치기해변 걸어서 5분, 오션뷰 객실, 1층 GS25 편의점.
제철: {season}

먼저 판단한다: 키워드의 핵심(예: 억새, 돌고래, 핑크뮬리, 동백)이 소개문이나 사진에 없으면
대본을 쓰지 말고 {{"skip": "이유"}} 만 출력한다. 없는 것을 있다고 하지 않는다.

대본 규칙:
- 장소를 꾸미는 동네 이름(제목·머리말·훅·캡션)은 '{area}' 로 쓴다. 장소가 성산읍이 아니면
  '성산에 숨은', '성산 근처' 처럼 장소에 성산을 붙이지 않는다. 성산은 호텔을 말할 때만 쓴다.
- 계절 표현('이번 가을', '지금', '요즘')은 위 제철과 오늘 날짜에 맞아야 한다.
  제철이 아니면 피는 시기를 알려 주고 그때 가 보라고 마무리한다 (예: "11월부터 붉게 피어요").
- 내레이션은 없다. 음악 위에 자막만으로 이야기가 이어져야 한다.
- 말투는 친구에게 알려 주듯 말하는 존댓말 ("~예요", "~해요"). 글처럼 꾸민 문장은 쓰지 않는다.
  나쁜 예: "능선 따라 걷는 길, 그림처럼 펼쳐져요" / 좋은 예: "입구부터 벌써\\n억새가 하얗게 깔려 있어요"
- 첫 장면은 훅이다. 끌림 방식에 맞춰 시작한다. 예:
  숨은명소 "{area}에 숨은 산책길, 하나 알려드릴게요" / 현지인추천 "성산 현지 호텔이 추천하는 {area} 오름" /
  요즘핫플 "요즘 제주에서 제일 많이 찾는 곳, 어딘지 아세요?" / 계절한정 "이 풍경, 딱 지금만 볼 수 있어요" /
  저장각 "제주 가기 전에 이건 저장해 두세요"
- 둘째 장면에서 장소 이름을 밝힌다.
- 전체 길이 25~30초: 장소 장면 6~8개.
- 사진 번호(photo)를 장면마다 고른다. 같은 사진은 두 번까지만. 첫 장면 사진은 가장 눈길을 끄는 것.
  자막이 사진 내용과 맞아야 한다 (다리 사진에 다리 이야기).
- 소개문에 없는 시간·요금·숫자·전설·풍경(예: 소개문에 없는 '바다가 보여요')은 쓰지 않는다.
  사진 설명은 사진에 확실히 보이는 것만. 날씨·시기 표현은 '가을이면'처럼 소개문 수준으로.
- 그다음 호텔 장면 1개(외관 사진). 거리는 이 문구를 그대로 쓴다 {dist}
  자막 예: "호텔아로하에서\\n1km 남짓" / "성산 호텔아로하에서\\n출발하는 동쪽 여행". 호텔의 단점·한계는 절대 말하지 않는다.
- 마지막 장면 1개(객실 영상): "저장해 두고 … 꼭 가 보세요" 같은 마무리.
- 자막(sub): 최대 2줄, 줄바꿈은 \\n, 한 줄 15자 이내, 의미 단위로 끊는다. 한자·이모지 금지.
- em: 자막 안에서 노랗게 강조할 낱말 (자막에 그대로 들어 있는 글자, 없으면 "").
- kicker: 장소를 꾸미는 머리말 (12자 이내, 예: "{area} 숨은 산책길", "가을 억새 명소"). 훅 문장을 넣지 않는다. name: 장소 이름 (9자 이내).
- sub_line: 예약 안내 화면 한 줄 (예: "오조포구 1km 남짓 · 성산일출봉 걸어서 5분", 30자 이내).
- caption_insta: 인스타 캡션. 3~5줄 + 빈 줄 + 해시태그 10개 안팎(#호텔아로하 #성산숙소 포함).
- caption_naver: 네이버 클립 설명. 2~4줄 + 해시태그 5~7개.
  두 캡션 모두 끝 줄에 "사진: 한국관광공사 (공공누리 제1유형)".
- title: 드라이브 폴더용 짧은 제목 (예: "{area} 숨은 산책길 {place}").
{cliche}

JSON 하나만 출력한다:
{{"title": "…", "kicker": "…", "name": "…", "sub_line": "…",
  "scenes": [{{"photo": 0, "sub": "…", "em": "…"}}],
  "hotel": {{"sub": "…", "em": "…"}},
  "cta": {{"sub": "…", "em": "…"}},
  "caption_insta": "…", "caption_naver": "…"}}"""


def place_info(key: str, place: str):
    items = [i for i in tour_photos._call(key, "KorService2", "searchKeyword2", keyword=place,
                                          lDongRegnCd=tour_photos.JEJU_REGION, numOfRows=20)
             if str(i.get("contenttypeid")) in tour_photos.PLACE_TYPES
             and place.replace(" ", "") in i.get("title", "").replace(" ", "")]
    if not items:
        return None
    items.sort(key=lambda i: len(i.get("title", "")))
    it = items[0]
    detail = tour_photos._call(key, "KorService2", "detailCommon2", contentId=it["contentid"])
    overview = re.sub(r"<[^>]+>", " ", (detail[0].get("overview") if detail else "") or "")
    photos = [p for p in tour_photos._place_photos(key, it["title"], "ko") if p["editable"]]
    return {"title": it["title"], "addr": it.get("addr1", ""), "overview": overview.strip(),
            "km": km_from_hotel(float(it["mapy"]), float(it["mapx"])), "photos": photos}


def download(url: str):
    try:
        resp = requests.get(url, headers=UA, timeout=30)
        resp.raise_for_status()
        im = Image.open(io.BytesIO(resp.content)).convert("RGB")
        return im if min(im.size) >= 400 else None
    except Exception:  # noqa: BLE001
        return None


def _b64(im: Image.Image) -> dict:
    sm = im.copy()
    sm.thumbnail((768, 768))
    buf = io.BytesIO()
    sm.save(buf, "JPEG", quality=80)
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                        "data": base64.b64encode(buf.getvalue()).decode()}}


def _check(s: dict, n: int, area: str) -> str:
    """대본 형식 점검. 문제가 있으면 이유를 돌려준다."""
    scenes = s.get("scenes") or []
    if not 5 <= len(scenes) <= 9:
        return f"장소 장면 수 {len(scenes)}"
    for sc in scenes + [s.get("hotel") or {}, s.get("cta") or {}]:
        if not sc.get("sub"):
            return "자막 빈 장면"
        if re.search(r"[一-鿿]", sc["sub"]):
            return "자막에 한자"  # Pretendard 에 한자가 없어 네모로 깨진다
        if sc["sub"].count("\n") > 1:
            sc["sub"] = "\n".join(sc["sub"].split("\n")[:2])
        if sc.get("em") and sc["em"] not in sc["sub"]:
            sc["em"] = ""
    for sc in scenes:
        if not isinstance(sc.get("photo"), int):
            return f"사진 번호 {sc.get('photo')}"
        sc["photo"] %= n  # 범위를 넘으면 앞 사진으로 돌린다
    if area != "성산":
        texts = [s.get("title", ""), s.get("kicker", ""), s.get("caption_insta", ""), s.get("caption_naver", ""),
                 *(sc["sub"] for sc in scenes), (s.get("cta") or {}).get("sub", "")]
        for t in texts:
            for ok in HOTEL_SEONGSAN:
                t = t.replace(ok, "")
            if "성산" in t:
                return f"{area} 장소에 '성산' 을 붙임"
    return ""


def write_script(client, model, cand: dict, info: dict, images: list, volume: int) -> dict:
    area = area_of(info["addr"])
    area_rule = "호텔과 같은 성산읍" if area == "성산" else "성산읍이 아니다"
    prompt = SCRIPT.format(today=now().strftime("%Y-%m-%d"), n=len(images), last=len(images) - 1, place=info["title"],
                           keyword=cand["keyword"], volume=f"{volume:,}", hook=cand.get("hook", ""),
                           overview=info["overview"][:1500] or "(소개문 없음)", addr=info["addr"],
                           area=area, area_rule=area_rule, season=season_note(cand["keyword"], now().month),
                           km=f"{info['km']:.1f}", dist=dist_phrase(info["km"]), cliche=cliche.RULE)
    for attempt in range(2):
        s = _ask(client, model, [*map(_b64, images), {"type": "text", "text": prompt}], 8000)
        if s.get("skip"):
            return s
        texts = " ".join(x["sub"] for x in s.get("scenes", []) + [s.get("hotel", {}), s.get("cta", {})]
                         if isinstance(x, dict) and "sub" in x)
        problem = _check(s, len(images), area) or ("상투 표현: " + "; ".join(cliche.find(texts)) if cliche.find(texts) else "")
        if not problem:
            return s
        print(f"[warn] 대본 다시 씀 ({attempt + 1}/2): {problem}")
    return {"skip": f"대본 점검 실패: {problem}"}


def fix_sub_line(script: dict, km: float) -> None:
    """먼 장소를 예약 화면에 호텔 거리와 나란히 쓰면 일출봉 근처로 읽혀서 호텔 사실만 남긴다."""
    if km > 10:
        script["sub_line"] = "성산일출봉 걸어서 5분 · 광치기해변 걸어서 5분"


def make_job(script: dict, images: list) -> dict:
    scenes = [{"src": images[sc["photo"]], "sub": sc["sub"], "em": sc.get("em", "")}
              for sc in script["scenes"]]
    scenes.append({"src": Image.open(reels.EXTERIOR), **script["hotel"]})
    scenes.append({"src": (reels.ROOM_A, 0.4), **script["cta"]})
    return {"kicker": script["kicker"], "name": script["name"], "sub_line": script["sub_line"], "scenes": scenes}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--place", default="")
    ap.add_argument("--keyword", default="")
    ap.add_argument("--hook", default="")
    ap.add_argument("--out", default="", help="드라이브 대신 저장할 로컬 폴더 (기록하지 않음)")
    args = ap.parse_args()

    import anthropic
    key = settings.env("TOUR_API_KEY", required=True)
    model = settings.env("ANTHROPIC_MODEL", "claude-sonnet-5")
    client = anthropic.Anthropic(api_key=settings.env("ANTHROPIC_API_KEY", required=True),
                                 max_retries=3, timeout=300.0)
    state = load_state()
    day = now().strftime("%Y-%m-%d")
    if not args.out and any(r["date"] == day for r in state["reels"]):
        print(f"[info] {day} 릴스는 이미 만들었습니다")
        return 0

    kws = collect_keywords()
    vol = {k["query"]: k["volume"] for k in kws}
    if args.place:
        cands = [{"keyword": args.keyword or args.place, "place": args.place, "hook": args.hook or "현지인추천"}]
    else:
        recent = [r["place"] for r in state["reels"][-40:]]
        listing = "\n".join(f"- {k['query']} (월 {k['volume']:,}회)" for k in kws[:90])
        seasons = ", ".join(f"{k} {m[0]}~{m[-1]}월" for k, m in SEASONS.items())
        cands = _ask(client, model, PICK.format(today=day, keywords=listing, seasons=seasons,
                                                used=", ".join(recent) or "(없음)"))["candidates"]
        cands = [c for c in cands if c.get("place") and c["place"] not in recent]
        off = [c for c in cands if any(now().month not in m for _, m in season_of(c.get("keyword", "")))]
        if off:
            print(f"[skip] 제철 아님: {[c['place'] + '/' + c['keyword'] for c in off]}")
        cands = [c for c in cands if c not in off]
    print(f"[info] 후보: {[c['place'] for c in cands]}")

    for cand in cands:
        info = place_info(key, cand["place"])
        if not info:
            print(f"[skip] {cand['place']}: 관광정보 없음")
            continue
        if any(r["place"] == info["title"] for r in state["reels"][-40:]) and not args.place:
            print(f"[skip] {info['title']}: 최근에 다룸")
            continue
        images = [im for im in (download(p["url"]) for p in info["photos"][:12]) if im]
        if len(images) < MIN_PHOTOS:
            print(f"[skip] {info['title']}: 1유형 사진 {len(images)}장 (최소 {MIN_PHOTOS})")
            continue
        script = write_script(client, model, cand, info, images,
                              vol.get(cand["keyword"], vol.get(cand["keyword"].replace(" ", ""), 0)))
        if script.get("skip"):
            print(f"[skip] {info['title']}: {script['skip']}")
            continue
        fix_sub_line(script, info["km"])
        print(f"[info] 오늘의 릴스: {script['title']} ({cand['keyword']}, {info['km']:.1f}km)")
        break
    else:
        print("::error title=릴스 주제 없음::조건에 맞는 장소를 찾지 못했습니다")
        return 1

    tmp = Path(tempfile.mkdtemp())
    out_dir = Path(args.out) if args.out else tmp / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    files = {"insta": out_dir / "reel_instagram.mp4", "naver": out_dir / "clip_naver.mp4",
             "cover": out_dir / "cover.jpg"}
    secs = reels.build(make_job(script, images), tmp, files["insta"], files["naver"], files["cover"], seed=day)
    (out_dir / "caption_instagram.txt").write_text(script["caption_insta"], encoding="utf-8")
    (out_dir / "caption_naver.txt").write_text(script["caption_naver"], encoding="utf-8")
    (out_dir / "script.json").write_text(json.dumps({**script, "keyword": cand["keyword"], "place": info["title"]},
                                                    ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[ok] 영상 {secs:.1f}초")

    if args.out:
        print(f"[ok] 로컬 저장: {out_dir}")
        return 0
    where = gdrive.save("아로하 릴스", day, f"[릴스] {script['title']}", sorted(out_dir.iterdir()),
                        root_name="인스타그램 게시물")
    print(f"[ok] 드라이브 저장: {where}")
    state["reels"].append({"date": day, "place": info["title"], "keyword": cand["keyword"],
                           "title": script["title"], "folder": where})
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
