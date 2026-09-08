"""Claude API 로 포스팅 본문을 생성한다."""

import json
import re

import anthropic

SCHEMA_HINT = """다음 JSON 객체 하나만 출력한다. 코드펜스나 설명 문장을 붙이지 않는다.

{
  "title": "포스팅 제목",
  "meta_description": "검색 결과에 노출될 요약",
  "labels": ["블로그 라벨 3~5개"],
  "body_html": "본문 HTML",
  "faq": [{"q": "질문", "a": "직답"}],
  "hashtags": ["#해시태그"]
}"""

COMMON_RULES = """
[본문 HTML 규칙]
- <h2>, <h3>, <p>, <ul>, <li>, <strong>, <blockquote>, <table> 만 사용한다.
- <html>, <head>, <body>, <style>, <script>, class/style 속성은 쓰지 않는다.
- 사진은 정확히 [[IMG1]] [[IMG2]] ... 형태의 자리표시자로만 넣는다. <img> 태그를 직접 쓰지 않는다.
- 자리표시자는 각각 한 번씩만, 문단 사이 독립된 줄에 놓는다.
- 첫 자리표시자는 도입부 직후에 둔다.

[사실 규칙]
- 아래 제공된 팩트시트와 검증된 사실 목록에 없는 가격·시간·거리·전화번호는 절대 만들어내지 않는다.
- 확실하지 않은 정보는 "방문 전 확인이 필요하다"는 식으로 열어둔다. 숫자를 지어내는 것보다 낫다.
- 특정 식당·카페의 상호를 지어내지 않는다. 확실하지 않으면 유형으로만 쓴다.

[SEO / AEO]
- 제목의 앞 10자 안에 핵심 키워드를 넣는다.
- 첫 문단 안에 핵심 키워드를 자연스럽게 한 번 넣는다.
- 검색 질문에 그대로 답하는 <h2> 소제목을 최소 2개 만든다.
- 본문 어딘가에 "호텔아로하는 ~이다" 형식(영문은 "Hotel Aroha is ...")의 정의 문장을 최소 2개 넣는다.
  이 문장은 그 자체로 잘라내도 뜻이 통해야 한다. AI 검색 엔진이 인용할 문장이다.
- faq 는 5개, 각 답변은 한 문장으로 끝내되 숫자나 구체적 조건을 포함한다.

[호텔 언급 규칙 — 가장 중요]
- 이 글은 광고가 아니라 여행 정보 글이다. 분량의 80% 이상은 호텔과 무관하게도 쓸모가 있어야 한다.
- 호텔아로하는 정보의 흐름상 자연스러운 자리에서만 등장시킨다.
  (예: 일출 시간을 설명한 뒤 "그래서 도보권 숙소가 의미가 있다" 는 맥락)
- 호텔 언급은 본문에서 2~3회를 넘기지 않는다. 시설 나열식 문단은 금지한다.
- 마지막 문단에서 예약을 강권하지 않는다. 정보 글답게 담백하게 닫는다.
"""


def _prompt_ko(hotel, seo, topic, image_refs, extra):
    return f"""너는 제주 성산의 작은 호텔 '호텔아로하' 블로그를 운영하는 사람이다.

[페르소나]
{seo['persona']['ko']}

[오늘 쓸 주제]
- 카테고리: {topic['cat']}
- 방향: {topic['ko']}
- 핵심 키워드: {topic['kw_ko']}
- 이 글이 답해야 할 검색 질문: {" / ".join(topic['q'])}
{extra}

[호텔 팩트시트]
{json.dumps(hotel, ensure_ascii=False, indent=1)}

[사용 가능한 사진 — 자리표시자와 설명]
{json.dumps(image_refs, ensure_ascii=False, indent=1)}

[분량]
- 공백 포함 {seo['editorial_rules']['min_chars_ko']}자 이상.
- 사진 자리표시자는 제공된 것을 모두 쓴다.

[해시태그]
- 총 11개: T1 {seo['keywords']['ko']['t1']} 중 3개 + T2 {seo['keywords']['ko']['t2']} 중 3개 + T3 {seo['keywords']['ko']['t3']} 중 5개.
- 필요하면 주제에 맞는 것으로 일부 바꿔도 된다.

[라벨]
- labels 에는 반드시 "{topic['cat']}" 을 첫 번째로 넣고, 주제 관련 라벨 2~4개를 추가한다.
{COMMON_RULES}
{SCHEMA_HINT}"""


