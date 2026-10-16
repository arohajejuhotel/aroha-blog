"""글마다 모바일용 세로 썸네일(1080x1350, 4:5)을 만든다.

디자인은 기존 블로그 썸네일(블로그/blog4.jpg)을 따른다:
사진 위에 둥근 카테고리 라벨 → 가는 흰 선 → 굵은 흰 제목 2줄.

배경 사진은 변형해도 되는 것만 쓴다.
- 한국관광공사 공공누리 제1유형 (출처 표기) 또는
- 호텔이 직접 찍은 사진
제3유형(변경 금지)과 관광사진 갤러리 사진은 글자를 얹지 않는다.

만든 파일은 저장소에 커밋·푸시하고 jsDelivr 주소로 쓴다. 커밋 해시로 고정된
jsDelivr 주소는 푸시 직후 바로 열려서, GitHub Pages 배포를 기다릴 필요가 없다.
"""

import io
import os
import re
import subprocess
import time
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
THUMB_DIR = ROOT / "assets" / "thumbs"
W, H = 1080, 1350

FONT_BOLD = [
    r"C:\Windows\Fonts\malgunbd.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothicExtraBold.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
]
FONT_REG = [
    r"C:\Windows\Fonts\malgun.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
]

GOLD = (176, 138, 62)
INK = (40, 34, 28)

LABELS = {
    "ko": {"성산여행정보": ("성산", "여행 정보"), "제주동부여행": ("제주 동부", "여행"),
           "제주전역여행": ("제주", "여행 정보"), "아로하이야기": ("호텔아로하", "이야기")},
    "en": {"성산여행정보": ("SEONGSAN", "GUIDE"), "제주동부여행": ("EAST JEJU", "GUIDE"),
           "제주전역여행": ("JEJU", "TRAVEL GUIDE"), "아로하이야기": ("HOTEL AROHA", "STORIES")},
}


def _font(paths: list, size: int):
    for p in paths:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    raise FileNotFoundError("한글 굵은 글꼴을 찾지 못했습니다 (fonts-nanum 설치 필요)")


def _cover(img: Image.Image) -> Image.Image:
    """비율을 유지한 채 1080x1350 을 꽉 채우도록 자른다."""
    img = img.convert("RGB")
    scale = max(W / img.width, H / img.height)
    img = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
    left = (img.width - W) // 2
    top = (img.height - H) // 2
    return img.crop((left, top, left + W, top + H))


def _shade(img: Image.Image) -> Image.Image:
    """글자가 어떤 사진 위에서도 읽히도록 위·아래를 어둡게 한다."""
    column = []
    for y in range(H):
        t = y / H
        # 제목이 놓이는 위쪽과 브랜드가 놓이는 맨 아래를 어둡게
        a = 150 * max(0.0, 1 - t / 0.62) + 170 * max(0.0, (t - 0.78) / 0.22)
        column.append(int(min(a, 190)))
    overlay = Image.new("L", (1, H))
    overlay.putdata(column)
    overlay = overlay.resize((W, H))
    black = Image.new("RGB", (W, H), (0, 0, 0))
    return Image.composite(black, img, overlay)


