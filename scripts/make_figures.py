"""블로그 본문에 넣을 도표 이미지를 만든다 (한/영).

사진만으로는 전달이 안 되는 정보 — 도보 거리, 일출 시각, 객실 비교, 페리 요금 —
를 브랜드 색으로 그린다. 숫자는 config/hotel.json 의 verified_facts 에 있는 것만 쓴다.

    python scripts/make_figures.py

결과: assets/figures/*.png + assets/figures.json (본문 삽입용 메타데이터)
"""

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "figures"
MANIFEST = ROOT / "assets" / "figures.json"

W = 1000
PAD = 44

CREAM = (244, 241, 236)
OCEAN = (58, 53, 48)
TEAL = (10, 122, 114)
MINT = (62, 202, 192)
GOLD = (232, 197, 71)
LINE = (226, 220, 210)
MUTED = (138, 129, 120)
WHITE = (255, 255, 255)

FONT_DIRS = [Path(r"C:\Windows\Fonts"), Path("/usr/share/fonts/truetype/nanum"),
             Path("/usr/share/fonts")]
BOLD_NAMES = ["malgunbd.ttf", "NanumGothicBold.ttf", "DejaVuSans-Bold.ttf"]
REG_NAMES = ["malgun.ttf", "NanumGothic.ttf", "DejaVuSans.ttf"]


def _find(names):
    for d in FONT_DIRS:
        for n in names:
            p = d / n
            if p.exists():
                return p
    return None


BOLD_PATH, REG_PATH = _find(BOLD_NAMES), _find(REG_NAMES)
if not BOLD_PATH or not REG_PATH:
    print("[error] 한글 폰트를 찾지 못했습니다.", file=sys.stderr)
    raise SystemExit(1)


def bold(size):
    return ImageFont.truetype(str(BOLD_PATH), size)


def reg(size):
    return ImageFont.truetype(str(REG_PATH), size)


def new_canvas(height):
    im = Image.new("RGB", (W, height), WHITE)
    return im, ImageDraw.Draw(im)


