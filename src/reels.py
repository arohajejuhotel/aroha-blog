# -*- coding: utf-8 -*-
"""훅 릴스 영상 만들기 (2026-10-23, 오조포구·해녀공연 훅 릴스를 자동화로 옮김).

화면: 사진 전체 화면 + 장면마다 다른 카메라 움직임 + 0.6초 페이드 (v4, 2026-10-19 승인)
글자: 첫 장면 큰 장소명, 나머지는 왼쪽 위 작은 라벨 (Pretendard).
      하단 자막은 고운바탕 명조 62pt, 강조어만 크림색 (2026-10-23 사용자 선택: "B인데 조금만 작게").
소리: 내레이션 없음 (2026-10-23 사용자: "나래이션 없이 음원으로"). 음악은 인스타·네이버 앱에서 고르는 게
      기본이다 (앱 음원이라야 저작권 걱정이 없고 노출에도 유리). assets/reels/music/ 에 무료 음원(mp3)을
      넣어 두면 날짜마다 돌려 가며 깐다. 비어 있으면 무음 트랙.
장면 길이는 자막 길이로 정한다 (읽을 시간).
끝: 호텔 영상 → 예약 안내 화면. 인스타용(전화·홈페이지)과 네이버 클립용(네이버 검색창) 두 가지.

원본 스크립트: 08.AROHA/인스타그램/릴스/수동제작/reel_hook.py, sample_reel_v4.py, style_aroha.py
"""
import re
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets" / "reels"
FONTS = ASSETS / "fonts"
XB, SB, MD = (str(FONTS / f"Pretendard-{w}.otf") for w in ("ExtraBold", "SemiBold", "Medium"))
SUB = str(FONTS / "GowunBatang-Bold.ttf")
MUSIC = ASSETS / "music"
EXTERIOR = ASSETS / "exterior.jpg"  # 1층 GS25 가 들어온 지금 외관 (예전 해담식당 간판 사진은 쓰지 않는다)
ROOM_A, ROOM_B = ASSETS / "room_a.mp4", ASSETS / "room_b.mp4"  # 오션뷰 객실 영상 (세로로 잘라 둔 4초)

W, H, FPS, FADE = 1080, 1920, 30, 0.6
MIN_DUR, MAX_DUR, END_DUR = 2.4, 3.6, 3.2
WHITE, SOFT, YELLOW, GOLD = (255, 255, 255), (238, 236, 230), (255, 214, 90), (203, 162, 88)
CREAM = (246, 226, 180)
NAVER_GREEN = (3, 199, 90)

# 카메라 움직임: (시작 중심x, 중심y, 확대) → (끝)
MOVES = [
    ((0.50, 0.50, 1.00), (0.52, 0.48, 1.12)),  # 다가가기
    ((0.30, 0.50, 1.00), (0.62, 0.50, 1.00)),  # 오른쪽으로
    ((0.50, 0.50, 1.12), (0.50, 0.50, 1.00)),  # 물러나기
    ((0.68, 0.50, 1.00), (0.36, 0.50, 1.00)),  # 왼쪽으로
    ((0.40, 0.55, 1.00), (0.58, 0.45, 1.12)),  # 대각선으로 다가가기
    ((0.35, 0.50, 1.05), (0.65, 0.50, 1.05)),  # 오른쪽으로
    ((0.50, 0.52, 1.00), (0.50, 0.46, 1.12)),  # 위로 다가가기
]


def _ffmpeg() -> str:
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


FF = _ffmpeg()


def run(args):
    subprocess.run([FF, "-nostdin", "-hide_banner", "-loglevel", "error", "-y", *args], check=True,
                   stdin=subprocess.DEVNULL)


def duration(path: Path) -> float:
    out = subprocess.run([FF, "-hide_banner", "-i", str(path)], capture_output=True, text=True).stderr
    h, m, s = re.search(r"Duration: (\d+):(\d+):([\d.]+)", out).groups()
    return int(h) * 3600 + int(m) * 60 + float(s)


def read_time(sub: str) -> float:
    """자막을 편하게 읽을 시간 (한 글자 약 0.11초 + 여유)."""
    return min(max(1.2 + len(sub.replace("\n", "")) * 0.11, MIN_DUR), MAX_DUR)


# ---------- 글자 ----------
def F(path, size):
    return ImageFont.truetype(path, size)


