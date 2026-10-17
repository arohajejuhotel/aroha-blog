# -*- coding: utf-8 -*-
"""한국어 블로그 글을 인스타그램 캐러셀로 다시 짠다 (2026-10-17).

흐름
  1. write()        Claude 가 글을 카드 문구 + 캡션 + 대체 텍스트로 바꾼다 (프런트 직원 말투)
  2. pick_photos()  카드마다 내용에 맞는 사진을 Claude 가 보고 고른다
  3. package()      insta_cards 로 1080x1350 카드를 그리고 캡션 파일과 함께 모은다
  4. 저장/발행      INSTAGRAM_MODE
                    - preview (기본): 구글 드라이브 '인스타그램 게시물/아로하/날짜 제목' 에 저장 → 사람이 올린다
                    - publish: Instagram API 로 캐러셀 발행 (INSTAGRAM_ACCESS_TOKEN 필요)
                    - off: 아무것도 안 한다

사진은 글자를 얹고 자르기 때문에 '변형 가능한' 사진만 쓴다:
호텔이 직접 찍은 사진 + 한국관광공사 공공누리 제1유형 (출처 표기).
"""
import io
import json
import os
import re
import time
from pathlib import Path

import requests
from PIL import Image

from src import insta_cards

PROMPT = """아래 블로그 글을 인스타그램 캐러셀(카드 여러 장) 게시물로 다시 짠다.

[글 제목] {title}
[블로그 주소] {url}
[호텔 팩트 — 숫자·시간·요금은 여기와 본문에 있는 것만 쓴다]
{facts}
[글 본문]
{body}

말투 (가장 중요)
- 호텔아로하 프런트 직원이 손님에게 말해 주듯 쓴다. 존댓말 구어체(~요, ~거든요, ~세요).
- 설명문·보고서 말투 금지. "~할 수 있습니다", "~를 소개합니다", "완벽 정리", "꿀팁", "알아보세요" 같은
  AI·광고 티 나는 표현을 쓰지 않는다.
- 손님이 실제로 묻는 질문을 그대로 소제목으로 써도 좋다. 예: "배표 미리 끊어야 해요?"
- 겪지 않은 일화("어제 오신 손님이…")를 지어내지 않는다. 의견("제 추천은 첫 배")은 괜찮다.
- 호텔 단점(객실 크기, 없는 시설, 일회용품, 조식)은 쓰지 않는다.

구성
- cover_lines: 표지 제목 2줄. 줄당 12자 안팎. 궁금해서 넘기게 만드는 말.
- cards: 정보 카드 4~5장. heading 은 16자 이내, body 는 2~3줄(줄바꿈 \\n, 줄당 22자 안팎).
  카드 하나에 정보 하나. 글에서 가장 쓸모 있는 것만 고른다.
  photo_hint: 이 카드에 어울리는 사진 장면 (예: "우도봉 등대", "성산항 여객선", "객실 창밖 바다").
- cta_heading: 마지막 카드 제목. 글 주제와 호텔을 잇는 한 줄 (16자 이내). 예: "우도 터미널까지 걸어서 10분"
- cta_points: 호텔 강점 3개 (각 16자 이내, 팩트에 있는 것만).
- caption: 3~5줄. 첫 줄은 훅(질문이나 공감), 가운데 핵심 1~2줄, 마지막 줄 "예약·문의는 프로필 링크에서".
  블로그 주소는 넣지 않는다 (인스타 캡션 링크는 눌리지 않는다).
- hashtags: 8~12개. 지역+주제 위주 (#성산숙소 #우도여행 처럼 붙여쓴 실제 검색어). #호텔아로하 포함.

다음 JSON 하나만 출력한다:
{{"cover_lines": ["", ""], "cards": [{{"heading": "", "body": "", "photo_hint": ""}}],
 "cta_heading": "", "cta_points": ["", "", ""], "caption": "", "hashtags": ["#"]}}"""

PHOTO_PROMPT = """인스타그램 카드에 넣을 사진을 고른다. 위 사진 {n}장(0번부터)이 후보다.

[게시물 주제] {title}
[장마다 필요한 장면]
{wants}

규칙
- 0번 장(표지)은 위쪽 절반에 큰 흰 글자를 얹는다. 하늘·바다처럼 위쪽이 단순한 사진, 사진 안 글자가 적은 사진.
- 각 장 내용과 실제로 맞는 사진을 고른다. 맞는 게 없으면 그 주제 장소의 분위기가 사는 사진.
- 같은 사진을 두 번 쓰지 않는다 (후보가 모자라면 예외).
- alts: 고른 사진마다 대체 텍스트 한 문장. 사진에 실제로 보이는 것만 쓴다 (장소를 확신할 수 없으면
  "제주 바닷가 풍경"처럼 일반적으로).
다음 JSON 하나만 출력한다: {{"pick": [장0 사진번호, 장1 사진번호, ...], "alts": ["장0 설명", ...], "reason": "한 줄"}}"""