def header(d, title, subtitle):
    d.rectangle([0, 0, W, 96], fill=OCEAN)
    d.rectangle([0, 96, W, 100], fill=TEAL)
    d.rectangle([0, 96, W // 3, 100], fill=GOLD)
    d.text((PAD, 28), title, font=bold(30), fill=WHITE)
    if subtitle:
        d.text((PAD, 64), subtitle, font=reg(16), fill=(190, 183, 175))


def footer(d, y, note):
    d.text((PAD, y), note, font=reg(14), fill=MUTED)
    d.text((W - PAD, y), "hotelaroha", font=bold(14), fill=TEAL, anchor="ra")


# ---------------------------------------------------------------- 도보 거리
def fig_walk(lang):
    T = {
        "ko": {"title": "호텔아로하에서 걸어갈 수 있는 곳",
               "sub": "제주 성산 · 렌터카 없이 이동 가능한 범위",
               "rows": [("광치기해변", "도보 5분", 5), ("짱구네 유채꽃밭", "도보 5분", 5),
                        ("성산일출봉", "도보 5~10분", 10), ("우도 페리 터미널", "도보 10분", 10),
                        ("섭지코지", "차로 8분", 24), ("제주국제공항", "차로 약 60분", 60)],
               "note": "도보 기준 성인 보통 걸음. 차량 이동 구간은 회색으로 표시."},
        "en": {"title": "What you can reach on foot from Hotel Aroha",
               "sub": "Seongsan, Jeju - the range you can cover without a car",
               "rows": [("Gwangchigi Beach", "5 min walk", 5),
                        ("Canola flower field", "5 min walk", 5),
                        ("Seongsan Ilchulbong", "5-10 min walk", 10),
                        ("Udo ferry terminal", "10 min walk", 10),
                        ("Seopjikoji", "8 min by car", 24),
                        ("Jeju International Airport", "about 60 min by car", 60)],
               "note": "Walking times at an average adult pace. Grey bars are by car."},
    }[lang]

    rows = T["rows"]
    h = 140 + len(rows) * 62 + 70
    im, d = new_canvas(h)
    header(d, T["title"], T["sub"])

    y = 140
    max_v = max(r[2] for r in rows)
    bar_x, bar_w = 330, W - PAD - 330 - 150
    for name, label, minutes in rows:
        walk = "차" not in label and "car" not in label
        color = TEAL if walk else (176, 170, 162)
        d.text((PAD, y + 6), name, font=bold(19), fill=OCEAN)
        width = max(14, int(bar_w * minutes / max_v))
        d.rounded_rectangle([bar_x, y + 4, bar_x + width, y + 30], radius=13, fill=color)
        d.text((bar_x + width + 14, y + 7), label, font=reg(17),
               fill=OCEAN if walk else MUTED)
        y += 62
        d.line([PAD, y - 16, W - PAD, y - 16], fill=LINE, width=1)

    footer(d, y + 4, T["note"])
    return im


# ---------------------------------------------------------------- 표 공통
def table(title, sub, cols, rows, note, widths=None):
    n = len(rows)
    h = 140 + 50 + n * 56 + 70
    im, d = new_canvas(h)
    header(d, title, sub)

    inner = W - PAD * 2
    widths = widths or [1 / len(cols)] * len(cols)
    xs, acc = [], PAD
    for wgt in widths:
        xs.append(acc)
        acc += inner * wgt

    y = 140
    d.rectangle([PAD, y, W - PAD, y + 46], fill=CREAM)
    for x, c in zip(xs, cols):
        d.text((x + 14, y + 14), c, font=bold(17), fill=TEAL)
    y += 46
    d.line([PAD, y, W - PAD, y], fill=TEAL, width=2)

    for r in rows:
        for i, (x, cell) in enumerate(zip(xs, r)):
            f = bold(17) if i == 0 else reg(17)
            d.text((x + 14, y + 17), str(cell), font=f,
                   fill=OCEAN if i == 0 else (69, 63, 57))
        y += 56
        d.line([PAD, y, W - PAD, y], fill=LINE, width=1)

    footer(d, y + 20, note)
    return im


def fig_sunrise(lang):
    if lang == "ko":
        return table("성산일출봉 여름 일출 시각", "일출 1시간 전 개장 · 성인 입장료 5,000원",
                     ["월", "일출 시각", "숙소에서 나서는 시각(권장)"],
                     [["6월", "05:20 ~ 05:30", "04:45"],
                      ["7월", "05:30 ~ 05:45", "04:55"],
                      ["8월", "05:45 ~ 06:10", "05:10"]],
                     "정상까지 20~30분. 매월 첫째 주 월요일 휴무, 매표 마감은 폐장 1시간 전.",
                     [0.16, 0.38, 0.46])
    return table("Sunrise times at Seongsan Ilchulbong (summer)",
                 "Opens one hour before sunrise · adult admission KRW 5,000",
                 ["Month", "Sunrise", "Suggested departure"],
                 [["June", "05:20 - 05:30", "04:45"],
                  ["July", "05:30 - 05:45", "04:55"],
                  ["August", "05:45 - 06:10", "05:10"]],
                 "20-30 min to the summit. Closed the first Monday of each month; "
                 "ticket sales end one hour before closing.",
                 [0.18, 0.38, 0.44])


def fig_rooms(lang):
    if lang == "ko":
        return table("호텔아로하 객실 3종", "기준 인원과 전망 · 비수기 요금 기준",
                     ["객실", "인원", "전망", "비수기"],
                     [["디럭스더블", "2인", "바다 전망", "120,000원"],
                      ["스탠다드 트윈", "2인 (최대 3인)", "바다 전망", "120,000원"],
                      ["패밀리 트윈", "3인 (최대 4인)", "마을 전망 · 풀키친", "180,000원"]],
                     "추가 인원 1인당 10,000원. 성수기 요금은 예약 채널의 캘린더를 확인하세요.",
                     [0.26, 0.24, 0.31, 0.19])
    return table("Three room types at Hotel Aroha", "Occupancy and view · low-season rate",
                 ["Room", "Guests", "View", "From"],
                 [["Deluxe Double", "2", "Ocean view", "KRW 120,000"],
                  ["Standard Twin", "2 (max 3)", "Ocean view", "KRW 120,000"],
                  ["Family Twin", "3 (max 4)", "Village view · kitchen", "KRW 180,000"]],
                 "Extra guest KRW 10,000 per person. Check the booking calendar for peak dates.",
                 [0.27, 0.21, 0.33, 0.19])


def fig_udo(lang):
    if lang == "ko":
        return table("우도 페리 기본 정보", "성산항 종합여객터미널 · 호텔에서 도보 10분",
                     ["항목", "내용"],
                     [["왕복 요금", "성인 11,500원 (선박료·도립공원료·터미널이용료 포함)"],
                      ["첫 배", "성수기(5~8월) 오전 7:00"],
                      ["막 배", "우도 출발 기준 오후 6:30"],
                      ["예약", "온라인 예약 불가 · 현장 발권만 가능"],
                      ["준비물", "신분증 필수"]],
                     "요금과 운항 시간은 계절과 기상에 따라 바뀝니다. 당일 확인하세요.",
                     [0.24, 0.76])
    return table("Udo ferry basics", "Seongsan Port terminal · 10 min walk from the hotel",
                 ["Item", "Detail"],
                 [["Return fare", "KRW 11,500 per adult (ferry, park and terminal fees)"],
                  ["First boat", "07:00 in peak season (May-August)"],
                  ["Last boat", "18:30 departing Udo"],
                  ["Booking", "No online booking - tickets are sold at the terminal"],
                  ["Bring", "Photo ID is required"]],
                 "Fares and times change with season and weather. Check on the day.",
                 [0.22, 0.78])


FIGURES = {
    "walk-distances": (fig_walk, ["walkable", "location", "sunrise-peak", "udo",
                                  "gwangchigi", "transport"]),
    "sunrise-times": (fig_sunrise, ["sunrise-peak", "sunrise"]),
    "room-types": (fig_rooms, ["family", "deluxe", "standard", "oceanview"]),
    "udo-ferry": (fig_udo, ["udo", "ferry", "daytrip"]),
}

CAPTIONS = {
    "walk-distances": ("호텔아로하에서 걸어갈 수 있는 곳 — 도보 거리 정리",
                       "What you can reach on foot from Hotel Aroha"),
    "sunrise-times": ("성산일출봉 여름 월별 일출 시각과 출발 권장 시각",
                      "Monthly sunrise times at Seongsan Ilchulbong"),
    "room-types": ("호텔아로하 객실 3종 비교 — 인원·전망·요금",
                   "Hotel Aroha room types compared"),
    "udo-ferry": ("우도 페리 요금·운항 시간·발권 방법 정리",
                  "Udo ferry fares, times and ticketing"),
}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    entries = []
    for name, (fn, tags) in FIGURES.items():
        for lang in ("ko", "en"):
            im = fn(lang)
            path = OUT / f"{name}-{lang}.png"
            im.save(path, "PNG", optimize=True)
            entries.append({
                "id": name, "lang": lang, "file": f"{name}-{lang}.png",
                "tags": tags,
                "caption": CAPTIONS[name][0 if lang == "ko" else 1],
                "width": im.width, "height": im.height,
            })
            print(f"  {path.name}  {im.width}x{im.height}  "
                  f"{path.stat().st_size // 1024}KB")

    MANIFEST.write_text(json.dumps({"figures": entries}, ensure_ascii=False, indent=1),
                        encoding="utf-8")
    print(f"\n{len(entries)}개 생성 -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
