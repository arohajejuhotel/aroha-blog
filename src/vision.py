# -*- coding: utf-8 -*-
"""후보 사진을 Claude 가 직접 보고 썸네일·본문용으로 고른다 (2026-10-16).

검색 결과 첫 번째 사진을 그대로 쓰면 주제와 어긋나거나, 글자를 얹기 어려운 복잡한
사진이 걸린다. 후보 미리보기(작은 이미지 주소)를 최대 10장 보여 주고 고르게 한다.
실패하면 None 을 돌려주고, 호출 쪽은 원래 순서대로 쓴다.
"""
import json

PROMPT = """블로그 글에 넣을 사진을 고른다.

[글 제목] {title}
[글 내용 요약] {summary}

위 사진 {n}장(0번부터)을 보고 고른다.
- thumb: 썸네일 배경 1장. 글 주제와 분위기가 맞고, 위쪽 절반에 큰 제목 글자를 얹어도 보기 좋은
  (복잡하지 않은) 사진. 사진 안에 글자·로고·워터마크가 크게 있는 것은 피한다.
- body: 본문에 넣을 사진 {k}장. 글 내용과 실제로 관련 있고, 서로 비슷하지 않은 것. thumb 와 겹치지 않게.
- 주제와 관련 없는 사진(엉뚱한 장소·음식·연출이 과한 사진)은 고르지 않는다. 맞는 게 모자라면 body 를 적게 골라도 된다.

다음 JSON 하나만 출력한다: {{"thumb": 번호, "body": [번호...], "reason": "한 줄"}}"""


def choose(client, model: str, title: str, summary: str, image_urls: list, k: int):
    urls = image_urls[:10]
    if len(urls) < 2:
        return None
    content = [{"type": "image", "source": {"type": "url", "url": u}} for u in urls]
    content.append({"type": "text", "text": PROMPT.format(title=title, summary=summary[:600],
                                                         n=len(urls), k=k)})
    try:
        resp = client.messages.create(model=model, max_tokens=800,
                                      messages=[{"role": "user", "content": content}])
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        pick = json.loads(text[text.index("{"): text.rindex("}") + 1])
        thumb = int(pick["thumb"])
        body = [int(i) for i in pick.get("body", []) if int(i) != thumb and 0 <= int(i) < len(urls)][:k]
        if not 0 <= thumb < len(urls):
            return None
        print(f"  사진 선택: 썸네일 {thumb}번, 본문 {body} — {pick.get('reason', '')}")
        return {"thumb": thumb, "body": body}
    except Exception as exc:
        print(f"  [경고] 사진 선택 실패, 검색 순서대로 사용 ({type(exc).__name__})")
        return None
