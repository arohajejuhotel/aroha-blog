"""주제에 맞는 도표 이미지를 고른다.

사진은 분위기를 전하고, 도표는 사진으로 전할 수 없는 정보(거리·시각·요금)를 전한다.
검색 사용자가 원하는 건 대개 후자라, 도표가 들어간 글이 체류 시간과 인용률이 높다.
"""


def pick(all_figures: list, topic: dict, lang: str, limit: int = 2) -> list:
    """주제 태그와 겹치는 도표를 고른다. 없으면 빈 목록."""
    wanted = set(topic.get("img", []))
    kw = f"{topic.get('kw_ko', '')} {topic.get('kw_en', '')}".lower()

    scored = []
    for fig in all_figures:
        if fig["lang"] != lang:
            continue
        tags = set(fig["tags"])
        score = len(wanted & tags)
        # 키워드에 도표 주제가 직접 등장하면 가산점
        for t in tags:
            if t.replace("-", " ") in kw:
                score += 2
        if score > 0:
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
