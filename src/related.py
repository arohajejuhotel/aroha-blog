"""관련 글 링크 (내부 링크).

2026-11-25 사용자 결정: Blogger 조회수가 낮아(누적 116회) 글끼리 이어 주는
내부 링크를 넣는다. 구글이 블로그를 한 주제의 정보 모음으로 읽게 하고,
들어온 독자가 다른 글로 넘어가게 하려는 목적.

- 같은 언어의 공개 글 중 라벨이 많이 겹치는 글 4편을 고른다.
- 블록은 class="aroha-related" div 하나라서 다시 돌리면 그 자리만 바뀐다.
- 새 글을 올린 뒤에는 그 글이 링크한 예전 글들의 블록도 다시 만들어,
  예전 글에서도 새 글로 들어오는 링크가 생기게 한다.

예전 글 전체에 붙이기:  python scripts/add_related_links.py [--dry-run]
"""

import html
import re

from src.render import C

PER_POST = 4
BLOCK_RE = re.compile(r'<div class="aroha-related"[^>]*>.*?</div>', re.S)
# 라벨이 겹쳐도 관련성을 말해 주지 않는 것들
GENERIC = {"english", "travel tips", "jeju guide"}
# 카테고리 라벨 (겹치면 약하게만 센다)
CATEGORY = {"seongsan travel", "east jeju guide", "jeju island guide", "aroha stories",
            "성산여행정보", "제주동부여행", "제주전역여행", "아로하이야기"}
STOP = {"a", "an", "the", "and", "or", "of", "in", "to", "for", "on", "at", "is", "it",
        "do", "you", "your", "what", "how", "when", "where", "which", "why", "with",
        "jeju", "guide", "by", "vs", "from", "are", "can", "i", "need", "s"}

HEADING = {"en": "More Jeju guides you may find useful", "ko": "함께 보면 좋은 제주 글"}


def lang_of(post: dict) -> str:
    labels = {l.lower() for l in post.get("labels", [])}
    return "en" if "english" in labels else "ko"


def _words(title: str) -> set:
    return {w for w in re.findall(r"[a-z0-9]+", title.lower()) if w not in STOP and len(w) > 2}


def score(a: dict, b: dict) -> float:
    la = {l.lower() for l in a.get("labels", [])} - GENERIC
    lb = {l.lower() for l in b.get("labels", [])} - GENERIC
    common = la & lb
    s = sum(0.5 if l in CATEGORY else 2.0 for l in common)
    s += 0.7 * len(_words(a.get("title", "")) & _words(b.get("title", "")))
    return s


def pick(target: dict, posts: list, n: int = PER_POST) -> list:
    """target 과 관련 깊은 같은 언어 글 n 편. 점수가 같으면 최신 글 먼저."""
    lang = lang_of(target)
    cands = [p for p in posts
             if p.get("url") and p.get("url") != target.get("url")
             and p.get("id") != target.get("id") and lang_of(p) == lang]
    cands.sort(key=lambda p: (score(target, p), p.get("published", "")), reverse=True)
    return cands[:n]


def block(items: list, lang: str) -> str:
    if not items:
        return ""
    lis = "".join(
        f'<li style="margin:6px 0;"><a href="{html.escape(p["url"])}" '
        f'style="color:{C["teal"]};">{html.escape(p["title"])}</a></li>'
        for p in items
    )
    return (
        f'<div class="aroha-related" style="margin:40px 0 0;padding:18px 22px;'
        f'border-left:4px solid {C["mint"]};background:#f7f5f1;border-radius:8px;">'
        f'<h3 style="margin:0 0 8px;font-size:18px;">{HEADING[lang]}</h3>'
        f'<ul style="margin:0;padding-left:20px;line-height:1.7;">{lis}</ul></div>'
    )


def apply(content: str, new_block: str) -> str:
    """본문에 관련 글 블록을 넣는다. 이미 있으면 그 자리를 바꾼다.

    새로 넣을 땐 FAQ 제목 바로 앞(본문이 끝난 자리)에 둔다.
    """
    if BLOCK_RE.search(content):
        return BLOCK_RE.sub(lambda _: new_block, content, count=1)
    if not new_block:
        return content
    for marker in ('<h2 style="margin-top:44px;">', '<script type="application/ld+json">'):
        i = content.find(marker)
        if i != -1:
            return content[:i] + new_block + "\n" + content[i:]
    return content + "\n" + new_block


def live_posts(client) -> list:
    """Blogger 의 공개 글 전부 (본문 제외)."""
    posts, token = [], None
    while True:
        params = {"maxResults": 50, "fetchBodies": "false", "status": "live"}
        if token:
            params["pageToken"] = token
        data = client._request("GET", f"/blogs/{client.blog_id}/posts", params=params)
        posts += data.get("items", [])
        token = data.get("nextPageToken")
        if not token:
            return posts


def refresh(client, post_ids: list, posts: list = None, dry_run: bool = False) -> int:
    """post_ids 글들의 관련 글 블록을 다시 만들어 고친다. 바뀐 글 수를 돌려준다."""
    posts = posts if posts is not None else live_posts(client)
    by_id = {p["id"]: p for p in posts}
    changed = 0
    for pid in post_ids:
        meta = by_id.get(pid)
        if not meta:
            continue
        full = client._request("GET", f"/blogs/{client.blog_id}/posts/{pid}")
        new = apply(full.get("content", ""), block(pick(meta, posts), lang_of(meta)))
        if new == full.get("content", ""):
            continue
        changed += 1
        if dry_run:
            print(f"[dry-run] 관련 글 갱신 예정: {meta['title']}")
            continue
        client.patch_post(pid, content=new)
        print(f"[ok] 관련 글 갱신: {meta['title']}")
    return changed