def _plain(body_html: str) -> str:
    t = re.sub(r"<script.*?</script>", "", body_html, flags=re.S)
    t = re.sub(r"<(br|/p|/h[1-6]|/li)[^>]*>", "\n", t)
    t = re.sub(r"<[^>]+>", "", t)
    return re.sub(r"\n{3,}", "\n\n", t).strip()


def _json(text: str) -> dict:
    return json.loads(text[text.index("{"): text.rindex("}") + 1], strict=False)


def write(client, model: str, title: str, url: str, body_html: str, hotel: dict) -> dict:
    facts = {k: hotel[k] for k in ("name_ko", "concept_ko", "checkin", "checkout", "rooms",
                                   "amenities_ko", "walking_distance_ko", "verified_facts",
                                   "honest_limits", "not_offered") if k in hotel}
    facts["selling_points"] = [p["ko"] for p in hotel.get("selling_points", [])]
    prompt = PROMPT.format(title=title, url=url or "(주소 미정)",
                           facts=json.dumps(facts, ensure_ascii=False)[:4000],
                           body=_plain(body_html)[:8000])
    resp = client.messages.create(model=model, max_tokens=8000,
                                  messages=[{"role": "user", "content": prompt}])
    post = _json("".join(b.text for b in resp.content if getattr(b, "type", "") == "text"))
    # 본문이 빈 카드, 마지막 예약 카드와 겹치는 카드는 뺀다
    cta = post.get("cta_heading", "").replace(" ", "")
    post["cards"] = [c for c in post["cards"]
                     if c.get("body", "").strip() and c.get("heading", "").replace(" ", "") != cta][:5]
    return post


def pick_photos(client, model: str, post: dict, title: str, cands: list) -> list:
    """장마다(표지 + 정보 카드) 후보 번호를 고른다. 실패하면 앞에서부터 차례로."""
    slots = 1 + len(post["cards"])
    fallback = [i % len(cands) for i in range(slots)]
    if len(cands) < 2:
        return fallback
    cands = cands[:12]
    wants = "\n".join([f"0번 장(표지): {' '.join(post['cover_lines'])}"] +
                      [f"{i}번 장: {c['heading']} — {c.get('photo_hint', '')}"
                       for i, c in enumerate(post["cards"], 1)])
    content = [{"type": "image", "source": {"type": "url", "url": c["url"]}} for c in cands]
    content.append({"type": "text", "text": PHOTO_PROMPT.format(n=len(cands), title=title, wants=wants)})
    text = ""
    try:
        # 사진 12장을 보고 생각하는 데 토큰이 꽤 든다. 모자라면 답(JSON) 없이 끝난다.
        resp = client.messages.create(model=model, max_tokens=8000,
                                      messages=[{"role": "user", "content": content}])
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        if not text:
            raise ValueError(f"빈 응답 (stop_reason={resp.stop_reason})")
        pick = _json(text)
        idx = [int(i) for i in pick["pick"]][:slots]
        if len(idx) < slots or not all(0 <= i < len(cands) for i in idx):
            return fallback
        alts = [str(a) for a in pick.get("alts", [])][:slots]
        if len(alts) == slots:
            # 실제로 고른 사진을 보고 쓴 설명으로 바꾼다. 마지막 예약 카드 설명은 그대로 둔다.
            post["alts"] = alts + ["호텔아로하 예약 안내 카드"]
        print(f"  [insta] 사진 선택 {idx} — {pick.get('reason', '')}")
        return idx
    except Exception as exc:  # noqa: BLE001
        print(f"  [insta] 사진 선택 실패, 순서대로 사용 ({type(exc).__name__}: {str(exc)[:200]}"
              f"{' / 응답: ' + text[:200] if text else ''})")
        return fallback