def shadow(img, xy, text, f, fill, blur=10, alpha=170):
    """테두리 없이 부드러운 그림자 (굵은 검은 테두리는 AI 티가 나서 쓰지 않는다)."""
    sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).text((xy[0] + 2, xy[1] + 4), text, font=f, fill=(0, 0, 0, alpha))
    img.alpha_composite(sh.filter(ImageFilter.GaussianBlur(blur)))
    ImageDraw.Draw(img).text(xy, text, font=f, fill=fill)


def shade(img, y0, y1, peak, mid=False):
    d = ImageDraw.Draw(img)
    for y in range(y0, y1):
        r = (y - y0) / (y1 - y0)
        a = peak * (1 - abs(r - 0.5) * 2) if mid else peak * (1 - r)
        d.line([(0, y), (W, y)], fill=(0, 0, 0, int(a)))


def intro_title(kicker: str, name: str) -> Image.Image:
    """첫 장면 제목: 머리말(작게) + 장소명(아주 크게) + 노란 선."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    shade(img, 0, 900, 150)
    shadow(img, (86, 250), kicker, F(MD, 46), SOFT, blur=8, alpha=160)
    size = 168
    while ImageDraw.Draw(img).textlength(name, font=F(XB, size)) > W - 172 and size > 100:
        size -= 6
    shadow(img, (80, 318), name, F(XB, size), WHITE, blur=12, alpha=180)
    ImageDraw.Draw(img).rectangle([88, 318 + int(size * 1.28), 88 + 96, 318 + int(size * 1.28) + 8], fill=YELLOW)
    return img


def label(kicker: str, name: str) -> Image.Image:
    """나머지 장면: 왼쪽 위 작은 한 줄 라벨."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    shade(img, 0, 420, 120)
    d = ImageDraw.Draw(img)
    d.ellipse([86, 186, 104, 204], fill=YELLOW)
    f1, f2 = F(MD, 38), F(SB, 38)
    shadow(img, (122, 172), kicker, f1, SOFT, blur=6, alpha=150)
    shadow(img, (122 + d.textlength(kicker, font=f1), 172), "  ·  ", f1, SOFT, blur=6, alpha=150)
    shadow(img, (122 + d.textlength(kicker + "  ·  ", font=f1), 172), name, f2, WHITE, blur=6, alpha=150)
    return img


def subtitle(text: str, em: str = "") -> Image.Image:
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    shade(img, 1040, 1520, 140, mid=True)
    d = ImageDraw.Draw(img)
    lines = text.split("\n")
    size = 62
    while max(d.textlength(x, font=F(SUB, size)) for x in lines) > W - 160 and size > 48:
        size -= 2
    f, gap = F(SUB, size), int(size * 1.5)
    y0 = 1230 - (len(lines) - 1) * gap // 2
    for k, line in enumerate(lines):
        segs = [(line, WHITE)]
        if em and em in line:
            a, b = line.split(em, 1)
            segs = [(a, WHITE), (em, CREAM), (b, WHITE)]
        x = (W - sum(d.textlength(s, font=f) for s, _ in segs)) / 2
        for s, c in segs:
            shadow(img, (x, y0 + k * gap), s, f, c, blur=9, alpha=190)
            x += d.textlength(s, font=f)
    return img


# ---------- 장면 ----------
def _ease(t: float) -> float:
    return t * t * (3 - 2 * t)


def _encoder(out: Path):
    return subprocess.Popen([FF, "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo",
                             "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                             "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                             "-pix_fmt", "yuv420p", "-r", str(FPS), str(out)], stdin=subprocess.PIPE)


def photo_seg(src: Image.Image, dur: float, move, title: Image.Image, sub: Image.Image, out: Path,
              first_frame: Path = None):
    src = src.convert("RGB")
    up = max((H * 1.15) / src.height, (W * 1.15) / src.width)
    big = src.resize((round(src.width * up), round(src.height * up)), Image.LANCZOS)
    big = big.filter(ImageFilter.UnsharpMask(radius=2.2, percent=80, threshold=2))
    big = ImageEnhance.Color(big).enhance(1.10)
    bh0 = min(big.height, big.width * H / W)
    bw0 = bh0 * W / H
    n = round(dur * FPS)
    (x0, y0, z0), (x1, y1, z1) = move
    p = _encoder(out)
    for i in range(n):
        e = _ease(i / max(n - 1, 1))
        cx, cy, z = x0 + (x1 - x0) * e, y0 + (y1 - y0) * e, z0 + (z1 - z0) * e
        bw, bh = bw0 / z, bh0 / z
        left = min(max(cx * big.width - bw / 2, 0), big.width - bw)
        top = min(max(cy * big.height - bh / 2, 0), big.height - bh)
        f = big.resize((W, H), Image.BICUBIC, box=(left, top, left + bw, top + bh)).convert("RGBA")
        f.alpha_composite(title)
        f.alpha_composite(sub)
        if i == 0 and first_frame:
            f.convert("RGB").save(first_frame, quality=92)
        p.stdin.write(f.convert("RGB").tobytes())
    p.stdin.close()
    p.wait()


