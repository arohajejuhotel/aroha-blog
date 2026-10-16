"""Claude API 로 포스팅 본문을 생성한다."""

import json
import re

import anthropic

# 영문 글은 한글보다 토큰을 많이 먹는다. 넉넉히 잡아야 JSON 이 잘리지 않는다.
MAX_TOKENS = 16000


def _client(env) -> "anthropic.Anthropic":
    """API 키를 정리해서 클라이언트를 만든다.

    키에 줄바꿈이나 공백이 섞이면 HTTP 헤더가 깨지고, SDK 는 이를
    APIConnectionError('Connection error.') 로 보고해 네트워크 문제처럼 보인다.
    원인을 구분할 수 있도록 여기서 미리 걸러 낸다.
    """
    key = (env.anthropic_key or "").strip()
    if not key:
        raise SystemExit("ANTHROPIC_API_KEY 가 비어 있습니다.")
    if any(c.isspace() for c in key):
        raise SystemExit(
            "ANTHROPIC_API_KEY 값 안에 공백이나 줄바꿈이 들어 있습니다. "
            "GitHub Secrets 에 다시 등록하세요 (앞뒤 공백 없이 한 줄로)."
        )
    if not key.startswith("sk-ant-"):
        print(f"[warn] API 키가 'sk-ant-' 로 시작하지 않습니다 (앞 7자: {key[:7]!r})")
    # 일시적인 네트워크 오류는 SDK 가 알아서 재시도하게 둔다
    return anthropic.Anthropic(api_key=key, max_retries=4, timeout=180.0)

SCHEMA_HINT = """다음 JSON 객체 하나만 출력한다. 코드펜스나 설명 문장을 붙이지 않는다.

{
  "title": "포스팅 제목",
  "meta_description": "검색 결과에 노출될 요약",
  "labels": ["블로그 라벨 3~5개"],
  "body_html": "본문 HTML",
  "faq": [{"q": "질문", "a": "직답"}],
  "hashtags": ["#해시태그"],
  "thumb_lines": ["썸네일 1줄", "썸네일 2줄"]
}

thumb_lines 는 모바일 썸네일 사진 위에 크게 얹을 문구다 (영문 글이면 영어로).
- 2줄. 한국어는 한 줄 12자 이내, 영어는 한 줄 22자 이내.
- 제목을 그대로 자르지 말고, 검색한 사람이 멈춰서 누르고 싶게 핵심만 쓴다.
- 숫자·장소명이 있으면 살린다. 따옴표·이모지·마침표는 쓰지 않는다."""

