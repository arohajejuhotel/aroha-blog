"""구글 비즈니스 프로필(Google Business Profile) 업로드용 사진 세트를 만든다.

02_사진 원본에서 카테고리별로 골라 규격에 맞게 변환하고,
업로드 순서대로 번호를 붙여 폴더로 정리한다.

    python scripts/gbp_photos.py

구글 규격
 - 형식 JPG, 용량 10KB~5MB
 - 최소 720x720, 권장 1200px 이상
 - 로고 1:1 정사각, 표지 16:9
"""

import argparse
import shutil
import sys
from pathlib import Path

from PIL import Image, ImageOps

SRC_PHOTOS = Path(r"G:\내 드라이브\08.AROHA\02_사진")
SRC_LOGO = Path(r"G:\내 드라이브\08.AROHA\05_로고")
OUT = Path(r"G:\내 드라이브\08.AROHA\11_구글비즈니스프로필")

LONG_EDGE = 1600
QUALITY = 88
MIN_SHORT_EDGE = 720

# 구글 비즈니스 프로필 카테고리 -> (원본 폴더, 고를 파일들)
# 파일명을 직접 지정해 품질이 좋은 컷만 쓴다.
PLAN = {
    "01_외부": [
        ("01_외관", "HOTELOUT_01.jpg"),
        ("01_외관", "HOTELOUT_02.jpg"),
        ("01_외관", "HOTELOUT_03.jpg"),
        ("01_외관", "HOTELOUT_04.jpg"),
        ("01_외관", "외관 (야간1).jpg"),
        ("01_외관", "외관 05.jpg"),
    ],
    "02_내부": [
        ("07_로비_프런트", "RECEP_01.jpg"),
        ("07_로비_프런트", "RECEP_011.jpg"),
        ("07_로비_프런트", "로비 01.jpg"),
        ("07_로비_프런트", "로비 02.jpg"),
    ],
    "03_객실": [
        ("04_객실_디럭스", "DELUXE_01.JPG"),
        ("04_객실_디럭스", "DELUXE_02.JPG"),
        ("04_객실_디럭스", "DELUXE_04.JPG"),
        ("03_객실_스탠다드오션뷰", "DSC09406.jpg"),
        ("03_객실_스탠다드오션뷰", "DSC09407.jpg"),
        ("03_객실_스탠다드오션뷰", "STANOCEAN_01.JPG"),
        ("02_객실_스탠다드", "스탠다드트윈_작가촬영_1.JPG"),
        ("02_객실_스탠다드", "스탠다드트윈_작가촬영_3.JPG"),
        ("05_객실_패밀리", "패밀리트윈(마을전망) (1).JPG"),
        ("05_객실_패밀리", "패밀리트윈(마을전망) (5).JPG"),
        ("05_객실_패밀리", "패밀리트윈(마을전망) (9).JPG"),
        ("06_객실_이코노미트윈", "ECONOMY_01.JPG"),
    ],
    "04_음식및음료": [
        ("08_레스토랑_조식", "BREAKFAST_01.JPG"),
        ("08_레스토랑_조식", "BREAKFAST_02.JPG"),
        ("08_레스토랑_조식", "RES_01.jpg"),
        ("08_레스토랑_조식", "RES_02.jpg"),
    ],
    # GS25.jpg 는 960x458 로 권장 해상도에 못 미쳐 제외했다.
    # 편의점 사진이 필요하면 현장에서 다시 찍어 추가하는 편이 낫다.
    "05_편의시설": [
        ("09_편의시설", "편의시설 01.jpg"),
        ("09_편의시설", "IMG_5448.JPG"),
        ("09_편의시설", "IMG_5451.JPG"),
        ("09_편의시설", "IMG_5580.JPG"),
    ],
    "06_주변": [
        ("10_주변환경", "성산일출봉.JPG"),
        ("10_주변환경", "IMG_6044.JPG"),
        ("10_주변환경", "IMG_6063.JPG"),
        ("10_주변환경", "IMG_5872.JPG"),
        ("10_주변환경", "IMG_6144.JPG"),
        ("10_주변환경", "IMG_5878.JPG"),
    ],
}

COVER = ("10_주변환경", "IMG_5878.JPG")   # 16:9 표지
LOGO = "aroha profile 1080.png"           # 1:1 로고


def load(path: Path) -> Image.Image:
    return ImageOps.exif_transpose(Image.open(path)).convert("RGB")


def fit(im: Image.Image, long_edge: int = LONG_EDGE) -> Image.Image:
    if max(im.size) > long_edge:
        scale = long_edge / max(im.size)
        im = im.resize((round(im.width * scale), round(im.height * scale)),
                       Image.LANCZOS)
    return im


def crop_ratio(im: Image.Image, ratio: float) -> Image.Image:
    """가운데를 기준으로 지정한 가로세로비로 잘라낸다."""
    w, h = im.size
    if w / h > ratio:
        new_w = round(h * ratio)
        left = (w - new_w) // 2
        return im.crop((left, 0, left + new_w, h))
    new_h = round(w / ratio)
    top = (h - new_h) // 2
    return im.crop((0, top, w, top + new_h))


def save(im: Image.Image, path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path, "JPEG", quality=QUALITY, optimize=True, progressive=True)
    return path.stat().st_size


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--clean", action="store_true", help="기존 출력 폴더를 지우고 새로 만든다")
    args = ap.parse_args()

    if not SRC_PHOTOS.is_dir():
        print(f"[error] 원본 폴더를 찾을 수 없습니다: {SRC_PHOTOS}", file=sys.stderr)
        return 1
    if args.clean and OUT.exists():
        shutil.rmtree(OUT)

    total, skipped, too_small = 0, [], []

    for category, items in PLAN.items():
        for n, (folder, name) in enumerate(items, start=1):
            src = SRC_PHOTOS / folder / name
            if not src.exists():
                skipped.append(f"{folder}/{name}")
                continue
            im = fit(load(src))
            if min(im.size) < MIN_SHORT_EDGE:
                too_small.append(f"{folder}/{name} ({im.width}x{im.height})")
            out = OUT / category / f"{category}_{n:02d}.jpg"
            size = save(im, out)
            total += 1
            print(f"  {category}/{out.name}  {im.width}x{im.height}  {size // 1024}KB")

    # 표지 (16:9)
    cover_src = SRC_PHOTOS / COVER[0] / COVER[1]
    if cover_src.exists():
        cover = fit(crop_ratio(load(cover_src), 16 / 9), 1920)
        save(cover, OUT / "00_표지" / "표지_16x9.jpg")
        print(f"  00_표지/표지_16x9.jpg  {cover.width}x{cover.height}")
        total += 1

    # 로고 (1:1)
    logo_src = SRC_LOGO / LOGO
    if logo_src.exists():
        logo = fit(crop_ratio(load(logo_src), 1.0), 1080)
        save(logo, OUT / "00_표지" / "로고_1x1.jpg")
        print(f"  00_표지/로고_1x1.jpg  {logo.width}x{logo.height}")
        total += 1
    else:
        skipped.append(str(logo_src))

    print(f"\n총 {total}장 생성 -> {OUT}")
    if skipped:
        print(f"[주의] 원본을 찾지 못해 건너뜀 {len(skipped)}건:")
        for s in skipped:
            print(f"   - {s}")
    if too_small:
        print(f"[주의] 권장 해상도({MIN_SHORT_EDGE}px)보다 작음:")
        for s in too_small:
            print(f"   - {s}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
