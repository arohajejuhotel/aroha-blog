"""Blogger 의 공개 글 전부에 '관련 글' 링크 블록을 넣거나 새로 고친다.

    python scripts/add_related_links.py --dry-run   # 무엇이 바뀔지 보기만
    python scripts/add_related_links.py             # 실제로 고치기
    python scripts/add_related_links.py --lang en   # 영어 글만

같은 언어 글끼리만 잇는다. 다시 돌려도 블록 자리만 바뀐다 (src/related.py).
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import related, settings  # noqa: E402
from src.blogger import Blogger  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--lang", choices=["ko", "en", "both"], default="both")
    args = ap.parse_args()

    e = settings.env
    client = Blogger(e("BLOGGER_BLOG_ID", required=True), e("GOOGLE_CLIENT_ID", required=True),
                     e("GOOGLE_CLIENT_SECRET", required=True), e("GOOGLE_REFRESH_TOKEN", required=True))
    posts = related.live_posts(client)
    targets = [p for p in posts if args.lang == "both" or related.lang_of(p) == args.lang]
    print(f"공개 글 {len(posts)}편 중 대상 {len(targets)}편")
    if args.dry_run:
        for p in targets[:3]:
            print(f"\n{p['title']}")
            for r in related.pick(p, posts):
                print(f"  -> {r['title']}")
    n = related.refresh(client, [p["id"] for p in targets], posts, dry_run=args.dry_run)
    print(f"\n{'바뀔' if args.dry_run else '바뀐'} 글: {n}편")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
