"""주제에 맞는 도표 이미지를 고른다.

사진은 분위기를 전하고, 도표는 사진으로 전할 수 없는 정보(거리·시각·요금)를 전한다.
검색 사용자가 원하는 건 대개 후자라, 도표가 들어간 글이 체류 시간과 인용률이 높다.
"""


# 도표는 정보를 전달할 때만 의미가 있다. 모든 글에 붙이면 오히려 상투적으로 보인다.
# 주제와 확실히 맞물릴 때(점수 2 이상)만 고르고, 한 글에 하나를 기본으로 한다.
MIN_SCORE = 2


def pick(all_figures: list, topic: dict, lang: str, limit: int = 1) -> list:
    """주제와 확실히 관련된 도표만 고른다. 애매하면 빈 목록을 돌려준다."""
    wanted = set(topic.get("img", []))
    kw = f"{topic.get('kw_ko', '')} {topic.get('kw_en', '')}".lower()
    angle = f"{topic.get('ko', '')} {topic.get('en', '')}".lower()

    scored = []
    for fig in all_figures:
        if fig["lang"] != lang:
            continue
        tags = set(fig["tags"])
        score = len(wanted & tags)
        # 핵심 키워드나 주제 방향에 도표 주제가 직접 등장하면 확실히 관련 있다
        for t in tags:
            word = t.replace("-", " ")
            if word in kw:
                score += 3
            elif word in angle:
                score += 1
        if score >= MIN_SCORE:
            scored.append((score, fig))

    scored.sort(key=lambda s: -s[0])
    return [f for _, f in scored[:limit]]


def to_refs(figs: list, base_url: str) -> list:
    """생성 모델에게 넘길 도표 참조 목록."""
    return [
        {
            "id": f"FIG{n + 1}",
            "url": f"{base_url}/figures/{f['file']}",
            "caption": f["caption"],
            "about": ", ".join(f["tags"]),
        }
        for n, f in enumerate(figs)
    ]
