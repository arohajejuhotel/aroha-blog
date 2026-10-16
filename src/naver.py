# -*- coding: utf-8 -*-
"""네이버 블로그에 붙여넣을 '네이버용 버전'을 만든다 (2026-10-16).

같은 글을 그대로 붙여넣으면 네이버 유사문서 필터에 걸려 검색에서 빠질 수 있다.
그래서 같은 주제를 네이버 말투·구성으로 다시 쓰고(문장 재사용 금지), 원문 링크를 단다.
결과물은 구글 드라이브 '네이버용 블로그 글/{blog}/날짜 제목' 폴더에 저장한다:
  - 00_네이버용_원고.html : 브라우저로 열어 전체 복사 → 네이버 에디터에 붙여넣기 (서식 유지)
  - 00_네이버용_원고.txt  : 서식 없는 버전
  - 01_썸네일.jpg/png, 02~ 사진 : 원고의 [사진n] 자리에 넣을 사진
"""
import html
import json
import re
import shutil
from pathlib import Path

PROMPT = """아래 블로그 글을 네이버 블로그용으로 **새로 쓴다**.

[원문 제목] {title}
[핵심 검색어] {keyword}
[원문 주소] {url}
[원문 본문]
{body}

규칙
- 같은 주제·같은 사실을 쓰되, 원문 문장을 그대로 가져오지 않는다. 도입부, 소제목 순서, 예시를 바꾼다.
  (네이버는 웹에 이미 있는 글과 비슷하면 검색에서 뺀다)
- 네이버 블로그 독자 말투: 짧은 문단(2~3문장), 소제목은 굵게, 핵심은 목록으로. 이모지는 소제목에만 가끔.
- 분량 1,500~2,500자. 제목은 핵심 검색어를 맨 앞에 넣고 25~35자.
- 사진 자리는 [사진1]~[사진{n}] 로 표시한다 (사진은 {n}장 있다. 1번은 썸네일이라 맨 위).
- 마지막 문단에 "더 자세한 내용은 원문에서" 처럼 원문 주소로 안내한다.
- 해시태그 10~15개 (네이버에서 실제로 검색되는 붙여쓴 단어).
{extra}
다음 JSON 하나만 출력한다:
{{"title": "제목", "body_html": "<p>, <h3>, <ul>, <li>, <strong> 만 쓴 본문", "hashtags": ["#태그"]}}"""


def _plain(body_html: str) -> str:
    t = re.sub(r"<script.*?</script>", "", body_html, flags=re.S)
    t = re.sub(r"<(br|/p|/h[1-6]|/li)[^>]*>", "\n", t)
    return re.sub(r"\n{3,}", "\n\n", html.unescape(re.sub(r"<[^>]+>", "", t))).strip()


def write(client, model: str, title: str, keyword: str, url: str, body_html: str,
          n_photos: int, extra: str = "") -> dict:
    prompt = PROMPT.format(title=title, keyword=keyword or title, url=url or "(주소 미정)",
                           body=_plain(body_html)[:9000], n=n_photos, extra=extra)
    resp = client.messages.create(model=model, max_tokens=6000,
                                  messages=[{"role": "user", "content": prompt}])
    text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    return json.loads(text[text.index("{"): text.rindex("}") + 1], strict=False)


def package(post: dict, photos: list, out_dir: Path) -> list:
    """원고(html/txt)와 사진을 out_dir 에 모으고 파일 목록을 돌려준다."""
    out_dir.mkdir(parents=True, exist_ok=True)
    files = []
    for i, src in enumerate(photos, 1):
        src = Path(src)
        dst = out_dir / (f"{i:02d}_썸네일{src.suffix}" if i == 1 else f"{i:02d}_사진{i}{src.suffix}")
        shutil.copyfile(src, dst)
        files.append(dst)

    tags = " ".join(post.get("hashtags", []))
    body = post["body_html"]
    # [사진n] 표시는 눈에 띄게 (붙여넣은 뒤 그 자리에 사진을 넣는다)
    body = re.sub(r"\[사진(\d+)\]",
                  lambda m: f'<p style="background:#fff3cd;padding:6px 10px;">📷 [사진{m.group(1)}] '
                            f'← {int(m.group(1)):02d}번 사진을 여기에</p>', body)
    page = (f"<!doctype html><meta charset='utf-8'><title>{html.escape(post['title'])}</title>"
            f"<div style='max-width:720px;margin:30px auto;font:16px/1.8 sans-serif'>"
            f"<p style='color:#888;font-size:13px'>아래 제목과 본문을 복사해 네이버 블로그에 붙여넣으세요. "
            f"노란 표시 자리에 같은 번호의 사진을 넣으면 됩니다.</p>"
            f"<h2>{html.escape(post['title'])}</h2>{body}<p>{html.escape(tags)}</p></div>")
    h = out_dir / "00_네이버용_원고.html"
    h.write_text(page, encoding="utf-8")
    t = out_dir / "00_네이버용_원고.txt"
    t.write_text(f"{post['title']}\n\n{_plain(post['body_html'])}\n\n{tags}\n", encoding="utf-8")
    return [h, t] + files