def video_seg(src: Path, ss: float, dur: float, title_png: Path, sub_png: Path, out: Path):
    vf = (f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
          f"fps={FPS},setsar=1,eq=saturation=1.10:contrast=1.03[v];"
          f"[v][1:v]overlay=0:0[a];[a][2:v]overlay=0:0,format=yuv420p")
    # 영상이 내레이션보다 짧으면 마지막 장면을 붙잡아 늘린다
    run(["-ss", str(ss), "-i", str(src), "-i", str(title_png), "-i", str(sub_png),
         "-filter_complex", vf + f",tpad=stop_mode=clone:stop_duration={dur:.3f}",
         "-t", f"{dur:.3f}", "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
         "-r", str(FPS), str(out)])


def _center(d, y, text, font, fill):
    d.text(((W - d.textlength(text, font=font)) / 2, y), text, font=font, fill=fill)


def end_card(tmp: Path, sub_line: str, naver: bool) -> Image.Image:
    """예약 안내 화면: 객실 영상 마지막 장면을 흐리게 깔고 정보만 크게."""
    still = tmp / "room_last.png"
    if not still.exists():
        run(["-sseof", "-0.2", "-i", str(ROOM_A), "-frames:v", "1", str(still)])
    img = Image.open(still).convert("RGB").resize((W, H)).filter(ImageFilter.GaussianBlur(28))
    img = ImageEnhance.Brightness(img).enhance(0.42).convert("RGBA")
    d = ImageDraw.Draw(img)
    y = 430
    _center(d, y, "예약 안내", F(XB, 46), GOLD)
    y += 90
    _center(d, y, "호텔아로하", F(XB, 104), WHITE)
    y += 150
    _center(d, y, sub_line, F(MD, 42), (225, 225, 225))
    y += 120
    d.line([(W / 2 - 60, y), (W / 2 + 60, y)], fill=GOLD, width=4)
    y += 70
    fl, fv = F(MD, 40), F(XB, 50)
    if naver:
        fs = F(XB, 56)
        bx0, bx1 = 110, W - 110
        d.rounded_rectangle((bx0, y, bx1, y + 124), radius=62, fill=WHITE, outline=NAVER_GREEN, width=8)
        d.text((bx0 + 60, y + 28), "호텔아로하", font=fs, fill=(30, 30, 30))
        d.text((bx1 - 60 - d.textlength("검색", font=fs), y + 28), "검색", font=fs, fill=NAVER_GREEN)
        y += 170
        _center(d, y, "네이버 예약으로 바로 예약하세요", F(XB, 48), GOLD)
        y += 120
        _center(d, y, "전화", fl, GOLD)
        _center(d, y + 54, "064-782-3100", fv, WHITE)
        y += 180
    else:
        for k, v in [("전화", "064-782-3100"), ("홈페이지", "www.hotelaroha.com"),
                     ("네이버", "'호텔아로하' 검색 → 네이버 예약")]:
            _center(d, y, k, fl, GOLD)
            _center(d, y + 54, v, fv, WHITE)
            y += 150
        y += 30
    box_w = 860
    box = Image.new("RGBA", img.size, (0, 0, 0, 0))  # 반투명은 따로 그려 겹쳐야 섞인다
    ImageDraw.Draw(box).rounded_rectangle(((W - box_w) / 2, y, (W + box_w) / 2, y + 150), radius=24,
                                          fill=(255, 255, 255, 34), outline=GOLD, width=3)
    img.alpha_composite(box)
    d = ImageDraw.Draw(img)
    fb = F(XB, 40)
    _center(d, y + 26, "전화·홈페이지로 직접 예약하면", fb, WHITE)
    _center(d, y + 80, "얼리 체크인 12:00 · 레이트 체크아웃 13:00", fb, GOLD)
    return img


