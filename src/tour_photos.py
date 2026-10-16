"""한국관광공사 TourAPI 에서 글 주제 장소의 사진을 가져온다.

호텔 사진 110장만 돌려 쓰면 글마다 비슷한 사진이 반복되고, 정작 글이 다루는
장소(한라산, 협재, 서귀포 폭포 등)의 모습은 보여 주지 못한다.

출처와 이용 조건
- 국문 관광정보 서비스(KorService2): 사진마다 cpyrhtDivCd 가 붙는다.
  Type1 = 공공누리 제1유형(출처표시, 변형 가능) / Type3 = 제3유형(출처표시, 변경 금지).
  Type1·Type3 만 쓰고, 그 외 값이거나 비어 있으면 쓰지 않는다.
- 관광사진 정보(PhotoGalleryService1): 한국관광공사 관광사진 갤러리. 촬영자를 함께 표기한다.
- 썸네일처럼 사진 위에 글자를 얹는 용도에는 Type1 만 쓴다 (Type3 는 변경 금지).
- 사진은 원본 주소(tong.visitkorea.or.kr)를 그대로 쓰고 자르거나 고치지 않는다.
"""

import time

import requests

BASE = "https://apis.data.go.kr/B551011"
# 예전 areaCode(39)로 거르면 관광지 다수가 빠진다. 법정동 시도 코드(제주=50)를 쓴다.
JEJU_REGION = "50"
TIMEOUT = 20

# 관광지 12, 문화시설 14, 축제·행사 15, 여행코스 25, 레포츠 28.
# 음식점(39)·숙박(32)·쇼핑(38)은 가게 홍보 사진이라 쓰지 않는다.
PLACE_TYPES = {"12", "14", "15", "25", "28"}

LICENSE = {
    "Type1": "공공누리 제1유형",
    "Type3": "공공누리 제3유형",
}


def _call(key: str, service: str, op: str, **params) -> list:
    params.update(serviceKey=key, MobileOS="ETC", MobileApp="AROHA", _type="json")
    params.setdefault("numOfRows", 20)
    params.setdefault("pageNo", 1)
    data = None
    for attempt in range(2):
        try:
            resp = requests.get(f"{BASE}/{service}/{op}", params=params, timeout=TIMEOUT)
            data = resp.json()
            break
        except (requests.RequestException, ValueError) as exc:
            # 오류 메시지에 요청 주소(serviceKey 포함)가 들어가므로 그대로 찍지 않는다.
            # 공개 저장소의 Actions 로그에 키가 남는다.
            print(f"[warn] TourAPI {op} 실패 ({type(exc).__name__}), 재시도 {attempt + 1}/2")
            time.sleep(2)
    if data is None:
        return []
    header = data.get("response", {}).get("header", {})
    if header.get("resultCode") != "0000":
        print(f"[warn] TourAPI {op} 오류: {header}")
        return []
    items = (data["response"].get("body") or {}).get("items") or {}
    items = items.get("item", []) if isinstance(items, dict) else []
    return items if isinstance(items, list) else [items]


def _credit(lang: str, license_name: str = "", photographer: str = "") -> str:
    if lang == "ko":
        who = f" · {photographer}" if photographer else ""
        lic = f" ({license_name})" if license_name else ""
        return f"사진: 한국관광공사{who}{lic}"
    who = f" / {photographer}" if photographer else ""
    lic = {"공공누리 제1유형": " (KOGL Type 1)", "공공누리 제3유형": " (KOGL Type 3)"}.get(license_name, "")
    return f"Photo: Korea Tourism Organization{who}{lic}"


