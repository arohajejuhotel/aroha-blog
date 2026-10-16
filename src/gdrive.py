# -*- coding: utf-8 -*-
"""네이버용 원고를 구글 드라이브(yhlee0428)의 '네이버용 블로그 글' 폴더에 저장한다.

네이버 블로그는 자동 업로드 API 가 없어서, 매일 네이버용으로 다시 쓴 글과 사진을
드라이브에 저장해 두고 사람이 복사·붙여넣기 한다. 드라이브 데스크톱이 PC 의
G:\\내 드라이브\\네이버용 블로그 글 로 동기화한다.

권한은 drive.file (이 앱이 만든 파일만) 이라 기존 드라이브 파일에는 접근하지 못한다.
환경 변수: GDRIVE_CLIENT_ID, GDRIVE_CLIENT_SECRET, GDRIVE_REFRESH_TOKEN
(로컬에서는 client_secret.json + token_drive.json 으로 대신한다)
"""
import json
import mimetypes
import os
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

ROOT_NAME = "네이버용 블로그 글"
API = "https://www.googleapis.com/drive/v3/files"
UPLOAD = "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&fields=id,name"
FOLDER = "application/vnd.google-apps.folder"


def _creds():
    cid = os.environ.get("GDRIVE_CLIENT_ID", "").strip()
    sec = os.environ.get("GDRIVE_CLIENT_SECRET", "").strip()
    tok = os.environ.get("GDRIVE_REFRESH_TOKEN", "").strip()
    if not (cid and sec and tok):
        here = Path(__file__).parent
        try:
            t = json.loads((here / "token_drive.json").read_text(encoding="utf-8"))
            cid, sec, tok = t["client_id"], t["client_secret"], t["refresh_token"]
        except Exception:
            return None
    return cid, sec, tok


def enabled() -> bool:
    return _creds() is not None


def _access_token() -> str:
    cid, sec, tok = _creds()
    data = urllib.parse.urlencode({"client_id": cid, "client_secret": sec, "refresh_token": tok,
                                   "grant_type": "refresh_token"}).encode()
    resp = urllib.request.urlopen("https://oauth2.googleapis.com/token", data, timeout=30)
    return json.loads(resp.read())["access_token"]


def _req(method, url, token, body=None, headers=None):
    h = {"Authorization": f"Bearer {token}", **(headers or {})}
    req = urllib.request.Request(url, data=body, headers=h, method=method)
    return json.loads(urllib.request.urlopen(req, timeout=60).read() or b"{}")


def _folder(token, name, parent=None) -> str:
    q = f"name = '{name}' and mimeType = '{FOLDER}' and trashed = false"
    if parent:
        q += f" and '{parent}' in parents"
    found = _req("GET", f"{API}?" + urllib.parse.urlencode({"q": q, "fields": "files(id)"}), token)
    if found.get("files"):
        return found["files"][0]["id"]
    meta = {"name": name, "mimeType": FOLDER, **({"parents": [parent]} if parent else {})}
    return _req("POST", f"{API}?fields=id", token, json.dumps(meta).encode(),
                {"Content-Type": "application/json; charset=UTF-8"})["id"]


def _upload(token, path: Path, parent: str, name: str = "") -> str:
    boundary = uuid.uuid4().hex
    meta = json.dumps({"name": name or path.name, "parents": [parent]}).encode()
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    body = (f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n".encode() + meta
            + f"\r\n--{boundary}\r\nContent-Type: {mime}\r\n\r\n".encode() + path.read_bytes()
            + f"\r\n--{boundary}--".encode())
    return _req("POST", UPLOAD, token, body, {"Content-Type": f"multipart/related; boundary={boundary}"})["id"]


def save(blog: str, day: str, title: str, files: list) -> str:
    """'네이버용 블로그 글/{blog}/{day} {title}' 폴더에 파일들을 올린다. 폴더 경로를 돌려준다."""
    token = _access_token()
    root = _folder(token, ROOT_NAME)
    blog_dir = _folder(token, blog, root)
    safe = "".join(c for c in title if c not in '\\/:*?"<>|')[:50].strip()
    post_dir = _folder(token, f"{day} {safe}", blog_dir)
    for f in files:
        _upload(token, Path(f), post_dir)
    return f"{ROOT_NAME}/{blog}/{day} {safe}"