def end_segment(card: Image.Image, out: Path):
    card = card.convert("RGB")
    n = round(END_DUR * FPS)
    p = _encoder(out)
    for i in range(n):  # 아주 살짝 다가가기
        z = 1.0 + 0.03 * i / (n - 1)
        bw, bh = W / z, H / z
        lft, top = (W - bw) / 2, (H - bh) / 2
        p.stdin.write(card.resize((W, H), Image.BICUBIC, box=(lft, top, lft + bw, top + bh)).tobytes())
    p.stdin.close()
    p.wait()


def _audio(total: float, tmp: Path, seed: str) -> Path:
    """배경 음원 (music 폴더에서 날짜마다 돌려 가며, 끝 1.5초 페이드아웃). 없으면 무음."""
    tracks = sorted(p for p in MUSIC.glob("*") if p.suffix.lower() in (".mp3", ".m4a", ".wav"))
    out = tmp / f"a_{seed}.wav"
    if tracks:
        track = tracks[sum(map(ord, seed)) % len(tracks)]
        run(["-i", str(track), "-t", f"{total:.3f}", "-af",
             f"afade=t=in:d=0.5,afade=t=out:st={max(total - 1.5, 0):.3f}:d=1.5,volume=0.8",
             "-ar", "44100", "-ac", "2", str(out)])
        print(f"[info] 배경 음원: {track.name}")
    else:
        run(["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", f"{total:.3f}", str(out)])
    return out


def _compose(parts: list, durs: list, audio: Path, tmp: Path, out: Path):
    """장면 사이를 겹쳐 부드럽게 (xfade)."""
    args = []
    for p in parts:
        args += ["-i", str(p)]
    chain, prev, acc = [], "[0:v]", durs[0]
    for k in range(1, len(parts)):
        lab = f"[x{k}]"
        chain.append(f"{prev}[{k}:v]xfade=transition=fade:duration={FADE}:offset={acc - FADE * k:.3f}{lab}")
        prev, acc = lab, acc + durs[k]
    video = tmp / f"video_{out.stem}.mp4"
    run([*args, "-filter_complex", ";".join(chain), "-map", prev, "-c:v", "libx264", "-preset", "medium",
         "-crf", "18", "-pix_fmt", "yuv420p", "-r", str(FPS), str(video)])
    out.parent.mkdir(parents=True, exist_ok=True)
    run(["-i", str(video), "-i", str(audio), "-map", "0:v", "-map", "1:a", "-c:v", "copy",
         "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", str(out)])


def build(job: dict, tmp: Path, out_insta: Path, out_naver: Path, cover: Path, seed: str = "") -> float:
    """job = {kicker, name, sub_line, scenes: [{src, sub, em}]}.
    src 는 PIL 이미지(사진) 또는 (영상 경로, 시작초). 장면은 한 번만 그리고 끝 화면만 바꿔 두 편을 만든다."""
    parts, durs = [], []
    for i, sc in enumerate(job["scenes"]):
        dur = read_time(sc["sub"])
        sub_img = subtitle(sc["sub"], sc.get("em", ""))
        title = intro_title(job["kicker"], job["name"]) if i == 0 else label(job["kicker"], job["name"])
        seg = tmp / f"p{i}.mp4"
        if isinstance(sc["src"], tuple):
            title.save(tmp / f"title{i}.png")
            sub_img.save(tmp / f"sub{i}.png")
            video_seg(sc["src"][0], sc["src"][1], dur, tmp / f"title{i}.png", tmp / f"sub{i}.png", seg)
        else:
            photo_seg(sc["src"], dur, MOVES[i % len(MOVES)], title, sub_img, seg,
                      first_frame=cover if i == 0 else None)
        parts.append(seg)
        durs.append(dur)

    total = sum(durs) + END_DUR - FADE * len(durs)
    audio = _audio(total, tmp, seed or job["name"])
    for naver, out in ((False, out_insta), (True, out_naver)):
        end = tmp / f"end_{'naver' if naver else 'insta'}.mp4"
        end_segment(end_card(tmp, job["sub_line"], naver), end)
        _compose(parts + [end], durs + [END_DUR], audio, tmp, out)
    return duration(out_insta)
