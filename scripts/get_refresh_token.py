"""구글 OAuth refresh token 을 발급받아 .env 에 써 넣는다.

.env 에 GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET 가 이미 있으면 그대로 실행하면 된다.

    python scripts/get_refresh_token.py

없으면 직접 넘길 수도 있다.

    python scripts/get_refresh_token.py --client-id XXX --client-secret YYY

브라우저가 열리면 **블로그를 운영할 구글 계정**으로 로그인하고 권한을 허용한다.
발급된 토큰은 .env 의 GOOGLE_REFRESH_TOKEN 에 자동으로 저장된다.
"""

import argparse
import secrets
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import requests

ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


def read_env() -> dict:
    if not ENV_FILE.exists():
        return {}
    env = {}
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def write_env(key: str, value: str) -> bool:
    """.env 의 해당 키를 갱신한다. 없으면 끝에 추가."""
    if not ENV_FILE.exists():
        return False
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    found = False
    for n, line in enumerate(lines):
        if line.strip().startswith(f"{key}="):
            lines[n] = f"{key}={value}"
            found = True
            break
    if not found:
        lines.append(f"{key}={value}")
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPE = "https://www.googleapis.com/auth/blogger"
PORT = 8731
REDIRECT = f"http://localhost:{PORT}/"

_result = {}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        query = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(query)
        _result.update({k: v[0] for k, v in params.items()})
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        ok = "code" in _result
        msg = ("인증이 끝났습니다. 터미널로 돌아가세요." if ok
               else f"인증 실패: {_result.get('error', 'unknown')}")
        self.wfile.write(
            f"<html><body style='font-family:system-ui;padding:60px;text-align:center'>"
            f"<h2>{msg}</h2></body></html>".encode("utf-8"))

    def log_message(self, *_args):
        pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--client-id", default="")
    ap.add_argument("--client-secret", default="")
    args = ap.parse_args()

    env = read_env()
    client_id = args.client_id or env.get("GOOGLE_CLIENT_ID", "")
    client_secret = args.client_secret or env.get("GOOGLE_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        print("클라이언트 정보를 찾을 수 없습니다.")
        print(f"  .env 파일({ENV_FILE})에 GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET 를 넣거나,")
        print("  --client-id / --client-secret 로 직접 넘기세요.")
        return 1
    print(f"클라이언트 ID: {client_id[:24]}...")

    state = secrets.token_urlsafe(16)
    url = AUTH_URL + "?" + urllib.parse.urlencode({
        "client_id": client_id,
        "redirect_uri": REDIRECT,
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    })

    print("브라우저에서 아래 주소를 열어 권한을 허용하세요:\n")
    print(url + "\n")
    webbrowser.open(url)

    server = HTTPServer(("localhost", PORT), Handler)
    print(f"localhost:{PORT} 에서 응답을 기다리는 중...")
    server.handle_request()

    if _result.get("state") != state:
        print("state 값이 일치하지 않습니다. 다시 시도하세요.")
        return 1
    if "code" not in _result:
        print(f"인증 실패: {_result}")
        return 1

    resp = requests.post(TOKEN_URL, data={
        "code": _result["code"],
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": REDIRECT,
        "grant_type": "authorization_code",
    }, timeout=30)
    if resp.status_code != 200:
        print(f"토큰 교환 실패 {resp.status_code}: {resp.text[:400]}")
        return 1
    token = resp.json().get("refresh_token")
    if not token:
        print("refresh_token 이 반환되지 않았습니다. https://myaccount.google.com/permissions "
              "에서 이 앱의 액세스를 삭제한 뒤 다시 실행하세요.")
        return 1

    # 어느 계정의 블로그에 연결됐는지 바로 확인해 준다
    access = resp.json().get("access_token")
    if access:
        blogs = requests.get(
            "https://www.googleapis.com/blogger/v3/users/self/blogs",
            headers={"Authorization": f"Bearer {access}"}, timeout=30)
        if blogs.status_code == 200:
            items = blogs.json().get("items", [])
            print("\n연결된 블로그:")
            for blog in items:
                print(f"  - {blog['url']}  (id: {blog['id']})")
            if items:
                write_env("BLOGGER_BLOG_ID", items[0]["id"])
                print("  -> BLOGGER_BLOG_ID 를 .env 에 저장했습니다.")
        else:
            print(f"\n[주의] 블로그 목록 조회 실패: {blogs.status_code}")

    if write_env("GOOGLE_REFRESH_TOKEN", token):
        print(f"\n[완료] GOOGLE_REFRESH_TOKEN 을 {ENV_FILE} 에 저장했습니다.")
        print("이어서 다음을 실행하세요:  python scripts/setup_check.py")
    else:
        print("\n" + "=" * 60)
        print("GOOGLE_REFRESH_TOKEN =")
        print(token)
        print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