def _place_photos(key: str, place: str, lang: str) -> list:
    """관광정보 서비스: 장소 검색 → 대표 사진 + 상세 사진 (저작권 유형이 확인된 것만)."""
    found = []
    items = [i for i in _call(key, "KorService2", "searchKeyword2", keyword=place,
                              lDongRegnCd=JEJU_REGION, numOfRows=20)
             if str(i.get("contenttypeid")) in PLACE_TYPES
             and place.replace(" ", "") in i.get("title", "").replace(" ", "")]
    # '카페한라산' 같은 가게 이름이 아니라 장소 자체가 먼저 오게 한다
    items.sort(key=lambda i: (not i.get("title", "").startswith(place.split()[0]),
                              len(i.get("title", ""))))
    for item in items[:3]:
        title = item.get("title", place)
        cid = item.get("contentid")
        if item.get("firstimage") and item.get("cpyrhtDivCd") in LICENSE:
            found.append({"url": item["firstimage"], "title": title,
                          "license": LICENSE[item["cpyrhtDivCd"]],
                          "editable": item["cpyrhtDivCd"] == "Type1", "photographer": ""})
        if cid:
            for img in _call(key, "KorService2", "detailImage2", contentId=cid,
                             imageYN="Y", numOfRows=10):
                code = img.get("cpyrhtDivCd")
                if img.get("originimgurl") and code in LICENSE:
                    found.append({"url": img["originimgurl"], "title": title,
                                  "license": LICENSE[code], "editable": code == "Type1",
                                  "photographer": ""})
        if found:
            break  # 첫 번째로 맞는 장소면 충분하다
    return found


def _gallery_photos(key: str, place: str) -> list:
    """관광사진 갤러리: 키워드 검색. 촬영자 표기를 붙인다. 변형하지 않는다."""
    found = []
    for item in _call(key, "PhotoGalleryService1", "gallerySearchList1",
                      keyword=place, numOfRows=20):
        url = item.get("galWebImageUrl")
        if not url:
            continue
        # 제주 밖 같은 이름의 장소가 섞이지 않게 촬영장소를 본다
        if "제주" not in (item.get("galPhotographyLocation") or "") + (item.get("galSearchKeyword") or ""):
            continue
        found.append({"url": url, "title": item.get("galTitle", place), "license": "",
                      "editable": False, "photographer": item.get("galPhotographer", "")})
    return found


def find(key: str, places: list, lang: str, count: int, used: set) -> list:
    """주제 장소 사진을 count 장까지 고른다. 이미 쓴 사진(used)은 뒤로 미룬다."""
    if not key or not places:
        return []
    pool, seen = [], set()
    for place in places:
        for p in _place_photos(key, place, lang) + _gallery_photos(key, place):
            if p["url"] in seen:
                continue
            seen.add(p["url"])
            p["place"] = place
            pool.append(p)
    # 안 쓴 사진 먼저, 그다음 저작권 유형이 확인된 사진 먼저
    pool.sort(key=lambda p: (p["url"] in used, not p["license"]))

    picked, per_place = [], {}
    for p in pool:
        # 한 장소에 몰리지 않게 장소당 최대 2장
        if per_place.get(p["place"], 0) >= 2 and len(places) > 1:
            continue
        picked.append(p)
        per_place[p["place"]] = per_place.get(p["place"], 0) + 1
        if len(picked) >= count:
            break
    for p in picked:
        p["credit"] = _credit(lang, p["license"], p["photographer"])
    return picked


def thumbnail_source(key: str, places: list, used: set):
    """썸네일 배경으로 쓸 수 있는(변형 가능한 Type1) 사진 한 장의 URL."""
    if not key:
        return None
    for place in places:
        cands = [p for p in _place_photos(key, place, "ko") if p["editable"]]
        cands.sort(key=lambda p: p["url"] in used)
        if cands:
            return cands[0]
    return None


def to_refs(photos: list, start: int, lang: str) -> list:
    """생성 모델에게 넘길 참조. 호텔 사진 다음 번호를 이어서 쓴다."""
    refs = []
    for n, p in enumerate(photos):
        alt = p["title"].split("[")[0].strip() or p["place"]
        refs.append({
            "id": f"IMG{start + n}",
            "url": p["url"],
            "alt": alt if lang == "ko" else f"{alt}, Jeju",
            "credit": p["credit"],
            "orientation": "landscape",
            "tags": ["place", p["place"]],
            "note": ("이 사진은 글 주제 장소의 실제 모습이다. 그 장소를 설명하는 문단 바로 아래에 둔다."
                     if lang == "ko" else
                     "Actual photo of the place this post covers. Put it right after the paragraph about that place."),
        })
    return refs
