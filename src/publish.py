"""매일 아침 실행되는 메인 스크립트.

한국어와 영어는 검색 의도가 달라 주제 풀을 따로 쓴다.
 - 한국어: config/topics.json     (성산 맛집, 물때, 주차 등)
 - 영어:   config/topics_en.json  (렌터카 필요 여부, 버스, 결제, 일정 등)

    python -m src.publish              # 한글 + 영어 각 1편
    python -m src.publish --dry-run    # 발행하지 않고 HTML 만 out/ 에 저장
    python -m src.publish --draft      # 초안으로만 올림 (검수용)
    python -m src.publish --lang en    # 한 언어만
    python -m src.publish --topic x02  # 특정 주제 강제 (양쪽 풀에서 id 로 찾음)
"""

import argparse
import datetime as dt
import re
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import images, render, settings, writer  # noqa: E402
from src.blogger import Blogger  # noqa: E402

KST = ZoneInfo("Asia/Seoul")
OUT = settings.ROOT / "out"


def done_ids(state: dict, lang: str) -> set:
    """이미 다룬 주제 id. 언어별로 따로 센다."""
    key = f"{lang}_topic"
    done = set()
    for post in state.get("posts", []):
        if post.get(key):
            done.add(post[key])
        # 주제 풀을 분리하기 전에 쌓인 기록 (한 주제를 두 언어로 썼다)
        elif post.get("topic_id"):
            done.add(post["topic_id"])
    return done


def choose_topic(pool: list, done: set, forced: str, month: int) -> dict:
    if forced:
        for t in pool:
            if t["id"] == forced:
                return t
        return {}

    remaining = [t for t in pool if t["id"] not in done]
    if not remaining:
        return {}

    # 이번 달에 맞는 계절 주제를 우선한다
    seasonal = [t for t in remaining if month in t.get("months", [])]
    if seasonal:
        return seasonal[0]
    # 제철이 아닌 계절 주제는 뒤로 미룬다
    evergreen = [t for t in remaining if not t.get("months")]
    return (evergreen or remaining)[0]


def permalink_title(topic: dict, lang: str) -> str:
    """주소로 쓸 영문 제목.

    Blogger 는 발행되는 순간의 제목으로 주소를 정한다. 한글 제목만으로는
    영문 슬러그가 만들어지지 않아 주소에 숫자만 남는다.
    """
    base = re.sub(r"[^a-zA-Z0-9\s-]", " ", topic["kw_en"]).strip()
    base = re.sub(r"\s+", " ", base)
    return f"{base} guide" if lang == "en" else f"{base} {topic['id']}"


def season_note(month: int, lang: str) -> str:
    if lang == "ko":
        return f"\n- 오늘은 {month}월이다. 지금 계절에 실제로 해당하는 이야기로 쓴다."
    return (f"\n- It is currently month {month} in Jeju. Write for this season."
            "\n- The reader is planning a trip from outside Korea. Explain what a "
            "Korean traveller would take for granted: how to pay, whether English "
            "works, what a hotel does and does not provide.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--draft", action="store_true")
    ap.add_argument("--lang", choices=["ko", "en", "both"], default="both")
    ap.add_argument("--topic", default="")
    args = ap.parse_args()

    env = settings.Env()
    hotel = settings.hotel()
    seo = settings.seo()
    state = settings.state()
    manifest = settings.manifest()

    today = dt.datetime.now(KST)
    month = today.month
    langs = ["ko", "en"] if args.lang == "both" else [args.lang]

    client = None
    if not args.dry_run:
        client = Blogger(env.blog_id, env.client_id, env.client_secret,
                         env.refresh_token)

    entry = {"date": f"{today:%Y-%m-%d}"}
    results = {}

    for lang in langs:
        pool = settings.topics(lang)
        topic = choose_topic(pool, done_ids(state, lang), args.topic, month)

        if not topic and args.topic:
            print(f"[warn] ({lang}) 주제 id '{args.topic}' 가 이 언어 풀에 없어 건너뜁니다.")
            continue

        if not topic:
            print(f"[info] ({lang}) 남은 주제가 없어 Claude 로 새 주제를 생성합니다.")
            new_topics = writer.expand_topics(env, hotel, seo, pool, lang=lang)
            pool = pool + new_topics
            (settings.save_topics_en if lang == "en" else settings.save_topics)(pool)
            print(f"[info] ({lang}) 새 주제 {len(new_topics)}개 추가")
            topic = choose_topic(pool, done_ids(state, lang), "", month)

        label = topic.get("ko") or topic["en"]
        print(f"[info] ({lang}) {today:%Y-%m-%d} 주제: [{topic['cat']}] {label}")

        # 사진은 언어별로 따로 고른다 (주제가 다르므로)
        usage = images.usage_counter(state)
        picked = images.pick(manifest, topic["img"],
                             seo["editorial_rules"]["images_per_post"], usage)
        refs = images.to_refs(picked, env.image_base, lang)

        post = writer.generate(env, hotel, seo, topic, refs, lang,
                               extra=season_note(month, lang))
        html = render.build(post, hotel, topic, refs, lang)
        s = writer.stats(post, lang)
        print(f"[info] ({lang}) 제목: {post['title']}")
        print(f"[info] ({lang}) 분량 {s['length']:,}{s['unit']} / 호텔 언급 {s['mentions']}회"
              f" / 정의문장 {s['definitions']}개 / 소제목 {s['h2']}개 / FAQ {s['faq']}개")

        if args.dry_run:
            OUT.mkdir(exist_ok=True)
            path = OUT / f"{today:%Y-%m-%d}-{topic['id']}-{lang}.html"
            path.write_text(
                f"<!doctype html><meta charset='utf-8'>"
                f"<title>{post['title']}</title>"
                f"<div style='max-width:760px;margin:40px auto;font-family:system-ui'>"
                f"<h1>{post['title']}</h1>{html}</div>", encoding="utf-8")
            print(f"[dry-run] {path}")
            continue

        created = client.create_post(post["title"], html, post["labels"],
                                     draft=args.draft,
                                     permalink_title=permalink_title(topic, lang))
        url = created.get("url", "")
        print(f"[ok] ({lang}) 발행: {url or '초안'}")
        if args.draft:
            settings.add_pending_title(created["id"], post["title"])

        results[lang] = {"title": post["title"], "url": url, "id": created["id"],
                         "labels": post["labels"]}
        entry[f"{lang}_topic"] = topic["id"]
        entry[f"{lang}_images"] = [p["file"] for p in picked]
        entry[lang] = results[lang]

    if not args.dry_run and results:
        state.setdefault("posts", []).append(entry)
        settings.save_state(state)
        print(f"[ok] state 업데이트 (누적 {len(state['posts'])}일)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
