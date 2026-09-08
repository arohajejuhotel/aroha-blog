"""
02_사진 폴더의 원본 사진을 블로그용으로 리사이즈/압축하고
태그가 붙은 manifest.json 을 만든다.

한 번만 돌리면 되고, 사진을 추가한 뒤에 다시 돌려도 된다(증분 처리).

    python scripts/prepare_images.py --source "G:/내 드라이브/08.AROHA/02_사진"
"""

import argparse
import hashlib
import io
import json
import os
import re
import sys
import unicodedata
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "assets" / "img"
MANIFEST = ROOT / "assets" / "manifest.json"

MAX_WIDTH = 1400
JPEG_QUALITY = 82

# 원본 폴더 -> 태그
FOLDER_TAGS = {
    "01_외관": ["exterior", "hotel"],
    "02_객실_스탠다드": ["room", "standard"],
    "03_객실_스탠다드오션뷰": ["room", "standard", "oceanview"],
    "04_객실_디럭스": ["room", "deluxe", "oceanview"],
    "05_객실_패밀리": ["room", "family", "kitchen"],
    "06_객실_이코노미트윈": ["room", "economy"],
    "07_로비_프런트": ["lobby", "hotel"],
    "08_레스토랑_조식": ["breakfast", "hotel"],
    "09_편의시설": ["amenity", "hotel"],
    "10_주변환경": ["surroundings"],
}

# 파일명 키워드 -> 추가 태그 (주변환경 폴더 세분화용)
FILENAME_TAGS = [
    (r"성산일출봉|seongsan|sunrise", ["sunrise-peak"]),
    (r"우도|udo", ["udo"]),
    (r"섭지코지|seopji", ["seopjikoji"]),
    (r"광치기|gwangchigi", ["gwangchigi"]),
    (r"야간|night", ["night"]),
    (r"gs25|store", ["convenience-store"]),
]

# 태그 -> 이미지 alt 문구 (한/영)
ALT_TEXT = {
    "exterior": ("호텔아로하 외관 — 제주 성산 성산일출봉 근처 숙소",
                 "Hotel Aroha exterior in Seongsan, Jeju"),
    "night": ("호텔아로하 야간 외관", "Hotel Aroha at night"),
    "deluxe": ("호텔아로하 디럭스더블 객실 — 바다 전망",
               "Hotel Aroha Deluxe Double room with ocean view"),
    "standard": ("호텔아로하 스탠다드 트윈 객실",
                 "Hotel Aroha Standard Twin room"),
    "oceanview": ("호텔아로하 객실에서 보이는 바다 전망",
                  "Ocean view from a Hotel Aroha guest room"),
    "family": ("호텔아로하 패밀리 트윈 — 침실과 거실이 분리된 가족 객실",
               "Hotel Aroha Family Twin with a separate living room"),
    "kitchen": ("호텔아로하 패밀리 트윈 주방", "Full kitchen in the Hotel Aroha Family Twin"),
    "economy": ("호텔아로하 이코노미 트윈 객실", "Hotel Aroha Economy Twin room"),
    "lobby": ("호텔아로하 로비와 프런트, 로비 도서관",
              "Hotel Aroha lobby, front desk and library"),
    "breakfast": ("호텔아로하 조식", "Breakfast at Hotel Aroha"),
    "amenity": ("호텔아로하 편의시설 — 1층 GS25 편의점",
                "Hotel Aroha amenities including the GS25 store downstairs"),
    "convenience-store": ("호텔아로하 1층 GS25 편의점",
                          "The GS25 convenience store on the ground floor of Hotel Aroha"),
    "sunrise-peak": ("성산일출봉 — 호텔아로하에서 도보 5~10분",
                     "Seongsan Ilchulbong, a 5-10 minute walk from Hotel Aroha"),
    "udo": ("우도 — 성산 페리 터미널에서 배로 이동",
            "Udo Island, reached by ferry from Seongsan"),
    "seopjikoji": ("섭지코지 — 성산에서 차로 8분",
                   "Seopjikoji, 8 minutes by car from Seongsan"),
    "gwangchigi": ("광치기해변 — 호텔아로하에서 도보 5분",
                   "Gwangchigi Beach, a 5 minute walk from Hotel Aroha"),
    "surroundings": ("제주 성산 주변 풍경", "Around Seongsan, Jeju"),
    "room": ("호텔아로하 객실", "A guest room at Hotel Aroha"),
    "hotel": ("호텔아로하", "Hotel Aroha"),
}