def _load(c: dict) -> Image.Image:
    if c.get("local") and Path(c["local"]).exists():
        return Image.open(c["local"])
    resp = requests.get(c["url"], timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    return Image.open(io.BytesIO(resp.content))


def package(post: dict, cands: list, idx: list, cat: str, out_dir: Path, stem: str) -> list:
    """카드 이미지 + 캡션 파일을 out_dir 에 만든다. 파일 목록(카드 먼저)을 돌려준다."""
    chosen = [cands[i] for i in idx]
    slides = {k: post[k] for k in ("cover_lines", "cards", "cta_heading", "cta_points")}
    cards = insta_cards.build(slides, [_load(c) for c in chosen], out_dir, stem, cat,
                              credits=[c.get("credit", "") for c in chosen])
    caption = post["caption"].strip() + "\n\n" + " ".join(post.get("hashtags", []))
    alts = post.get("alts", [])
    credit_note = sorted({c["credit"] for c in chosen if c.get("credit")})
    guide = [caption, "", "─" * 20, "대체 텍스트 (장마다 접근성 → 대체 텍스트에 붙여넣기)"]
    guide += [f"{i}. {a}" for i, a in enumerate(alts, 1)]
    if credit_note:
        guide += ["", " / ".join(credit_note)]
    txt = out_dir / f"{stem}-캡션.txt"
    txt.write_text("\n".join(guide) + "\n", encoding="utf-8")
    return cards + [txt]


# --- Instagram API 발행 ---------------------------------------------------------
# Instagram API with Instagram Login. 토큰을 받은 뒤 처음 켤 때 반드시 한 번 검수한다.
GRAPH = "https://graph.instagram.com/v21.0"


def can_publish() -> bool:
    return bool(os.environ.get("INSTAGRAM_ACCESS_TOKEN", "").strip()
                and os.environ.get("INSTAGRAM_USER_ID", "").strip())


def _post(path: str, **data) -> dict:
    data["access_token"] = os.environ["INSTAGRAM_ACCESS_TOKEN"].strip()
    resp = requests.post(f"{GRAPH}/{path}", data=data, timeout=60)
    body = resp.json()
    if resp.status_code != 200 or "error" in body:
        # 응답에 토큰이 들어가지 않으므로 메시지만 남긴다
        raise RuntimeError(f"Instagram API {path}: {body.get('error', {}).get('message', body)}")
    return body


def _wait_ready(container_id: str) -> None:
    token = os.environ["INSTAGRAM_ACCESS_TOKEN"].strip()
    for _ in range(30):
        r = requests.get(f"{GRAPH}/{container_id}",
                         params={"fields": "status_code", "access_token": token}, timeout=30).json()
        if r.get("status_code") == "FINISHED":
            return
        if r.get("status_code") == "ERROR":
            raise RuntimeError(f"Instagram 컨테이너 처리 실패: {container_id}")
        time.sleep(4)
    raise RuntimeError("Instagram 컨테이너 처리 시간 초과")


def host(cards: list) -> list:
    """카드를 저장소에 한 번에 커밋·푸시하고 jsDelivr 주소 목록을 돌려준다 (썸네일과 같은 방식).
    cards 는 저장소 안(assets/insta/...)에 있어야 한다."""
    from src import thumbnail
    rels = [Path(c).relative_to(thumbnail.ROOT).as_posix() for c in cards]
    thumbnail._git("add", *rels)
    thumbnail._git("commit", "-m", f"chore: instagram cards {Path(cards[0]).stem}")
    for _ in range(3):
        try:
            thumbnail._git("push", "origin", "HEAD")
            break
        except Exception:  # noqa: BLE001
            thumbnail._git("pull", "--rebase", "origin", "main")
    else:
        raise RuntimeError("인스타 카드 푸시 실패")
    sha = thumbnail._git("rev-parse", "HEAD")
    urls = [f"https://cdn.jsdelivr.net/gh/{thumbnail._repo_slug()}@{sha}/{r}" for r in rels]
    for _ in range(12):  # jsDelivr 가 가져올 때까지
        if all(requests.head(u, timeout=15).status_code == 200 for u in urls):
            break
        time.sleep(5)
    return urls


def publish(image_urls: list, caption: str, alts: list) -> str:
    """공개 주소의 JPEG 들로 캐러셀을 발행하고 게시물 id 를 돌려준다."""
    uid = os.environ["INSTAGRAM_USER_ID"].strip()
    children = []
    for i, url in enumerate(image_urls):
        extra = {"alt_text": alts[i]} if i < len(alts) and alts[i] else {}
        c = _post(f"{uid}/media", image_url=url, is_carousel_item="true", **extra)
        children.append(c["id"])
    for c in children:
        _wait_ready(c)
    carousel = _post(f"{uid}/media", media_type="CAROUSEL", children=",".join(children),
                     caption=caption)
    _wait_ready(carousel["id"])
    return _post(f"{uid}/media_publish", creation_id=carousel["id"])["id"]
