"""Blogger API v3 클라이언트 (refresh token 방식, 의존성 최소)."""

import time

import requests

TOKEN_URL = "https://oauth2.googleapis.com/token"
API = "https://www.googleapis.com/blogger/v3"


class Blogger:
    def __init__(self, blog_id: str, client_id: str, client_secret: str,
                 refresh_token: str):
        self.blog_id = blog_id
        self._client_id = client_id
        self._client_secret = client_secret
        self._refresh_token = refresh_token
        self._token = None
        self._expires_at = 0.0

    # --- auth ---------------------------------------------------------
    def _access_token(self) -> str:
        if self._token and time.time() < self._expires_at - 60:
            return self._token
        resp = requests.post(TOKEN_URL, data={
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "refresh_token": self._refresh_token,
            "grant_type": "refresh_token",
        }, timeout=30)
        if resp.status_code != 200:
            raise SystemExit(
                "구글 토큰 갱신 실패. GOOGLE_REFRESH_TOKEN 이 만료되었거나 "
                f"클라이언트 정보가 틀렸습니다.\n{resp.status_code} {resp.text}"
            )
        data = resp.json()
        self._token = data["access_token"]
        self._expires_at = time.time() + data.get("expires_in", 3600)
        return self._token

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._access_token()}",
            "Content-Type": "application/json; charset=UTF-8",
        }

    def _request(self, method: str, path: str, **kwargs):
        url = f"{API}{path}"
        for attempt in range(3):
            resp = requests.request(method, url, headers=self._headers(),
                                    timeout=60, **kwargs)
            if resp.status_code < 300:
                return resp.json()
            if resp.status_code in (429, 500, 502, 503) and attempt < 2:
                wait = 5 * (attempt + 1)
                print(f"[warn] Blogger {resp.status_code}, {wait}초 후 재시도")
                time.sleep(wait)
                continue
            raise SystemExit(f"Blogger API 오류 {resp.status_code}: {resp.text}")

    # --- api ----------------------------------------------------------
    def blog_info(self) -> dict:
        return self._request("GET", f"/blogs/{self.blog_id}")

    def create_post(self, title: str, content: str, labels: list,
                    draft: bool = False) -> dict:
        payload = {
            "kind": "blogger#post",
            "blog": {"id": self.blog_id},
            "title": title,
            "content": content,
            "labels": labels[:20],
        }
        return self._request(
            "POST", f"/blogs/{self.blog_id}/posts/",
            params={"isDraft": "true" if draft else "false"},
            json=payload,
        )

    def patch_post(self, post_id: str, **fields) -> dict:
        return self._request("PATCH", f"/blogs/{self.blog_id}/posts/{post_id}",
                             json=fields)


def blog_id_from_url(blog_url: str, api_key: str) -> str:
    """API 키만으로 블로그 주소 -> blogId 를 조회한다 (최초 세팅용)."""
    resp = requests.get(f"{API}/blogs/byurl",
                        params={"url": blog_url, "key": api_key}, timeout=30)
    resp.raise_for_status()
    return resp.json()["id"]
