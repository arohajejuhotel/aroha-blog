"""구글 OAuth refresh token 을 한 번만 발급받는 도우미 (로컬 PC 에서 1회 실행).

사전 준비 — Google Cloud Console (console.cloud.google.com):
 1. 프로젝트 생성
 2. "API 및 서비스 > 라이브러리" 에서 Blogger API v3 사용 설정
 3. "OAuth 동의 화면" 구성 (외부 / 테스트 사용자에 본인 지메일 추가)
 4. "사용자 인증 정보 > OAuth 클라이언트 ID" 를 '데스크톱 앱' 으로 생성
 5. 클라이언트 ID 와 보안 비밀번호를 아래에 넣고 실행

    python scripts/get_refresh_token.py --client-id XXX --client-secret YYY

브라우저가 열리면 호텔 블로그를 운영할 구글 계정으로 로그인하고 권한을 허용한다.
터미널에 출력되는 refresh token 을 GitHub Secrets 에 저장한다.
"""

import argparse
import secrets
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests

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
    ap.add_argument("--client-id", required=True)
    ap.add_argument("--client-secret", required=True)
    args = ap.parse_args()

    state = secrets.token_urlsafe(16)
    url = AUTH_URL + "?" + urllib.parse.urlencode({
        "client_id": args.client_id,
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
        "client_id": args.client_id,
        "client_secret": args.client_secret,
        "redirect_uri": REDIRECT,
        "grant_type": "authorization_code",
    }, timeout=30)
    resp.raise_for_status()
    token = resp.json().get("refresh_token")
    if not token:
        print("refresh_token 이 반환되지 않았습니다. 구글 계정 보안 설정에서 "
              "이 앱의 권한을 삭제한 뒤 다시 실행하세요.")
        print(resp.json())
        return 1

    print("\n" + "=" * 60)
    print("GOOGLE_REFRESH_TOKEN =")
    print(token)
    print("=" * 60)
    print("\n이 값을 GitHub 저장소의 Settings > Secrets and variables > Actions 에")
    print("GOOGLE_REFRESH_TOKEN 이라는 이름으로 저장하세요.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
