"""블로그의 초안을 확인하고 발행한다.

    python scripts/drafts.py              # 초안 목록만 보기
    python scripts/drafts.py --publish    # 초안 전부 발행
    python scripts/drafts.py --publish --id 1234567  # 특정 글만 발행
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import settings  # noqa: E402
from src.blogger import Blogger  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--publish", action="store_true", help="초안을 발행한다")
    ap.add_argument("--id", default="", help="특정 글 id 만 발행")
    args = ap.parse_args()

    env = settings.Env()
    client = Blogger(env.blog_id, env.client_id, env.client_secret,
                     env.refresh_token)

    data = client._request(
        "GET", f"/blogs/{env.blog_id}/posts",
        params={"status": "DRAFT", "fetchBodies": "false", "maxResults": 20},
    )
    drafts = data.get("items", [])
    if not drafts:
        print("초안이 없습니다.")
        return 0

    print(f"초안 {len(drafts)}건")
    for post in drafts:
        labels = ", ".join(post.get("labels", []))
        print(f"  [{post['id']}] {post['title']}")
        print(f"      라벨: {labels}")

    if not args.publish:
        print("\n발행하려면 --publish 를 붙여 다시 실행하세요.")
        return 0

    targets = [p for p in drafts if not args.id or p["id"] == args.id]
    if not targets:
        print(f"id {args.id} 인 초안을 찾지 못했습니다.")
        return 1

    # 한국어 글을 먼저 발행해 URL 순서를 자연스럽게 맞춘다
    targets.sort(key=lambda p: "English" in p.get("labels", []))
    pending = settings.pending_titles()
    for post in targets:
        result = client._request(
            "POST", f"/blogs/{env.blog_id}/posts/{post['id']}/publish")
        url = result.get("url", "")
        # 주소는 발행 순간의 제목으로 정해졌다. 이제 진짜 제목으로 되돌린다.
        real_title = pending.get(str(post["id"]))
        if real_title and real_title != result["title"]:
            result = client.patch_post(post["id"], title=real_title)
            settings.drop_pending_title(post["id"])
        print(f"[발행] {result['title']}")
        print(f"       {url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