def _wrap(draw, text: str, font, max_w: int) -> list:
    words = text.split(" ")
    lines, cur = [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if draw.textlength(trial, font=font) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def make(lines: list, cat: str, lang: str, photo: Image.Image, credit: str,
         out: Path, badge: tuple = ()) -> Path:
    img = _shade(_cover(photo))
    d = ImageDraw.Draw(img)

    # 카테고리 라벨 (둥근 알약 모양, 두 가지 색)
    # 특집 주제는 badge 로 라벨을 바꾼다 (예: 전국체전 / 특집)
    a, b = badge or LABELS[lang].get(cat, LABELS[lang]["제주전역여행"])
    f_label = _font(FONT_BOLD, 40)
    pad_x, pad_y = 44, 22
    tw = d.textlength(f"{a} {b}", font=f_label)
    box = (60, 210, 60 + tw + pad_x * 2, 210 + 40 + pad_y * 2)
    pill = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(pill).rounded_rectangle(box, radius=(box[3] - box[1]) // 2,
                                           fill=(250, 248, 244, 235))
    img = Image.alpha_composite(img.convert("RGBA"), pill).convert("RGB")
    d = ImageDraw.Draw(img)
    d.text((box[0] + pad_x, box[1] + pad_y - 4), a, font=f_label, fill=INK)
    d.text((box[0] + pad_x + d.textlength(a + " ", font=f_label), box[1] + pad_y - 4),
           b, font=f_label, fill=GOLD)

    # 가는 선
    line_y = box[3] + 52
    d.line((60, line_y, W - 60, line_y), fill=(255, 255, 255), width=3)

    # 제목 (최대 3줄, 넘치면 글자를 줄인다)
    size = 96 if lang == "ko" else 86
    while True:
        f_title = _font(FONT_BOLD, size)
        wrapped = []
        for ln in lines:
            wrapped += _wrap(d, ln, f_title, W - 120)
        if len(wrapped) <= 3 or size <= 60:
            break
        size -= 6
    y = line_y + 56
    for ln in wrapped[:3]:
        # 살짝 그림자를 넣어 밝은 하늘 위에서도 읽히게 한다
        shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(shadow).text((62, y + 4), ln, font=f_title, fill=(0, 0, 0, 140))
        img = Image.alpha_composite(img.convert("RGBA"),
                                    shadow.filter(ImageFilter.GaussianBlur(6))).convert("RGB")
        d = ImageDraw.Draw(img)
        d.text((60, y), ln, font=f_title, fill=(255, 255, 255))
        y += int(size * 1.28)

    # 아래: 브랜드 + 사진 출처 (공공누리는 출처 표기가 이용 조건이다)
    brand = "HOTEL AROHA · 제주 성산" if lang == "ko" else "HOTEL AROHA · Seongsan, Jeju"
    d.text((60, H - 128), brand, font=_font(FONT_BOLD, 34), fill=(255, 255, 255))
    if credit:
        d.text((60, H - 76), credit, font=_font(FONT_REG, 26), fill=(215, 215, 215))

    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "JPEG", quality=86, optimize=True, progressive=True)
    return out


def load_photo(url_or_path: str) -> Image.Image:
    if re.match(r"https?://", url_or_path):
        resp = requests.get(url_or_path, timeout=30)
        resp.raise_for_status()
        return Image.open(io.BytesIO(resp.content))
    return Image.open(url_or_path)


def fallback_lines(title: str) -> list:
    """모델이 thumb_lines 를 주지 않았을 때 제목을 두 줄로 나눈다."""
    parts = re.split(r"\s*[—,:|\-]\s*", title, maxsplit=1)
    if len(parts) == 2 and all(parts):
        return parts
    mid = len(title) // 2
    cut = title.rfind(" ", 0, mid + 4)
    return [title[:cut], title[cut + 1:]] if cut > 0 else [title]


# --- 호스팅 ------------------------------------------------------------------

def _git(*args) -> str:
    return subprocess.run(["git", "-c", "user.name=aroha-bot",
                           "-c", "user.email=actions@github.com", *args],
                          cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


def _repo_slug() -> str:
    slug = os.environ.get("GITHUB_REPOSITORY")
    if slug:
        return slug
    remote = _git("remote", "get-url", "origin")
    m = re.search(r"github\.com[:/](.+?)(?:\.git)?$", remote)
    return m.group(1)


def publish(path: Path) -> str:
    """썸네일을 커밋·푸시하고, 커밋 해시로 고정된 jsDelivr 주소를 돌려준다."""
    rel = path.relative_to(ROOT).as_posix()
    _git("add", rel)
    _git("commit", "-m", f"chore: thumbnail {path.stem}")
    for attempt in range(3):
        try:
            _git("push", "origin", "HEAD")
            break
        except subprocess.CalledProcessError:
            _git("pull", "--rebase", "origin", "main")
    else:
        raise RuntimeError("썸네일 푸시 실패")
    sha = _git("rev-parse", "HEAD")
    url = f"https://cdn.jsdelivr.net/gh/{_repo_slug()}@{sha}/{rel}"
    # jsDelivr 가 파일을 가져올 때까지 잠깐 기다린다
    for _ in range(12):
        try:
            if requests.head(url, timeout=15).status_code == 200:
                return url
        except requests.RequestException:
            pass
        time.sleep(5)
    print(f"[warn] 썸네일 주소가 아직 열리지 않습니다 (곧 열림): {url}")
    return url