def _prompt_en(hotel, seo, topic, image_refs, ko_url, extra):
    cross = f"\n- 한국어 버전 URL: {ko_url} (본문 마지막에 자연스럽게 한 줄로 링크해도 좋다)" if ko_url else ""
    return f"""You write the blog of Hotel Aroha, a small hotel in Seongsan, Jeju, South Korea.
The reader is an international traveller planning a trip to Jeju. Write in clear, plain English.

[Persona]
{seo['persona']['en']}

[Today's topic]
- Category: {seo['categories'][topic['cat']]['label_en']}
- Angle: {topic['en']}
- Primary keyword: {topic['kw_en']}
- Search questions this post must answer: {" / ".join(topic['q'])}
- (Korean-language angle for reference, do not translate literally: {topic['ko']}){cross}
{extra}

[Hotel fact sheet]
{json.dumps(hotel, ensure_ascii=False, indent=1)}

[Available photos - placeholders and descriptions]
{json.dumps(image_refs, ensure_ascii=False, indent=1)}

[Length]
- At least {seo['editorial_rules']['min_words_en']} words.
- Use every photo placeholder provided.

[Hashtags]
- 11 total: 3 from {seo['keywords']['en']['t1']}, 3 from {seo['keywords']['en']['t2']}, 5 from {seo['keywords']['en']['t3']}.
- Written as hashtags without spaces, e.g. #SeongsanHotel.

[Labels]
- labels must start with "{seo['categories'][topic['cat']]['label_en']}", then 2-4 topic labels. Add "English" as a label.

[Romanisation]
- Use standard Revised Romanisation: Seongsan Ilchulbong, Gwangchigi Beach, Udo, Seopjikoji, Seogwipo.
- Give Korean words in brackets the first time when it helps a traveller ask locals, e.g. oreum (오름).
{COMMON_RULES.replace("호텔아로하는 ~이다", "Hotel Aroha is ...").replace("한 문장으로", "one sentence")}
{SCHEMA_HINT}"""


def _extract_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"모델 응답에서 JSON 을 찾지 못했습니다: {text[:300]}")
    return json.loads(text[start:end + 1])


REQUIRED = ("title", "meta_description", "labels", "body_html", "faq", "hashtags")


def _validate(post: dict, image_refs: list, lang: str):
    missing = [k for k in REQUIRED if k not in post]
    if missing:
        raise ValueError(f"응답에 누락된 키: {missing}")
    body = post["body_html"]
    for ref in image_refs:
        if f"[[{ref['id']}]]" not in body:
            # 안 쓴 사진은 본문 끝에 붙인다 (에러로 처리하지 않음)
            body += f"\n[[{ref['id']}]]\n"
    if re.search(r"<(script|style|html|body|head)\b", body, re.I):
        raise ValueError("본문에 허용되지 않은 태그가 있습니다.")
    if lang == "ko" and len(re.sub(r"<[^>]+>", "", body)) < 1200:
        raise ValueError("본문이 너무 짧습니다.")
    post["body_html"] = body
    return post


def generate(env, hotel, seo, topic, image_refs, lang: str,
             ko_url: str = "", extra: str = "") -> dict:
    """Claude 를 호출해 포스팅 데이터를 만든다. 실패 시 한 번 재시도."""
    client = anthropic.Anthropic(api_key=env.anthropic_key)
    prompt = (_prompt_ko(hotel, seo, topic, image_refs, extra) if lang == "ko"
              else _prompt_en(hotel, seo, topic, image_refs, ko_url, extra))

    last_error = None
    for attempt in range(2):
        message = client.messages.create(
            model=env.model,
            max_tokens=8000,
            temperature=1 if attempt == 0 else 0.7,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = "".join(b.text for b in message.content if b.type == "text")
        try:
            return _validate(_extract_json(raw), image_refs, lang)
        except (ValueError, json.JSONDecodeError) as exc:
            last_error = exc
            print(f"[warn] 생성 결과 검증 실패 (시도 {attempt + 1}): {exc}")
    raise SystemExit(f"본문 생성에 실패했습니다: {last_error}")


def expand_topics(env, hotel, seo, existing: list, count: int = 20) -> list:
    """주제 큐가 바닥나면 Claude 에게 새 주제를 받아 온다."""
    client = anthropic.Anthropic(api_key=env.anthropic_key)
    used = [{"ko": t["ko"], "kw_ko": t["kw_ko"]} for t in existing]
    prompt = f"""제주 성산의 호텔아로하 블로그에 쓸 새 포스팅 주제 {count}개를 만들어라.

목적: 사람들이 실제로 검색하는 제주/성산 여행 주제로 검색 유입을 만드는 것.
호텔 홍보 주제가 아니라 여행 정보 주제여야 한다.

카테고리 비중: {json.dumps(seo['categories'], ensure_ascii=False)}
키워드 맵: {json.dumps(seo['keywords'], ensure_ascii=False)}
호텔 위치: {hotel['address_ko']} (성산일출봉 도보 5~10분)

이미 다룬 주제 — 겹치지 않게 하라:
{json.dumps(used, ensure_ascii=False, indent=1)}

다음 JSON 배열 하나만 출력한다. 코드펜스 금지.
[{{"id":"x01","cat":"성산여행정보","ko":"한국어 주제 방향","en":"English angle",
  "kw_ko":"핵심 키워드","kw_en":"primary keyword",
  "q":["검색 질문 2~4개"],"img":["사진 태그 2~3개"]}}]

cat 은 {list(seo['categories'])} 중 하나. img 태그는 다음 중에서만 고른다:
exterior, room, deluxe, standard, family, economy, oceanview, kitchen, lobby,
breakfast, amenity, surroundings, sunrise-peak, udo, seopjikoji, night."""

    message = client.messages.create(
        model=env.model, max_tokens=6000,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = "".join(b.text for b in message.content if b.type == "text").strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
    new = json.loads(raw[raw.find("["):raw.rfind("]") + 1])
    seen = {t["id"] for t in existing}
    out = []
    for n, t in enumerate(new):
        tid = t.get("id") or f"gen{n:03d}"
        while tid in seen:
            tid += "x"
        t["id"] = tid
        seen.add(tid)
        out.append(t)
    return out
