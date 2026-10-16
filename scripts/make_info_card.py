"""글 맨 아래에 붙는 '호텔아로하 기본 정보' 카드 이미지를 만든다 (한국어/영어).

    python scripts/make_info_card.py

config/hotel.json 의 정보가 바뀌면 다시 실행하고 커밋한다.
결과: assets/info/hotel-info-ko.png, assets/info/hotel-info-en.png (가로 1080px, 모바일 기준)
"""

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.thumbnail import FONT_BOLD, FONT_REG, _font  # noqa: E402

W = 1080
PAD = 64
CREAM = (244, 241, 236)
INK = (58, 53, 48)
TEAL = (10, 122, 114)
MINT = (62, 202, 192)
GOLD = (232, 197, 71)
LINE = (224, 217, 207)
MUTED = (110, 102, 94)

TEXT = {
    "ko": {
        "heading": "호텔아로하 기본 정보",
        "slogan": "성산일출봉을 앞마당처럼, 광치기해변을 산책로처럼",
        "rows": [
            ("주소", "제주특별자치도 서귀포시 성산읍 성산등용로 40"),
            ("전화", "064-782-3100"),
            ("체크인 · 아웃", "15:00 / 11:00"),
            ("도보 거리", "성산일출봉 5~10분 · 광치기해변 5분\n우도 페리 터미널 10분"),
            ("객실", "디럭스더블 · 스탠다드 트윈 (오션뷰)\n패밀리룸 27평형 (침실·거실 분리, 풀키친)\n이코노미 트윈"),
            ("편의시설", "1층 GS25 (06:00~24:00, ATM)\n무료주차 · EV 충전 · 짐 보관 · 로비 도서관\n한국어·영어·중국어 응대"),
        ],
        "perk_title": "전화 예약 혜택  064-782-3100",
        "perk": "전화로 직접 예약하면\n얼리체크인 12:00 · 레이트체크아웃 13:00",
        "contact": "네이버에서 '호텔아로하' 검색 · 네이버 예약",
    },
    "en": {
        "heading": "Hotel Aroha at a glance",
        "slogan": "Seongsan Ilchulbong as your front yard",
        "rows": [
            ("Address", "40 Seongsandeungyong-ro, Seongsan-eup,\nSeogwipo-si, Jeju, South Korea"),
            ("Phone", "+82-64-782-3100"),
            ("Check-in / out", "15:00 / 11:00"),
            ("On foot", "Seongsan Ilchulbong 5-10 min\nGwangchigi Beach 5 min · Udo ferry 10 min"),
            ("Rooms", "Deluxe Double · Standard Twin (ocean view)\nFamily room (living room, full kitchen)\nEconomy Twin"),
            ("Facilities", "GS25 on the ground floor (06:00-24:00, ATM)\nFree parking · EV charging · Luggage storage\nLobby library · Korean, English, Chinese spoken"),
        ],
        "perk_title": "Book by phone  +82-64-782-3100",
        "perk": "Call to book direct for\nearly check-in 12:00 · late check-out 13:00",
        "contact": "Also on Agoda and Trip.com",
    },
}


def _wrap(draw, text, font, max_w):
    out = []
    for para in text.split("\n"):
        words, cur = para.split(" "), ""
        for w in words:
            trial = f"{cur} {w}".strip()
            if draw.textlength(trial, font=font) <= max_w:
                cur = trial
            else:
                out.append(cur)
                cur = w
        out.append(cur)
    return out


def make(lang: str) -> Path:
    t = TEXT[lang]
    f_head = _font(FONT_BOLD, 30)
    f_slogan = _font(FONT_REG, 30 if lang == "ko" else 26)
    f_key = _font(FONT_BOLD, 30)
    f_val = _font(FONT_REG, 31 if lang == "ko" else 29)
    f_perk_t = _font(FONT_BOLD, 30)
    f_perk = _font(FONT_BOLD, 38 if lang == "ko" else 34)
    f_contact = _font(FONT_REG, 30)

    # 높이를 먼저 계산한다
    probe = ImageDraw.Draw(Image.new("RGB", (W, 10)))
    key_w = 230 if lang == "ko" else 250
    val_w = W - PAD * 2 - key_w
    rows = [(k, _wrap(probe, v, f_val, val_w)) for k, v in t["rows"]]
    slogan_lines = _wrap(probe, t["slogan"], f_slogan, W - PAD * 2)
    perk_lines = t["perk"].split("\n")

    logo = Image.open(ROOT / "assets" / "brand" / "logo.png").convert("RGBA")
    logo.thumbnail((560, 200))

    h = PAD + logo.height + 30 + len(slogan_lines) * 44 + 40
    h += 50  # heading
    for _, lines in rows:
        h += max(1, len(lines)) * 46 + 30
    h += 40 + 70 + len(perk_lines) * 54 + 30 + 50 + 40 + PAD

    img = Image.new("RGB", (W, h), CREAM)
    d = ImageDraw.Draw(img)

    y = PAD
    img.paste(logo, ((W - logo.width) // 2, y), logo)
    y += logo.height + 30
    for ln in slogan_lines:
        d.text(((W - d.textlength(ln, font=f_slogan)) // 2, y), ln, font=f_slogan, fill=MUTED)
        y += 44
    y += 40

    d.text((PAD, y), t["heading"].upper() if lang == "en" else t["heading"], font=f_head, fill=TEAL)
    y += 50
    d.line((PAD, y, W - PAD, y), fill=LINE, width=2)
    y += 22
    for key, lines in rows:
        d.text((PAD, y + 2), key, font=f_key, fill=TEAL)
        for i, ln in enumerate(lines):
            d.text((PAD + key_w, y + i * 46), ln, font=f_val, fill=INK)
        y += max(1, len(lines)) * 46 + 8
        d.line((PAD, y + 8, W - PAD, y + 8), fill=LINE, width=1)
        y += 22
    y += 40

    # 직접 예약 혜택 박스
    box_h = 70 + len(perk_lines) * 54 + 30
    d.rounded_rectangle((PAD, y, W - PAD, y + box_h), radius=22, fill=TEAL)
    d.text((PAD + 40, y + 30), t["perk_title"], font=f_perk_t, fill=GOLD)
    yy = y + 78
    for ln in perk_lines:
        d.text((PAD + 40, yy), ln, font=f_perk, fill=(255, 255, 255))
        yy += 54
    y += box_h + 50

    d.text(((W - d.textlength(t["contact"], font=f_contact)) // 2, y), t["contact"],
           font=f_contact, fill=INK)

    out = ROOT / "assets" / "info" / f"hotel-info-{lang}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, optimize=True)
    return out


if __name__ == "__main__":
    for lang in ("ko", "en"):
        print(make(lang))
