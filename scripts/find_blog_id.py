"""블로그 주소로 blogId 를 조회한다.

인증 없이 API 키만 필요:
 Google Cloud Console > 사용자 인증 정보 > API 키 생성 (Blogger API 사용 설정 후)

    python scripts/find_blog_id.py --url https://hotelaroha.blogspot.com --api-key XXX

인증된 방식으로 확인하고 싶으면 (환경 변수 설정 후):

    python scripts/find_blog_id.py --whoami
"""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests  # noqa: E402

from src.blogger import Blogger, blog_id_from_url  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url")
    ap.add_argument("--api-key")
    ap.add_argument("--whoami", action="store_true",
                    help="환경 변수의 OAuth 정보로 내 블로그 목록 조회")
    args = ap.parse_args()

    if args.whoami:
        client = Blogger(
            os.environ.get("BLOGGER_BLOG_ID", "0"),
            os.environ["GOOGLE_CLIENT_ID"],
            os.environ["GOOGLE_CLIENT_SECRET"],
            os.environ["GOOGLE_REFRESH_TOKEN"],
        )
        resp = requests.get(
            "https://www.googleapis.com/blogger/v3/users/self/blogs",
            headers={"Authorization": f"Bearer {client._access_token()}"},
            timeout=30)
        resp.raise_for_status()
        for blog in resp.json().get("items", []):
            print(f"{blog['id']}  {blog['name']}  {blog['url']}")
        return 0

    if not (args.url and args.api_key):
        ap.error("--url 과 --api-key 를 함께 주거나 --whoami 를 쓰세요.")
    print(blog_id_from_url(args.url, args.api_key))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
