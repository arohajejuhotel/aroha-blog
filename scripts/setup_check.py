"""세팅이 제대로 됐는지 점검한다. .env 를 읽어서 하나씩 확인만 하고, 아무것도 발행하지 않는다.

    python scripts/setup_check.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env"

PLACEHOLDERS = ("sk-ant-...", "1234567890123456789", "....apps.googleusercontent.com",
                "GOCSPX-...", "1//0e...", "<github-id>", "여기에")


def load_env() -> dict:
    if not ENV_FILE.exists():
        raise SystemExit(f".env 파일이 없습니다: {ENV_FILE}")
    env = {}
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def check_filled(env: dict) -> list:
    required = ["ANTHROPIC_API_KEY", "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET",
                "GOOGLE_REFRESH_TOKEN"]
    missing = []
    for key in required:
        value = env.get(key, "")
        if not value or any(p in value for p in PLACEHOLDERS):
            missing.append(key)
    return missing


def main() -> int:
    env = load_env()
    ok = True

    print("1. .env 값 확인")
    missing = check_filled(env)
    if missing:
        print(f"   [X] 아직 채워지지 않음: {', '.join(missing)}")
        return 1
    print("   [O] 필수 값 입력됨")

    print("2. 구글 토큰 갱신")
    resp = requests.post("https://oauth2.googleapis.com/token", data={
        "client_id": env["GOOGLE_CLIENT_ID"],
        "client_secret": env["GOOGLE_CLIENT_SECRET"],
        "refresh_token": env["GOOGLE_REFRESH_TOKEN"],
        "grant_type": "refresh_token",
    }, timeout=30)
    if resp.status_code != 200:
        print(f"   [X] 실패 {resp.status_code}: {resp.text[:300]}")
        return 1
    token = resp.json()["access_token"]
    print("   [O] 액세스 토큰 발급 성공")

    print("3. 블로그 목록 조회")
    resp = requests.get("https://www.googleapis.com/blogger/v3/users/self/blogs",
                        headers={"Authorization": f"Bearer {token}"}, timeout=30)
    if resp.status_code != 200:
        print(f"   [X] 실패 {resp.status_code}: {resp.text[:300]}")
        return 1
    blogs = resp.json().get("items", [])
    if not blogs:
        print("   [X] 이 계정에 블로그가 없습니다. 로그인 계정을 확인하세요.")
        return 1
    for blog in blogs:
        print(f"   [O] {blog['url']}")
        print(f"       BLOGGER_BLOG_ID = {blog['id']}")
    current = env.get("BLOGGER_BLOG_ID", "")
    ids = {b["id"] for b in blogs}
    if current in ids:
        print("   [O] .env 의 BLOGGER_BLOG_ID 가 일치합니다")
    else:
        print("   [!] 위 ID 를 .env 의 BLOGGER_BLOG_ID 에 넣으세요")
        ok = False

    print("4. Anthropic API 키")
    resp = requests.post("https://api.anthropic.com/v1/messages", headers={
        "x-api-key": env["ANTHROPIC_API_KEY"],
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }, json={
        "model": env.get("ANTHROPIC_MODEL", "claude-sonnet-5"),
        "max_tokens": 8,
        "messages": [{"role": "user", "content": "ping"}],
    }, timeout=60)
    if resp.status_code == 200:
        print("   [O] 키 정상, 모델 호출 성공")
    else:
        print(f"   [X] 실패 {resp.status_code}: {resp.text[:300]}")
        ok = False

    print("5. 이미지 CDN")
    base = env.get("IMAGE_BASE_URL", "")
    if not base or any(p in base for p in PLACEHOLDERS):
        print("   [!] 아직 미설정 (GitHub Pages 세팅 후 입력)")
        ok = False
    else:
        import json
        manifest = json.loads((ROOT / "assets" / "manifest.json").read_text(encoding="utf-8"))
        sample = manifest["images"][0]["file"]
        url = f"{base.rstrip('/')}/{sample}"
        try:
            head = requests.head(url, timeout=20, allow_redirects=True)
            if head.status_code == 200 and "image" in head.headers.get("Content-Type", ""):
                print(f"   [O] 사진 접근 가능: {url}")
            else:
                print(f"   [X] {head.status_code} {url}")
                ok = False
        except requests.RequestException as exc:
            print(f"   [X] 접근 실패: {exc}")
            ok = False

    print()
    print("모든 항목 통과. 발행 준비 완료." if ok else "위의 [X] / [!] 항목을 처리하세요.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
