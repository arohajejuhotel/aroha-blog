"""인스타그램 캐러셀 카드(1080x1350, 4:5)를 만든다.

블로그 글 하나를 5~7장 카드로 다시 짠다.
 - 1장  표지: 블로그 썸네일과 같은 디자인 (사진 + 라벨 + 굵은 제목)
 - 중간 정보 카드: 위 사진 + 아래 크림 패널 (번호 · 소제목 · 본문 2~4줄)
 - 마지막 예약 카드: 다크 배경 + 로고 + 호텔 강점 + "예약은 프로필 링크에서"

카드 문구(slides)는 writer 단계에서 Claude 가 만든다. 여기서는 그리기만 한다.
"""

from pathlib import Path

from PIL import Image, ImageDraw

from src import thumbnail
from src.thumbnail import FONT_BOLD, FONT_REG, W, H, _cover, _font, _wrap

ROOT = Path(__file__).resolve().parents[1]
LOGO = ROOT / "assets" / "brand" / "logo.png"

# 웹사이트·블로그와 같은 브랜드 색
CREAM = (244, 241, 236)
OCEAN = (58, 53, 48)
TEAL = (10, 122, 114)
MINT = (62, 202, 192)
GOLD = (232, 197, 71)
MUTED = (120, 112, 104)

HANDLE = "@hotel_aroha_jeju"
PHOTO_H = 720  # 정보 카드 위쪽 사진 높이
PAD = 72


def _footer(d: ImageDraw.ImageDraw, page: int, total: int, color, dot_on, dot_off,
            brand: bool = True) -> None:
    """맨 아래: 브랜드 + 넘김 점. brand=False 면 점만 가운데에."""
    if brand:
        d.text((PAD, H - 92), "HOTEL AROHA", font=_font(FONT_BOLD, 28), fill=color)
    r, gap = 7, 26
    x0 = W - PAD - (total - 1) * gap if brand else (W - (total - 1) * gap) / 2
    for i in range(total):
        cx, cy = x0 + i * gap, H - 76
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=dot_on if i == page - 1 else dot_off)


def cover(lines: list, cat: str, photo: Image.Image, credit: str, out: Path,
          badge: tuple = ()) -> Path:
    """1장: 블로그 썸네일 디자인을 그대로 쓴다 (계정 전체 톤이 한 줄로 이어진다)."""
    thumbnail.make(lines, cat, "ko", photo, credit, out, badge=badge)
    img = Image.open(out)
    d = ImageDraw.Draw(img)
    # 오른쪽 아래 넘김 안내
    f = _font(FONT_BOLD, 30)
    label = "넘겨보기  →"
    d.text((W - PAD - d.textlength(label, font=f), H - 128), label, font=f, fill=(255, 255, 255))
    img.save(out, "JPEG", quality=88, optimize=True, progressive=True)
    return out


def info(no: int, heading: str, body: str, photo: Image.Image, page: int, total: int,
         out: Path, credit: str = "") -> Path:
    """정보 카드: 위 사진, 아래 크림 패널에 번호 · 소제목 · 본문."""
    img = Image.new("RGB", (W, H), CREAM)
    ph = _cover_box(photo, W, PHOTO_H)
    img.paste(ph, (0, 0))
    d = ImageDraw.Draw(img)
    if credit:
        f_c = _font(FONT_REG, 22)
        d.text((W - 24 - d.textlength(credit, font=f_c), PHOTO_H - 40), credit,
               font=f_c, fill=(235, 235, 235))

    # 번호 배지 (사진과 패널 경계에 걸친 민트 원)
    cx, cy, r = PAD + 44, PHOTO_H, 44
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=MINT)
    f_no = _font(FONT_BOLD, 40)
    num = f"{no:02d}"
    d.text((cx - d.textlength(num, font=f_no) / 2, cy - 26), num, font=f_no, fill=OCEAN)

    # 소제목 (최대 2줄, 넘치면 글자를 줄인다)
    y = PHOTO_H + 78
    size = 60
    while True:
        f_h = _font(FONT_BOLD, size)
        hl = _wrap(d, heading, f_h, W - PAD * 2)
        if len(hl) <= 2 or size <= 44:
            break
        size -= 4
    for ln in hl[:2]:
        d.text((PAD, y), ln, font=f_h, fill=OCEAN)
        y += int(size * 1.3)

    # 골드 짧은 선
    y += 14
    d.line((PAD, y, PAD + 64, y), fill=GOLD, width=6)
    y += 36

    # 본문 (줄바꿈 존중, 최대 5줄)
    f_b = _font(FONT_REG, 40)
    bl = []
    for para in body.split("\n"):
        bl += _wrap(d, para, f_b, W - PAD * 2) if para.strip() else [""]
    for ln in bl[:5]:
        d.text((PAD, y), ln, font=f_b, fill=(80, 74, 68))
        y += 62

    _footer(d, page, total, MUTED, TEAL, (210, 204, 196))
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "JPEG", quality=88, optimize=True, progressive=True)
    return out


