"""포스팅에 쓸 사진을 태그 기준으로 고른다.

같은 사진이 매번 반복되지 않도록, 이미 사용한 횟수가 적은 사진을 먼저 쓴다.
"""

import random
from collections import Counter


def _score(image, usage: Counter, wanted: list) -> tuple:
    """정렬 키: (사용횟수, -태그일치수, 랜덤)"""
    hits = sum(1 for t in wanted if t in image["tags"])
    return (usage.get(image["file"], 0), -hits, random.random())


def pick(manifest: list, wanted_tags: list, count: int, usage: Counter) -> list:
    """wanted_tags 에 맞는 사진을 count 장 고른다. 모자라면 태그 범위를 넓힌다."""
    chosen = []
    seen = set()

    # 1순위: 요청된 태그를 순서대로 훑으며 태그당 최소 1장씩 확보
    for tag in wanted_tags:
        pool = [i for i in manifest if tag in i["tags"] and i["file"] not in seen]
        if not pool:
            continue
        pool.sort(key=lambda i: _score(i, usage, wanted_tags))
        chosen.append(pool[0])
        seen.add(pool[0]["file"])
        if len(chosen) >= count:
            return chosen

    # 2순위: 요청 태그 중 아무거나 걸리는 사진
    pool = [
        i for i in manifest
        if i["file"] not in seen and any(t in i["tags"] for t in wanted_tags)
    ]
    pool.sort(key=lambda i: _score(i, usage, wanted_tags))
    for img in pool:
        if len(chosen) >= count:
            return chosen
        chosen.append(img)
        seen.add(img["file"])

    # 3순위: 호텔 대표 이미지로 채운다
    fallback = [
        i for i in manifest
        if i["file"] not in seen
        and any(t in i["tags"] for t in ("exterior", "surroundings", "lobby", "room"))
    ]
    fallback.sort(key=lambda i: _score(i, usage, ["exterior"]))
    for img in fallback:
        if len(chosen) >= count:
            break
        chosen.append(img)
        seen.add(img["file"])

    return chosen


def usage_counter(state: dict) -> Counter:
    counter = Counter()
    for post in state.get("posts", []):
        for f in post.get("images", []):
            counter[f] += 1
    return counter


def to_refs(images: list, base_url: str, lang: str) -> list:
    """생성 모델에게 넘길 이미지 참조 목록."""
    return [
        {
            "id": f"IMG{n + 1}",
            "url": f"{base_url}/{img['file']}",
            "alt": img["alt_ko"] if lang == "ko" else img["alt_en"],
            "orientation": img["orientation"],
            "tags": img["tags"],
        }
        for n, img in enumerate(images)
    ]