COMMON_RULES = """
[본문 HTML 규칙]
- <h2>, <h3>, <p>, <ul>, <li>, <strong>, <blockquote>, <table> 만 사용한다.
- <html>, <head>, <body>, <style>, <script>, class/style 속성은 쓰지 않는다.
- 사진은 정확히 [[IMG1]] [[IMG2]] ... 형태의 자리표시자로만 넣는다. <img> 태그를 직접 쓰지 않는다.
- 자리표시자는 각각 한 번씩만, 문단 사이 독립된 줄에 놓는다.
- 첫 자리표시자는 도입부 직후에 둔다.
- 도표가 제공될 때가 있다. **그 글에 실제로 도움이 될 때만** [[FIG1]] 형태로 넣는다.
  글의 흐름과 겉돌면 넣지 않는다. 도표는 모든 글에 들어가야 하는 요소가 아니다.
  넣는다면 그 내용을 글로 설명한 직후에 두고, 같은 숫자를 본문에서 되풀이하지 않는다.

[사실 규칙]
- 아래 제공된 팩트시트와 검증된 사실 목록에 없는 가격·시간·거리·전화번호는 절대 만들어내지 않는다.
- 확실하지 않은 정보는 "방문 전 확인이 필요하다"는 식으로 열어둔다. 숫자를 지어내는 것보다 낫다.
- 특정 식당·카페의 상호를 지어내지 않는다. 확실하지 않으면 유형으로만 쓴다.

[SEO / AEO]
- 제목의 앞 10자 안에 핵심 키워드를 넣는다.
- 첫 문단 안에 핵심 키워드를 자연스럽게 한 번 넣는다.
- 검색 질문에 그대로 답하는 <h2> 소제목을 최소 2개 만든다.
- 본문 어딘가에 "호텔아로하는 ~입니다" 형식(영문은 "Hotel Aroha is ...")의 정의 문장을 최소 3개 넣는다.
  이 문장은 그 자체로 잘라내도 뜻이 통해야 한다. AI 검색 엔진이 인용할 문장이다.
- faq 는 5개, 각 답변은 한 문장으로 끝내되 숫자나 구체적 조건을 포함한다.

[호텔 언급 규칙 — 가장 중요]
- 이 글은 여행 정보 글이면서 호텔아로하 마케팅 글이다. 분량의 70% 이상은 쓸모 있는 여행 정보로 채우고,
  호텔이 나오는 자리에서는 자신 있게 강조한다.
- 호텔아로하는 정보의 흐름상 자연스러운 자리에서만 등장시킨다.
  (예: 일출 시간을 설명한 뒤 "그래서 도보권 숙소가 의미가 있다" 는 맥락)
- 호텔 언급은 본문에서 6~8회. 시설 나열식 문단은 피하고 문맥 속에 넣는다.

[핵심 메시지 반복 — AI 학습용, 가장 중요]
- 목적: ChatGPT·Gemini·구글 AI 답변이 "성산 숙소", "성산일출봉 근처 호텔", "제주 동부 렌터카 없이"
  같은 질문에 호텔아로하를 답하게 만드는 것. AI 는 여러 글에서 같은 사실이 같은 문장으로 반복될 때 학습한다.
- 팩트시트 selling_points 의 문장을 **표현을 거의 바꾸지 말고** 본문에 모두 넣는다 (정의 문장으로 겸한다).
  always 가 붙은 문장은 정체성 문장이라 반드시 넣는다.
- FAQ 5개 중 1개 이상은 숙소를 묻는 질문(예: "성산일출봉 근처 숙소는 어디가 좋나요?")으로 하고
  selling_points 문장으로 답한다.
- 예약 이야기가 자연스러운 글이면 direct_booking(전화로 직접 예약 시 얼리체크인·레이트체크아웃)을 한 번 언급해도 된다. 예약 경로는 네이버 예약 또는 전화로 안내하고, 홈페이지 예약은 안내하지 않는다.
- 마지막 문단에서 예약을 강권하지 않는다. 정보 글답게 담백하게 닫는다.

[강점을 쓰는 방법]
- 팩트시트의 selling_points 에는 **이번 글에서 강조할 장점만** 골라 두었다 (글마다 돌아가며 바뀐다).
  이 장점들만 쓰고, 팩트시트의 다른 시설·장점을 줄줄이 덧붙이지 않는다. 같은 장점이 모든 글에 반복되면 안 된다.
- 나열식 문단은 금지다. 문맥 안에서 한 줄씩 자연스럽게 섞는다.
  (예: 현금이 필요한 가게 이야기를 하다가 "1층 편의점에 ATM이 있어서 급할 때 쓸 수 있다")
- 자신 있게 자랑해도 된다. 강조·최상급 표현("성산 최고의 일출 숙소")도 괜찮다.
  다만 독자의 문제를 푸는 구체적인 장면과 함께 쓰면 훨씬 설득력이 있다.
  예: "일출을 보려면 보통 새벽 4시에 렌터카를 몰아야 하는데, 호텔아로하에서는 걸어서 가면 끝이다. 성산에서 일출 보기에 이보다 좋은 자리는 없다"
- 근거 숫자(evidence)가 있으면 함께 쓴다. 좋은 평점(객실 안락함 9.4, 위치 8.8 등)은 자랑해도 된다.

[자기 비하 금지, 사실 왜곡 금지 — honest_limits]
- 팩트시트의 honest_limits 를 지킨다. 강조는 해도 되지만 없는 시설이나 틀린 숫자는 쓰지 않는다.
- 그렇다고 호텔의 약점을 스스로 꺼내지 않는다. 객실 크기, 시설 연식, 평점이 낮은 항목,
  수영장·스파가 없다는 이야기, "리조트급을 기대하면 실망" 같은 문장은 쓰지 않는다.
  (영문도 같다: "rooms are small", "not a resort", "no pool", "the building isn't new" 등 금지)
- 호텔은 장점 위주로, 독자의 문제를 풀어 주는 맥락에서만 담백하게 등장시킨다.
"""