VALID_EXT = {".jpg", ".jpeg", ".png", ".JPG", ".JPEG", ".PNG"}


def slugify(folder: str, name: str, digest: str) -> str:
    base = FOLDER_TAGS.get(folder, ["photo"])[0]
    stem = unicodedata.normalize("NFKD", Path(name).stem)
    stem = re.sub(r"[^a-zA-Z0-9]+", "-", stem).strip("-").lower()
    stem = re.sub(r"-+", "-", stem)[:28]
    return f"{base}-{stem}-{digest}" if stem else f"{base}-{digest}"


def tags_for(folder: str, filename: str) -> list:
    tags = list(FOLDER_TAGS.get(folder, ["misc"]))
    low = filename.lower()
    for pattern, extra in FILENAME_TAGS:
        if re.search(pattern, low):
            tags.extend(t for t in extra if t not in tags)
    return tags


def alt_for(tags: list) -> tuple:
    for t in tags:
        if t in ALT_TEXT and t not in ("hotel", "room", "surroundings"):
            return ALT_TEXT[t]
    for t in tags:
        if t in ALT_TEXT:
            return ALT_TEXT[t]
    return ("호텔아로하 제주 성산", "Hotel Aroha, Seongsan, Jeju")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True, help="02_사진 폴더 경로")
    ap.add_argument("--force", action="store_true", help="이미 처리한 파일도 다시 처리")
    args = ap.parse_args()

    src = Path(args.source)
    if not src.is_dir():
        print(f"[error] source not found: {src}", file=sys.stderr)
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    entries = []
    skipped = 0

    for folder in sorted(os.listdir(src)):
        fdir = src / folder
        if not fdir.is_dir():
            continue
        for name in sorted(os.listdir(fdir)):
            path = fdir / name
            if path.suffix not in VALID_EXT or not path.is_file():
                continue
            digest = hashlib.sha1(f"{folder}/{name}".encode("utf-8")).hexdigest()[:8]
            slug = slugify(folder, name, digest)
            out_path = OUT_DIR / f"{slug}.jpg"

            if out_path.exists() and not args.force:
                skipped += 1
            else:
                try:
                    with Image.open(path) as im:
                        im = ImageOps.exif_transpose(im).convert("RGB")
                        if im.width > MAX_WIDTH:
                            h = round(im.height * MAX_WIDTH / im.width)
                            im = im.resize((MAX_WIDTH, h), Image.LANCZOS)
                        im.save(out_path, "JPEG", quality=JPEG_QUALITY, optimize=True,
                                progressive=True)
                except Exception as exc:  # noqa: BLE001
                    print(f"[skip] {path}: {exc}", file=sys.stderr)
                    continue

            tags = tags_for(folder, name)
            alt_ko, alt_en = alt_for(tags)
            with Image.open(out_path) as im:
                w, h = im.size
            entries.append({
                "file": f"{slug}.jpg",
                "tags": tags,
                "alt_ko": alt_ko,
                "alt_en": alt_en,
                "width": w,
                "height": h,
                "orientation": "landscape" if w >= h else "portrait",
                "source": f"{folder}/{name}",
            })

    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(
        json.dumps({"images": entries}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    tag_count = {}
    for e in entries:
        for t in e["tags"]:
            tag_count[t] = tag_count.get(t, 0) + 1
    print(f"processed {len(entries)} images ({skipped} already existed)")
    print("tags:", json.dumps(tag_count, ensure_ascii=False, sort_keys=True))
    print(f"manifest -> {MANIFEST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
