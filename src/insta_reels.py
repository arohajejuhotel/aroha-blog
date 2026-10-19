# -*- coding: utf-8 -*-
"""캐러셀 카드(1080x1350)를 릴스용 세로 영상(1080x1920, 약 15초)으로 만든다.

- 배경: 같은 카드를 크게 흐리게 깔아 위아래를 채운다
- 카드: 화면 가운데보다 조금 위(릴스 아래쪽 글자·버튼 영역을 피해서), 천천히 확대
- 장 사이는 짧게 겹쳐 넘어간다 (크로스페이드)
- 소리는 넣지 않는다. 음악은 인스타 앱에서 고른다 (앱 음악이라야 저작권 문제가 없다)

ffmpeg 는 imageio-ffmpeg 에 들어 있는 실행 파일을 쓴다 (pip install imageio-ffmpeg).
"""
import subprocess
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter

W, H = 1080, 1920
FPS = 30
CARD_W = 1000
FADE = 0.35  # 초


def _ffmpeg() -> str:
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def _background(card: Image.Image) -> Image.Image:
    scale = max(W / card.width, H / card.height)
    bg = card.resize((round(card.width * scale), round(card.height * scale)), Image.LANCZOS)
    left, top = (bg.width - W) // 2, (bg.height - H) // 2
    bg = bg.crop((left, top, left + W, top + H)).filter(ImageFilter.GaussianBlur(42))
    return ImageEnhance.Brightness(bg).enhance(0.62)