def cta(heading: str, points: list, page: int, total: int, out: Path) -> Path:
    """마지막 카드: 예약 유도."""
    img = Image.new("RGB", (W, H), OCEAN)
    d = ImageDraw.Draw(img)
    f_h = _font(FONT_BOLD, 62)
    f_p = _font(FONT_REG, 42)
    hl = _wrap(d, heading, f_h, W - PAD * 2)[:2]
    points = points[:4]
    lg = _logo_on_dark(Image.open(LOGO).convert("RGBA"), 420) if LOGO.exists() else None

    # 로고·제목·강점 묶음을 버튼 위 공간의 가운데에 놓는다
    block = (lg.height + 100 if lg else 0) + len(hl) * 84 + 50 + len(points) * 76
    y = max(110, (H - 330 - block) // 2)

    if lg:
        img.paste(lg, ((W - lg.width) // 2, y), lg)
        y += lg.height + 100
    for ln in hl:
        d.text(((W - d.textlength(ln, font=f_h)) / 2, y), ln, font=f_h, fill=CREAM)
        y += 84
    y += 50

    widest = max((d.textlength(p, font=f_p) for p in points), default=0)
    x = (W - widest - 56) / 2
    for p in points:
        d.ellipse((x, y + 16, x + 24, y + 40), fill=MINT)
        d.text((x + 52, y), p, font=f_p, fill=CREAM)
        y += 76

    # 예약 안내 알약 버튼
    f_btn = _font(FONT_BOLD, 40)
    label = "예약·문의는 프로필 링크에서"
    tw = d.textlength(label, font=f_btn)
    bx0, by0 = (W - tw) / 2 - 56, H - 300
    d.rounded_rectangle((bx0, by0, bx0 + tw + 112, by0 + 100), radius=50, fill=GOLD)
    d.text((bx0 + 56, by0 + 24), label, font=f_btn, fill=OCEAN)
    f_hd = _font(FONT_REG, 30)
    d.text(((W - d.textlength(HANDLE, font=f_hd)) / 2, by0 + 132), HANDLE, font=f_hd,
           fill=(200, 194, 186))

    _footer(d, page, total, (200, 194, 186), MINT, (110, 104, 98), brand=False)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "JPEG", quality=88, optimize=True, progressive=True)
    return out


def _cover_box(img: Image.Image, w: int, h: int) -> Image.Image:
    img = img.convert("RGB")
    scale = max(w / img.width, h / img.height)
    img = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
    left, top = (img.width - w) // 2, (img.height - h) // 2
    return img.crop((left, top, left + w, top + h))


def _logo_on_dark(logo: Image.Image, width: int) -> Image.Image:
    """회색 글자는 크림, 청록 잎은 민트로 바꾼다."""
    logo = logo.crop(logo.getchannel("A").getbbox())
    logo = logo.resize((width, round(logo.height * width / logo.width)), Image.LANCZOS)
    px = logo.load()
    for yy in range(logo.height):
        for xx in range(logo.width):
            r, g, b, a = px[xx, yy]
            if a:
                px[xx, yy] = (*(MINT if g - r > 40 else CREAM), a)
    return logo


def build(slides: dict, photos: list, out_dir: Path, stem: str, cat: str,
          credits: list = None) -> list:
    """slides = {"cover_lines": [...], "cards": [{"heading","body"}...],
                 "cta_heading": str, "cta_points": [...]}
    photos[0] 은 표지, 이후는 정보 카드에 순서대로 쓴다 (모자라면 돌려쓴다)."""
    credits = credits or [""] * len(photos)
    cards = slides["cards"]
    total = len(cards) + 2
    files = [cover(slides["cover_lines"], cat, photos[0], credits[0],
                   out_dir / f"{stem}-01.jpg")]
    rest = list(zip(photos[1:], credits[1:])) or [(photos[0], credits[0])]
    for i, c in enumerate(cards, 1):
        ph, cr = rest[(i - 1) % len(rest)]
        files.append(info(i, c["heading"], c["body"], ph, i + 1, total,
                          out_dir / f"{stem}-{i + 1:02d}.jpg", credit=cr))
    files.append(cta(slides["cta_heading"], slides["cta_points"], total, total,
                     out_dir / f"{stem}-{total:02d}.jpg"))
    return files
