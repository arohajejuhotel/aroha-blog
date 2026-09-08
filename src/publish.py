"""매일 아침 실행되는 메인 스크립트.

    python -m src.publish              # 한글 + 영어 두 편 발행
    python -m src.publish --dry-run    # 발행하지 않고 HTML 만 out/ 에 저장
    python -m src.publish --draft      # 초안으로만 올림 (검수용)
    python -m src.publish --lang ko    # 한 언어만
    python -m src.publish --topic s03  # 특정 주제 강제
"""

import argparse
import datetime as dt
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import images, render, settings, writer  # noqa: E402
from src.blogger import Blogger  # noqa: E402

KST = ZoneInfo("Asia/Seoul")
OUT = settings.ROOT / "out"


def choose_topic(all_topics: list, state: dict, forced: str, month: int) -> dict:
    if forced:
        for t in all_topics:
            if t["id"] == forced:
                return t
        raise SystemExit(f"주제 id '{forced}' 를 찾을 수 없습니다.")

    done = {p["topic_id"] for p in state.get("posts", [])}
    remaining = [t for t in all_topics if t["id"] not in done]
    if not remaining:
        return {}

    # 이번 달에 맞는 계절 주제를 우선한다
    seasonal = [t for t in remaining if month in t.get("months", [])]
    if seasonal:
        return seasonal[0]
    # 계절이 지정된 주제는 제철이 아니면 뒤로 미룬다
    evergreen = [t for t in remaining if not t.get("months")]
    return (evergreen or remaining)[0]


def season_note(month: int, lang: str) -> str:
    if lang == "ko":
        return f"\n- 오늘은 {month}월이다. 지금 계절에 실제로 해당하는 이야기로 쓴다."
    return f"\n- It is currently month {month} in Jeju. Write for this season."


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
    all_topics = settings.topics()
    state = settings.state()
    manifest = settings.manifest()

    today = dt.datetime.now(KST)
    month = today.month

    topic = choose_topic(all_topics, state, args.topic, month)
    if not topic:
        print("[info] 남은 주제가 없어 Claude 로 새 주제를 생성합니다.")
        new_topics = writer.expand_topics(env, hotel, seo, all_topics)
        all_topics += new_topics
        settings.save_topics(all_topics)
        print(f"[info] 새 주제 {len(new_topics)}개 추가")
        topic = choose_topic(all_topics, state, "", month)

    print(f"[info] {today:%Y-%m-%d} 주제: [{topic['cat']}] {topic['ko']}")

    usage = images.usage_counter(state)
    picked = images.pick(manifest, topic["img"],
                         seo["editorial_rules"]["images_per_post"], usage)
    print(f"[info] 사진 {len(picked)}장: {[p['file'] for p in picked]}")

    client = None
    if not args.dry_run:
        client = Blogger(env.blog_id, env.client_id, env.client_secret,
                         env.refresh_token)

    langs = ["ko", "en"] if args.lang == "both" else [args.lang]
    results = {}
    ko_url = ""

    for lang in langs:
        refs = images.to_refs(picked, env.image_base, lang)
        post = writer.generate(env, hotel, seo, topic, refs, lang,
                               ko_url=ko_url, extra=season_note(month, lang))
        html = render.build(post, hotel, topic, refs, lang, cross_url=ko_url)
        print(f"[info] ({lang}) 제목: {post['title']}  본문 {len(html):,}자")

        if args.dry_run:
            OUT.mkdir(exist_ok=True)
            path = OUT / f"{today:%Y-%m-%d}-{topic['id']}-{lang}.html"
            path.write_text(
                f"<!doctype html><meta charset='utf-8'>"
                f"<title>{post['title']}</title>"
                f"<div style='max-width:760px;margin:40px auto;font-family:system-ui'>"
                f"<h1>{post['title']}</h1>{html}</div>",
                encoding="utf-8")
            print(f"[dry-run] {path}")
            results[lang] = {"title": post["title"], "url": "", "id": ""}
            continue

        created = client.create_post(post["title"], html, post["labels"],
                                     draft=args.draft)
        url = created.get("url", "")
        print(f"[ok] ({lang}) 발행: {url or '초안'}")
        results[lang] = {"title": post["title"], "url": url,
                         "id": created["id"], "labels": post["labels"]}
        if lang == "ko":
            ko_url = url
            ko_post = (post, refs)

    # 한국어 글에 영어 글 링크를 나중에 채워 넣는다
    if not args.dry_run and "ko" in results and "en" in results and results["en"]["url"]:
        post, refs = ko_post
        html = render.build(post, hotel, topic, refs, "ko",
                            cross_url=results["en"]["url"])
        client.patch_post(results["ko"]["id"], content=html)
        print("[ok] 한국어 글에 영문 버전 링크 추가")

    if not args.dry_run:
        state.setdefault("posts", []).append({
            "date": f"{today:%Y-%m-%d}",
            "topic_id": topic["id"],
            "category": topic["cat"],
            "images": [p["file"] for p in picked],
            "ko": results.get("ko", {}),
            "en": results.get("en", {}),
        })
        settings.save_state(state)
        print(f"[ok] state 업데이트 (누적 {len(state['posts'])}일)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