def _frame(bg: Image.Image, card: Image.Image, t: float) -> Image.Image:
    """t: 0~1 (장 안에서의 진행). 카드를 1.00 → 1.035 배로 천천히 키운다."""
    z = 1.0 + 0.035 * t
    cw = round(CARD_W * z)
    ch = round(card.height * cw / card.width)
    c = card.resize((cw, ch), Image.BILINEAR)
    f = bg.copy()
    y = (H - ch) // 2 - 70
    f.paste(c, ((W - cw) // 2, y))
    return f


# --- 릴스 전용 화면 (카드를 그대로 넣으면 글씨가 작아 2초 안에 못 읽는다) ---------------
# 릴스 화면은 아래 ~420px 에 설명·음악 표시, 오른쪽 ~140px 에 버튼이 겹친다. 글자는 그 밖에 둔다.
SAFE_BOTTOM = H - 440
SAFE_RIGHT = W - 150
PADX = 80


def _fonts():
    from src.thumbnail import FONT_BOLD, FONT_REG, _font
    return FONT_BOLD, FONT_REG, _font


def _cover_full(photo: Image.Image) -> Image.Image:
    photo = photo.convert("RGB")
    s = max(W / photo.width, H / photo.height) * 1.08  # 확대 여유
    return photo.resize((round(photo.width * s), round(photo.height * s)), Image.LANCZOS)


def _kenburns(big: Image.Image, t: float) -> Image.Image:
    """big 에서 1080x1920 을 잘라 천천히 확대해 보인다."""
    z = 1.0 + 0.07 * t
    s = min(big.width / W, big.height / H) / z  # 9:16 비율로, 사진 안에서만 자른다
    cw, ch = round(W * s), round(H * s)
    left, top = (big.width - cw) // 2, (big.height - ch) // 2
    return big.crop((left, top, left + cw, top + ch)).resize((W, H), Image.BILINEAR)


def _shade_bottom(img: Image.Image, start: float = 0.35) -> Image.Image:
    col = [int(min(205, max(0, (y / H - start) / (1 - start) * 230))) for y in range(H)]
    m = Image.new("L", (1, H))
    m.putdata(col)
    return Image.composite(Image.new("RGB", (W, H), (16, 14, 12)), img, m.resize((W, H)))


def _shade_top(img: Image.Image) -> Image.Image:
    col = [int(max(0, 170 * (1 - y / (H * 0.55)))) for y in range(H)]
    m = Image.new("L", (1, H))
    m.putdata(col)
    return Image.composite(Image.new("RGB", (W, H), (16, 14, 12)), img, m.resize((W, H)))


def _text_block(d, lines, font, x, y, gap, fill, shadow=True):
    from PIL import ImageDraw  # noqa: F401
    for ln in lines:
        if shadow:
            d.text((x + 3, y + 3), ln, font=font, fill=(0, 0, 0))
        d.text((x, y), ln, font=font, fill=fill)
        y += gap
    return y


def _overlay_photo(base: Image.Image, label: str, heading: str, sub: str, cover: bool,
                   credit: str = "") -> Image.Image:
    from PIL import ImageDraw
    from src.thumbnail import _wrap
    FB, FR, _font = _fonts()
    img = _shade_top(base) if cover else _shade_bottom(base)
    d = ImageDraw.Draw(img)
    if credit:  # 공공누리 출처 표기 (오른쪽 위, 버튼 영역 위쪽)
        fc = _font(FR, 26)
        d.text((W - 40 - d.textlength(credit, font=fc), 150), credit, font=fc, fill=(235, 235, 235))
    maxw = SAFE_RIGHT - PADX
    if cover:
        size = 104
        while True:
            f = _font(FB, size)
            ls = []
            for part in heading.split("\n"):
                ls += _wrap(d, part, f, maxw)
            if len(ls) <= 3 or size <= 72:
                break
            size -= 6
        y = 300
        if label:
            fl = _font(FB, 40)
            tw = d.textlength(label, font=fl)
            d.rounded_rectangle((PADX, y, PADX + tw + 56, y + 76), radius=38, fill=(250, 248, 244))
            d.text((PADX + 28, y + 14), label, font=fl, fill=(58, 53, 48))
            y += 130
        _text_block(d, ls, f, PADX, y, int(size * 1.25), (255, 255, 255))
    else:
        # 한 줄에 들어가면 한 줄로 (글자 한두 개만 다음 줄로 넘어가는 걸 막는다)
        size = 84
        while size > 64 and d.textlength(heading, font=_font(FB, size)) > maxw:
            size -= 4
        f = _font(FB, size if d.textlength(heading, font=_font(FB, size)) <= maxw else 84)
        ls = _wrap(d, heading, f, maxw)[:2]
        fs = _font(FR, 46)
        ss = _wrap(d, sub, fs, maxw)[:2] if sub else []
        y = SAFE_BOTTOM - len(ls) * 108 - len(ss) * 64 - 30
        y = _text_block(d, ls, f, PADX, y, 108, (255, 255, 255))
        _text_block(d, ss, fs, PADX, y + 20, 64, (236, 232, 226))
    return img


def _big_scene(big_text: str, heading: str) -> Image.Image:
    from PIL import ImageDraw
    from src.insta_cards import CREAM, GOLD, OCEAN, TEAL
    from src.thumbnail import _wrap
    FB, FR, _font = _fonts()
    img = Image.new("RGB", (W, H), CREAM)
    d = ImageDraw.Draw(img)
    size = 300
    while size > 110:
        f = _font(FB, size)
        if d.textlength(big_text, font=f) <= W - PADX * 2:
            break
        size -= 10
    fh = _font(FB, 64)
    hl = _wrap(d, heading, fh, W - PADX * 2)[:2]
    block = int(size * 1.1) + 60 + 6 + 60 + len(hl) * 84
    y = (SAFE_BOTTOM + 200 - block) // 2
    d.text(((W - d.textlength(big_text, font=f)) / 2, y), big_text, font=f, fill=TEAL)
    y += int(size * 1.1) + 60
    d.line((W / 2 - 50, y, W / 2 + 50, y), fill=GOLD, width=7)
    y += 66
    for ln in hl:
        d.text(((W - d.textlength(ln, font=fh)) / 2, y), ln, font=fh, fill=OCEAN)
        y += 84
    return img


def _naver_end(heading: str, points: list) -> Image.Image:
    """네이버 클립용 마지막 장면: '프로필 링크' 대신 네이버 검색·예약 안내."""
    from PIL import ImageDraw
    from src.insta_cards import CREAM, GOLD, LOGO, MINT, OCEAN, _logo_on_dark
    from src.thumbnail import _wrap
    FB, FR, _font = _fonts()
    img = Image.new("RGB", (W, H), OCEAN)
    d = ImageDraw.Draw(img)
    y = 330
    if LOGO.exists():
        lg = _logo_on_dark(Image.open(LOGO).convert("RGBA"), 520)
        img.paste(lg, ((W - lg.width) // 2, y), lg)
        y += lg.height + 110
    fh = _font(FB, 68)
    for ln in _wrap(d, heading, fh, W - PADX * 2)[:2]:
        d.text(((W - d.textlength(ln, font=fh)) / 2, y), ln, font=fh, fill=CREAM)
        y += 90
    y += 50
    fp = _font(FR, 46)
    widest = max((d.textlength(p, font=fp) for p in points), default=0)
    x = (W - widest - 60) / 2
    for p in points[:3]:
        d.ellipse((x, y + 18, x + 26, y + 44), fill=MINT)
        d.text((x + 56, y), p, font=fp, fill=CREAM)
        y += 82
    # 네이버 검색창 모양 + 예약 안내
    y = max(y + 90, 1180)
    fs = _font(FB, 52)
    box = (PADX + 20, y, W - PADX - 20, y + 120)
    d.rounded_rectangle(box, radius=60, outline=(3, 199, 90), width=8, fill=(255, 255, 255))
    q = "호텔아로하"
    d.text((box[0] + 60, y + 30), q, font=fs, fill=OCEAN)
    d.text((box[2] - 60 - d.textlength("검색", font=fs), y + 30), "검색", font=fs, fill=(3, 199, 90))
    fb = _font(FB, 46)
    t = "네이버 예약으로 바로 예약하세요"
    d.text(((W - d.textlength(t, font=fb)) / 2, y + 170), t, font=fb, fill=GOLD)
    return img


def _card_scene(card_path: Path) -> Image.Image:
    card = Image.open(card_path).convert("RGB")
    f = _background(card)
    c = card.resize((CARD_W, round(card.height * CARD_W / card.width)), Image.LANCZOS)
    f.paste(c, ((W - CARD_W) // 2, (H - c.height) // 2 - 120))
    return f


def make_native(slides: dict, photos: list, cards: list, out: Path, cover_label: str = "",
                credits: list = None, naver: bool = False) -> Path:
    """릴스 전용 화면으로 만든다.
    slides/photos 는 insta_cards.build 에 넣은 것과 같은 것. cards 는 build 가 만든 카드 경로(요약·예약 카드 재사용)."""
    from src.insta_cards import PHOTO_LAYOUTS
    credits = credits or [""] * len(photos)
    scenes = []  # (kind, data, seconds)
    big0 = _cover_full(photos[0])
    scenes.append(("photo", (big0, cover_label, "\n".join(slides["cover_lines"]), "", True,
                             credits[0]), 2.4))
    pi = 1
    for i, c in enumerate(slides["cards"]):
        layout = c.get("layout", "split")
        if layout in PHOTO_LAYOUTS:
            j = pi % len(photos) if len(photos) > 1 else 0
            pi += 1
            sub = c.get("body", "").split("\n")[0]
            scenes.append(("photo", (_cover_full(photos[j]), "", c["heading"], sub, False,
                                     credits[j]), 1.9))
        elif layout == "big":
            scenes.append(("still", _big_scene(c.get("big", ""), c["heading"]), 1.9))
        elif layout == "summary":
            scenes.append(("still", _card_scene(cards[i + 1]), 3.0))
    if naver:
        scenes.append(("still", _naver_end(slides.get("cta_heading", "제주 성산, 호텔아로하"),
                                           slides.get("cta_points", [])), 2.6))
    else:
        scenes.append(("still", _card_scene(cards[-1]), 2.4))

    out.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(
        [_ffmpeg(), "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-preset", "medium",
         "-movflags", "+faststart", str(out)],
        stdin=subprocess.PIPE)

    def render(scene, t):
        kind, data, _ = scene
        if kind == "photo":
            big, label, heading, sub, cover, credit = data
            return _overlay_photo(_kenburns(big, t), label, heading, sub, cover, credit)
        # 사진 없는 장면도 아주 조금 확대해 정지 화면처럼 보이지 않게
        z = 1.0 + 0.02 * t
        cw, ch = round(W / z), round(H / z)
        return data.crop(((W - cw) // 2, (H - ch) // 2, (W + cw) // 2, (H + ch) // 2)).resize((W, H))

    fade_n = int(FADE * FPS)
    for i, sc in enumerate(scenes):
        frames = int(sc[2] * FPS)
        for k in range(frames):
            t = k / max(1, frames - 1)
            f = render(sc, t)
            if i < len(scenes) - 1 and k >= frames - fade_n:
                a = (k - (frames - fade_n) + 1) / (fade_n + 1)
                f = Image.blend(f, render(scenes[i + 1], 0.0), a)
            proc.stdin.write(f.tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError("ffmpeg 영상 만들기 실패")
    return out


def make(cards: list, out: Path, durations: list = None) -> Path:
    """cards: 카드 jpg 경로 목록 (순서대로). durations: 장마다 초 (없으면 표지 2.6 / 중간 2.0 / 끝 2.4)."""
    imgs = [Image.open(p).convert("RGB") for p in cards]
    n = len(imgs)
    if not durations:
        durations = [2.6] + [2.0] * (n - 2) + [2.4] if n > 1 else [3.0]
    bgs = [_background(im) for im in imgs]
    out.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(
        [_ffmpeg(), "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-preset", "medium",
         "-movflags", "+faststart", str(out)],
        stdin=subprocess.PIPE)
    fade_n = int(FADE * FPS)
    for i in range(n):
        frames = int(durations[i] * FPS)
        for k in range(frames):
            t = k / max(1, frames - 1)
            f = _frame(bgs[i], imgs[i], t)
            # 장 끝부분에서 다음 장과 겹쳐 넘어간다
            if i < n - 1 and k >= frames - fade_n:
                a = (k - (frames - fade_n) + 1) / (fade_n + 1)
                f = Image.blend(f, _frame(bgs[i + 1], imgs[i + 1], 0.0), a)
            proc.stdin.write(f.tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError("ffmpeg 영상 만들기 실패")
    return out