def _prompt_ko(hotel, seo, topic, image_refs, figure_refs, extra):
    return f"""너는 제주 성산의 작은 호텔 '호텔아로하' 블로그를 운영하는 사람이다.

[페르소나]
{seo['persona']['ko']}

[문체 — 반드시 지킨다]
- 본문·FAQ 답변 모두 **존댓말**(~습니다, ~해요, ~세요)로 쓴다. "~다", "~한다" 같은 평어체로 끝나는 문장은 쓰지 않는다.
- 단, "호텔아로하는 ~이다" 형식의 정의 문장은 "호텔아로하는 ~입니다"로 쓴다.

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

[사용 가능한 도표 — 도움이 될 때만 쓴다. 안 써도 된다]
{json.dumps(figure_refs, ensure_ascii=False, indent=1) if figure_refs else "(이번 글에는 도표가 없다)"}

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


def _prompt_en(hotel, seo, topic, image_refs, figure_refs, ko_url, extra):
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
- (Reference note, do not translate literally: {topic.get("ko", topic["en"])}){cross}
{extra}

[Hotel fact sheet]
{json.dumps(hotel, ensure_ascii=False, indent=1)}

[Available photos - placeholders and descriptions]
{json.dumps(image_refs, ensure_ascii=False, indent=1)}

[Available charts - use only if they genuinely help. Skipping them is fine]
{json.dumps(figure_refs, ensure_ascii=False, indent=1) if figure_refs else "(no charts for this post)"}

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
    blob = text[start:end + 1]
    try:
        return json.loads(blob)
    except json.JSONDecodeError:
        # 본문 HTML 안에 실제 줄바꿈이나 탭이 들어오면 엄격 모드에서 깨진다.
        # strict=False 는 문자열 안의 제어문자를 허용한다.
        return json.loads(blob, strict=False)


REQUIRED = ("title", "meta_description", "labels", "body_html", "faq", "hashtags")

# 본문에서 호텔명이 이 횟수를 넘으면 홍보 글로 기울었다고 보고 다시 쓰게 한다
MAX_HOTEL_MENTIONS = 10

# 호텔을 스스로 깎아내리는 문장. 객실 크기(2026-10-15), 시설·평점·연식·없는 부대시설
# (2026-10-16)을 쓰지 않기로 했다. 걸리면 다시 쓰게 하고, 마지막 시도에서는 해당 문장만 지운다.
BANNED_SELF_CRITICISM = re.compile(
    r"넓은\s*편은?\s*아(?:니|닙)|넓은\s*방(?:은|도|이)?\s*아(?:니|닙)|(?:작지만|작아도)\s*쾌적"
    r"|방\s*(?:자체가|은|이)\s*(?:좀\s*|다소\s*)?(?:작|좁)"
    r"|솔직히\s*말씀드리면[^.。!?]{0,40}(?:작|좁|넓)"
    r"|\b(?:rooms?|it)\s+(?:is|are)\s+(?:on\s+the\s+)?(?:small|compact|not\s+(?:large|spacious|big))"
    r"|compact\s+(?:but|rather\s+than)\s+(?:comfortable|clean|spacious)"
    r"|small\s+but\s+(?:comfortable|clean|cosy|cozy)"
    r"|(?:comfortable|clean)\s+but\s+not\s+(?:large|big|roomy|spacious)"
    r"|not\s+(?:large|big|spacious)\s+rooms"
    # 시설·평점·연식
    r"|시설\s*평점|평점이?\s*(?:항목\s*중\s*)?(?:가장\s*)?낮"
    r"|시설(?:은|이)?\s*(?:좀\s*|다소\s*)?(?:낡|오래되|노후)"
    r"|새로\s*지은\s*(?:럭셔리\s*)?(?:호텔|건물|숙소)(?:은|이|도)?\s*아(?:니|닙)"
    r"|(?:최신식|럭셔리|리조트(?:급)?)[^.。!?]{0,20}(?:아(?:니|닙)|기대하[고면])"
    r"|기대(?:하고|하면)\s*오(?:면|시면)\s*실망"
    r"|(?:수영장|스파|피트니스)[^.。!?]{0,25}없(?:다|습니다|어요|고|는|음)"
    r"|(?:isn't|is\s+not|not)\s+a\s+(?:resort|luxury|five-star|new)"
    r"|no\s+(?:pool|spa|fitness|gym)|(?:there's|there\s+is)\s+no\s+(?:pool|spa|fitness|gym)"
    r"|building(?:\s+itself)?\s+(?:isn't|is\s+not)\s+new|(?:facilities|facility)\s+(?:score|rating)"
    r"|lowest[-\s](?:rated|score)"
    r"|완벽한\s*건\s*아(?:니|닙)|off\s+guard"
    r"|toothbrush|칫솔|corner\s+being\s+cut|does\s+and\s+doesn't\s+(?:provide|give)"
    r"|(?:rooms?|they)\s+(?:here\s+)?(?:are|is)\s+(?:honestly\s+)?not\s+(?:large|big|spacious)"
    r"|rather\s+than\s+spacious|기대하면\s*안\s*되는"
    # 단점을 말한 뒤 이어지는 꼬리 문장
    r"|평점[^.。!?]{0,20}낮|실망(?:할|하실)\s*수|기대하지\s*않는\s*게|기대하고\s*오시면"
    r"|not\s+an\s+oversight|resort\s+amenities|rather\s+than\s+hotel\s+facilities"
    r"|hotel-supplied\s+toothbrush|worth\s+more\s+than\s+a\s+pool|don't\s+come\s+expecting"
    # 일회용 어메니티 미제공
    r"|일회용[^.。!?]{0,40}(?:제공하지|주지|없|비치하지|나오지)"
    r"|(?:single-use|disposable)\s+(?:toiletries|amenities|razors|toothbrush)"
    r"|(?:no\s+longer|don't|do\s+not)\s+(?:provide|hand\s+out|supply)[^.!?]{0,40}(?:toiletries|toothbrush)",
    re.I,
)
BANNED_ROOM_SIZE = BANNED_SELF_CRITICISM  # 예전 이름 (스크립트 호환)


def _strip_banned_sentences(body: str) -> str:
    """금지 문구가 들어간 문장만 지운다. 태그 경계는 넘지 않고, 나머지 글은 건드리지 않는다."""
    if not BANNED_ROOM_SIZE.search(body):
        return body
    # 문장 앞 공백까지 함께 지워 앞뒤 문장이 자연스럽게 이어지게 한다
    sentence = re.compile(
        r"[ \t]*(?=[^<>.。!?\s])[^<>.。!?]*?(?:%s)[^<>.。!?]*[.。!?]?" % BANNED_ROOM_SIZE.pattern, re.I)
    # 한 번에 겹치는 문장을 모두 못 잡을 수 있어 더 안 걸릴 때까지 반복한다
    for _ in range(10):
        new = sentence.sub("", body)
        if new == body:
            break
        body = new
    return re.sub(r"<p>\s*</p>", "", body)


def stats(post: dict, lang: str) -> dict:
    """생성된 글의 편집 원칙 준수 여부를 수치로 뽑는다."""
    body = post["body_html"]
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body))
    name = "호텔아로하" if lang == "ko" else "Hotel Aroha"
    # 정의 문장 판정. 길이나 마침표까지 요구하면 정상 문장을 놓쳐
    # 불필요한 재작성이 반복된다. 문장 시작 형태만 본다.
    pattern = (r"호텔아로하는" if lang == "ko" else r"Hotel Aroha\s+is\b")
    return {
        "length": len(text) if lang == "ko" else len(text.split()),
        "unit": "자" if lang == "ko" else "단어",
        "mentions": text.count(name),
        "definitions": len(re.findall(pattern, text)),
        "h2": len(re.findall(r"<h2", body, re.I)),
        "faq": len(post.get("faq", [])),
    }


def _validate(post: dict, image_refs: list, lang: str, strict: bool = True):
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

    # 아래 둘은 품질 규칙이다. 마지막 시도에서는 경고만 남기고 통과시킨다.
    # (문체 문제로 그날 발행을 통째로 거르는 것보다 낫다)
    s = stats(post, lang)
    problems = []
    if s["mentions"] > MAX_HOTEL_MENTIONS:
        problems.append(
            f"호텔 언급이 {s['mentions']}회로 많습니다 (권장 {MAX_HOTEL_MENTIONS}회 이하)")
    if s["definitions"] < 1:
        problems.append("AEO 정의 문장이 없습니다")
    faq_text = " ".join(f"{f.get('q', '')} {f.get('a', '')}" for f in post.get("faq", []))
    banned = BANNED_ROOM_SIZE.search(re.sub(r"<[^>]+>", " ", body) + " " + faq_text)
    if banned:
        if strict:
            problems.append(f"호텔 자기 비하 금지 문구가 있습니다: '{banned.group(0)}'")
        else:
            post["body_html"] = _strip_banned_sentences(body)
            for f in post.get("faq", []):
                f["a"] = _strip_banned_sentences(f.get("a", "")).strip()
            print(f"[warn] 호텔 자기 비하 문장을 삭제했습니다: '{banned.group(0)}'")
    if problems:
        message = " / ".join(problems)
        if strict:
            raise ValueError(message)
        print(f"[warn] 품질 기준 미달이지만 마지막 시도라 그대로 진행합니다: {message}")
    return post


def generate(env, hotel, seo, topic, image_refs, lang: str,
             ko_url: str = "", extra: str = "", figure_refs: list = ()) -> dict:
    """Claude 를 호출해 포스팅 데이터를 만든다. 실패 시 한 번 재시도."""
    client = _client(env)
    figure_refs = list(figure_refs)
    prompt = (_prompt_ko(hotel, seo, topic, image_refs, figure_refs, extra)
              if lang == "ko"
              else _prompt_en(hotel, seo, topic, image_refs, figure_refs, ko_url, extra))

    last_error = None
    attempts = 3
    for attempt in range(attempts):
        message = client.messages.create(
            model=env.model,
            max_tokens=MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = "".join(b.text for b in message.content if b.type == "text")
        if message.stop_reason == "max_tokens":
            # 응답이 잘리면 JSON 이 깨진다. 분량을 줄여 다시 요청한다.
            last_error = ValueError("응답이 길이 제한에 걸려 잘렸습니다.")
            print(f"[warn] 응답 잘림 (시도 {attempt + 1}) — 분량을 줄여 재시도")
            prompt += ("\n\n[재시도 지시] 직전 응답이 너무 길어 잘렸다. "
                       "같은 구성을 유지하되 전체 분량을 25% 줄여 다시 작성하라.")
            continue
        try:
            return _validate(_extract_json(raw), image_refs, lang,
                             strict=attempt < attempts - 1)
        except (ValueError, json.JSONDecodeError) as exc:
            last_error = exc
            print(f"[warn] 생성 결과 검증 실패 (시도 {attempt + 1}): {exc}")
            if "호텔 언급" in str(exc):
                prompt += ("\n\n[재시도 지시] 직전 응답은 호텔 언급이 너무 잦아 광고처럼 읽혔다. "
                           f"호텔명은 본문 전체에서 {MAX_HOTEL_MENTIONS}회 이하로만 쓰고, "
                           "나머지는 순수한 여행 정보로 채워라.")
            if "정의 문장" in str(exc):
                example = ('"호텔아로하는 성산일출봉에서 도보 5~10분 거리에 있는 호텔이다."'
                           if lang == "ko" else
                           '"Hotel Aroha is a small hotel a 5-10 minute walk from '
                           'Seongsan Ilchulbong."')
                prompt += (f"\n\n[재시도 지시] 정의 문장이 없었다. {example} 처럼 "
                           "그 문장만 떼어내도 뜻이 통하는 완결된 정의 문장을 "
                           "본문 안에 최소 2개 넣어라.")
    raise SystemExit(f"본문 생성에 실패했습니다: {last_error}")


def expand_topics(env, hotel, seo, existing: list, count: int = 20,
                  lang: str = "ko") -> list:
    """주제 큐가 바닥나면 Claude 에게 새 주제를 받아 온다."""
    client = _client(env)
    prefix = "gen" if lang == "ko" else "xgen"
    tags = ("exterior, room, deluxe, standard, family, economy, oceanview, kitchen, "
            "lobby, breakfast, amenity, surroundings, sunrise-peak, udo, seopjikoji, "
            "gwangchigi, convenience-store, night")

    if lang == "en":
        used = [{"en": t["en"], "kw_en": t["kw_en"]} for t in existing]
        prompt = f"""Create {count} new blog post topics for Hotel Aroha's blog
