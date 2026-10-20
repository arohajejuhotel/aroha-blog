# -*- coding: utf-8 -*-
"""AI 가 쓴 티가 나는 상투 표현을 걸러낸다 (2026-10-20).

사용자 지적: "~가 전부다", "~ ~ 하나만" 같은 표현은 너무 AI 스럽다.
1) 프롬프트에 RULE 을 넣어 처음부터 덜 쓰게 하고
2) 생성 뒤 scrub() 으로 걸린 문장만 Claude 에게 다시 쓰게 한다. 그래도 남으면 그 문장을 지운다.
역삼동이선생 저장소(blog-auto/cliche.py)에도 같은 파일이 있다. 고칠 때 둘 다 고친다.
"""
import json
import re

RULE = """[AI 티 나는 상투 표현 금지 — 반드시 지킨다]
- "~가 전부다/전부입니다", "그게 다다", "이게 핵심이다", "~면 끝이다", "그걸로 끝"
- "~ 하나만 있으면/기억하면/챙기면", "딱 하나", "단 하나", "~ 하나면 충분하다"
- "이것만 알면", "결론부터 말하면", "이유는 하나다", "답은 간단하다", "단순한 ~이 아니라 ~이다"
- 영어: "is all you need", "all it takes is", "that's it.", "just one thing", "here's the thing",
  "the secret is", "not just a ..., it's ..."
이런 단정·요약형 결론 문장 대신, 구체적인 장면·숫자·이유를 담은 평범한 문장으로 쓴다."""

PATTERN = re.compile(
    r"전부(?:다|입니다|예요|이에요|였다|였어요|였습니다|야)(?=[\s.!?。,\"'”’]|$)"
    r"|그게\s*다(?:다|입니다|예요)|이게\s*(?:전부|핵심|답)(?:이다|입니다|이에요|다)?(?=[\s.!?。,]|$)"
    r"|(?:면|그걸로)\s*끝(?:이다|입니다|이에요|이야|나요|난다|납니다)?(?=[\s.!?。,\"'”]|$)"
    r"|하나만\s*(?:있으면|챙기|기억|알면|알아|준비|보면|하면|가져)"
    r"|하나면\s*(?:충분|끝|된다|됩니다|돼요)|딱\s*하나|단\s*하나(?:만|뿐|의|다|입니다)?"
    r"|이것만\s*(?:알면|기억|챙기)|결론부터\s*말(?:하면|하자면|씀드리면)"
    r"|이유는\s*(?:단\s*)?(?:하나|간단)|답은\s*(?:간단|하나|명확)"
    r"|(?:단순한|그냥)\s*\S+(?:이|가)\s*아니(?:라|다|에요|었)"
    r"|\bis\s+all\s+you\s+need|\ball\s+(?:you\s+need|it\s+takes)\s+is"
    r"|\bthat'?s\s+(?:it|all)\s*[.!]|\bjust\s+one\s+thing|\bhere'?s\s+the\s+thing"
    r"|\bthe\s+secret\s+is|\b(?:isn'?t|is\s+not)\s+just\s+an?\s+[^.!?]{1,40}[,—–-]\s*it'?s",
    re.I,
)

# 태그 경계를 넘지 않는 한 문장
_SENTENCE = re.compile(
    r"[ \t]*(?=[^<>.。!?\s])[^<>.。!?\n]*?(?:%s)[^<>.。!?\n]*[.。!?]?" % PATTERN.pattern, re.I)


def find(text: str) -> list:
    """걸린 문장 목록 (중복 제거, 순서 유지)."""
    return list(dict.fromkeys(m.group(0).strip() for m in _SENTENCE.finditer(text or "")))


def _drop(text: str) -> str:
    for _ in range(10):
        new = _SENTENCE.sub("", text)
        if new == text:
            break
        text = new
    return re.sub(r"<p>\s*</p>", "", re.sub(r"<p>[ \t]+", "<p>", text))


def scrub(client, model: str, text: str, style: str = "") -> str:
    """상투 문장만 다시 쓰게 해서 바꾼다. 실패하거나 다시 쓴 문장도 걸리면 그 문장을 지운다."""
    bad = find(text)
    if not bad:
        return text
    print(f"[info] AI 상투 표현 {len(bad)}문장 고쳐 씀: {bad[:3]}")
    try:
        prompt = (
            "아래 문장들은 블로그 글에서 AI 가 쓴 티가 나는 상투 표현이 들어간 문장이다.\n"
            f"{RULE}\n\n각 문장을 같은 뜻·같은 말투{('(' + style + ')') if style else ''}로, "
            "상투 표현 없이 자연스럽게 다시 쓴다. 사실·숫자는 바꾸지 않는다. "
            "HTML 태그가 있으면 그대로 둔다.\n"
            "JSON 문자열 배열 하나만 출력한다 (입력과 같은 순서·같은 개수).\n\n"
            + json.dumps(bad, ensure_ascii=False))
        resp = client.messages.create(model=model, max_tokens=2000,
                                      messages=[{"role": "user", "content": prompt}])
        raw = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        fixed = json.loads(re.search(r"\[.*\]", raw, re.S).group(0))
        if len(fixed) == len(bad):
            for old, new in zip(bad, fixed):
                if isinstance(new, str) and new.strip() and not PATTERN.search(new):
                    text = text.replace(old, new.strip())
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] 상투 표현 고쳐 쓰기 실패, 해당 문장을 지웁니다 ({type(exc).__name__}: {exc})")
    return _drop(text)


def scrub_fields(client, model: str, post: dict, keys, style: str = "") -> dict:
    """post 의 문자열 필드(또는 문자열 리스트·faq 리스트)를 한꺼번에 검사한다."""
    for key in keys:
        val = post.get(key)
        if isinstance(val, str):
            post[key] = scrub(client, model, val, style)
        elif isinstance(val, list):
            for i, item in enumerate(val):
                if isinstance(item, str):
                    val[i] = scrub(client, model, item, style)
                elif isinstance(item, dict):
                    for k, v in item.items():
                        if isinstance(v, str) and k not in ("photo_hint", "layout"):
                            item[k] = scrub(client, model, v, style)
    return post