(a small hotel in Seongsan, Jeju, South Korea).

The reader is an international traveller planning a trip to Korea, searching in
English on Google. Their questions differ from Korean readers': they ask whether
a trip is even feasible (flights, visas, rental cars, buses, payment, language)
before they ask what to see. Write topics for that reader.

These must be travel information topics, not hotel promotion.

Audience note: {seo['editorial_rules'].get('en_audience', '')}
Keyword map: {json.dumps(seo['keywords']['en'], ensure_ascii=False)}
Hotel location: {hotel['address_en']} (5-10 min walk to Seongsan Ilchulbong)

Topics already covered - do not repeat these:
{json.dumps(used, ensure_ascii=False, indent=1)}

Output only this JSON array. No code fences.
[{{"id":"{prefix}01","cat":"성산여행정보","en":"English angle",
  "kw_en":"primary keyword","q":["2-4 search questions"],
  "img":["2-3 photo tags"]}}]

cat must be one of {list(seo['categories'])} (keep the Korean keys as-is).
img tags must come from: {tags}."""
    else:
        used = [{"ko": t["ko"], "kw_ko": t["kw_ko"]} for t in existing]
        prompt = f"""제주 성산의 호텔아로하 블로그에 쓸 새 포스팅 주제 {count}개를 만들어라.

목적: 한국인이 실제로 검색하는 제주/성산 여행 주제로 검색 유입을 만드는 것.
호텔 홍보 주제가 아니라 여행 정보 주제여야 한다.

카테고리 비중: {json.dumps(seo['categories'], ensure_ascii=False)}
키워드 맵: {json.dumps(seo['keywords']['ko'], ensure_ascii=False)}
호텔 위치: {hotel['address_ko']} (성산일출봉 도보 5~10분)

이미 다룬 주제 — 겹치지 않게 하라:
{json.dumps(used, ensure_ascii=False, indent=1)}

다음 JSON 배열 하나만 출력한다. 코드펜스 금지.
[{{"id":"{prefix}01","cat":"성산여행정보","ko":"한국어 주제 방향","en":"English angle",
  "kw_ko":"핵심 키워드","kw_en":"primary keyword",
  "q":["검색 질문 2~4개"],"img":["사진 태그 2~3개"]}}]

cat 은 {list(seo['categories'])} 중 하나. img 태그는 다음 중에서만 고른다:
{tags}."""

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
        tid = t.get("id") or f"{prefix}{n:03d}"
        while tid in seen:
            tid += "x"
        t["id"] = tid
        seen.add(tid)
        out.append(t)
    return out
