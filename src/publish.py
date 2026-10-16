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

from src import figures, images, render, settings, thumbnail, tour_photos, writer  # noqa: E402
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


def in_window(topic: dict, day: str) -> bool:
    """기간 한정 주제(전국체전 등)의 발행 가능 기간인지. window 가 없으면 항상 참."""
    window = topic.get("window")
    return not window or window[0] <= day <= window[1]


def choose_topic(pool: list, done: set, forced: str, month: int, day: str = "") -> dict:
    if forced:
        for t in pool:
            if t["id"] == forced:
                return t
        return {}

    day = day or dt.datetime.now(KST).strftime("%Y-%m-%d")
    # 기간이 지난 이벤트 주제는 다시 쓰지 않는다
    remaining = [t for t in pool if t["id"] not in done and in_window(t, day)]
    if not remaining:
        return {}

    # 기간 한정 주제가 기간 안이면 가장 먼저 쓴다
    timely = [t for t in remaining if t.get("window")]
    if timely:
        return timely[0]

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
            "works, how check-in works and what the hotel offers.")


def facts_note(topic: dict, lang: str) -> str:
    """시기성 주제는 확인된 사실만 쓰도록 근거 목록을 함께 넘긴다."""
    facts = topic.get("facts")
    if not facts:
        return ""
    head = ("\n[확인된 사실 — 이 목록에 없는 일정·장소·숫자는 지어내지 않는다]"
            if lang == "ko" else
            "\n[Verified facts - do not invent dates, venues or numbers beyond this list]")
    return head + "".join(f"\n- {f}" for f in facts)


def scope_note(seo: dict, lang: str) -> str:
    scope = seo.get("editorial_rules", {}).get("scope")
    if not scope:
        return ""
    if lang == "ko":
        return f"\n- {scope}"
    return ("\n- Topics cover all of Jeju, not only Seongsan. When the topic is in the west or "
            "south, mention Hotel Aroha only once or twice as an east-side base, never forced.")


# 같은 블로그에 하루 이 편수를 넘겨 발행하지 않는다 (정기 2편 + 특집 1편)
MAX_POSTS_PER_DAY = 3


def posts_on(state: dict, day: str) -> int:
    """그날 이미 공개 발행한 글 수 (언어 합산)."""
    return sum(1 for p in state.get("posts", []) if p.get("date") == day
               for lang in ("ko", "en") if p.get(lang, {}).get("url"))


POINTS_PER_POST = 3  # always 문장 외에 글마다 돌아가며 넣을 장점 수


def pick_points(hotel: dict, state: dict, lang: str) -> list:
    """글마다 다른 장점을 쓰도록, 지금까지 덜 쓴 장점부터 고른다."""
    import random
    used = {}
    for post in state.get("posts", []):
        for pid in post.get(f"{lang}_points", []):
            used[pid] = used.get(pid, 0) + 1
    pool = hotel.get("selling_points", [])
    always = [p for p in pool if p.get("always")]
    rest = sorted((p for p in pool if not p.get("always")),
                  key=lambda p: (used.get(p["id"], 0), random.random()))
    return always + rest[:POINTS_PER_POST]


def hotel_for_post(hotel: dict, points: list, lang: str) -> dict:
    """생성 모델에 넘길 팩트시트. 이번 글의 장점만 남겨 같은 자랑이 반복되지 않게 한다."""
    h = {k: v for k, v in hotel.items() if k not in ("selling_points", "strengths")}
    h["selling_points"] = [{"id": p["id"], "always": bool(p.get("always")), "text": p[lang]}
                           for p in points]
    return h


# 장소 키워드가 없는 예전 주제는 사진 태그로 장소를 짐작한다
TAG_PLACES = {"sunrise-peak": "성산일출봉", "udo": "우도", "seopjikoji": "섭지코지",
              "gwangchigi": "광치기해변"}
KTO_PER_POST = 3


def topic_places(topic: dict) -> list:
    if topic.get("place"):
        return topic["place"]
    places = [TAG_PLACES[t] for t in topic.get("img", []) if t in TAG_PLACES]
    return places or ["성산일출봉"]


def used_photo_urls(state: dict) -> set:
    used = set()
    for post in state.get("posts", []):
        for key in ("ko_photos", "en_photos"):
            used.update(post.get(key, []))
    return used


def make_thumbnail(env, topic, post, lang, picked_hotel, used, day, dry_run):
    """모바일 세로 썸네일을 만들어 주소를 돌려준다. 실패해도 발행은 계속한다."""
    try:
        places = topic_places(topic)
        src = tour_photos.thumbnail_source(env.tour_key, places, used)
        if src:
            photo, credit = thumbnail.load_photo(src["url"]), tour_photos._credit(lang, src["license"])
        else:
            # 변형 가능한 관광공사 사진이 없으면 호텔이 직접 찍은 사진을 쓴다
            own = next((p for p in picked_hotel if p.get("orientation") != "portrait"),
                       picked_hotel[0])
            photo, credit = thumbnail.load_photo(str(settings.ROOT / "assets" / "img" / own["file"])), ""
        lines = post.get("thumb_lines") or thumbnail.fallback_lines(post["title"])
        out = thumbnail.THUMB_DIR / f"{day}-{topic['id']}-{lang}.jpg"
        thumbnail.make(lines, topic["cat"], lang, photo, credit, out,
                       badge=tuple(topic.get("badge", ())) if lang == "ko" else ())
        if dry_run:
            return {"url": out.resolve().as_uri(), "alt": post["title"], "credit": credit}
        return {"url": thumbnail.publish(out), "alt": post["title"], "credit": credit}
    except Exception as exc:  # noqa: BLE001 — 썸네일 때문에 그날 발행을 놓치지 않는다
        print(f"[warn] ({lang}) 썸네일 생성 실패, 썸네일 없이 진행: {type(exc).__name__}: {exc}")
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--draft", action="store_true")
    ap.add_argument("--lang", choices=["ko", "en", "both"], default="both")
    ap.add_argument("--topic", default="")
    ap.add_argument("--force", action="store_true",
                    help="하루 발행 한도(MAX_POSTS_PER_DAY)를 넘겨서라도 발행")
    args = ap.parse_args()

    env = settings.Env()
    hotel = settings.hotel()
    seo = settings.seo()
    state = settings.state()
    manifest = settings.manifest()
    all_figures = settings.figures()

    today = dt.datetime.now(KST)
    month = today.month
    langs = ["ko", "en"] if args.lang == "both" else [args.lang]

    client = None
    if not args.dry_run:
        client = Blogger(env.blog_id, env.client_id, env.client_secret,
                         env.refresh_token)

    entry = {"date": f"{today:%Y-%m-%d}"}
    results = {}

    published_today = posts_on(state, entry["date"])
    for lang in langs:
        # 하루에 너무 많이 올리면 Blogger 가 스팸 블로그로 의심할 수 있다
        limited = not (args.dry_run or args.draft or args.force)
        if limited and published_today >= MAX_POSTS_PER_DAY:
            print(f"[warn] ({lang}) 오늘 이미 {published_today}편 발행 — 하루 한도 "
                  f"{MAX_POSTS_PER_DAY}편이라 건너뜁니다 (--force 로 무시 가능)")
            continue
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
        # 글 주제 장소의 실제 사진(한국관광공사)을 먼저 찾고, 나머지를 호텔 사진으로 채운다
        used_photos = used_photo_urls(state)
        kto = tour_photos.find(env.tour_key, topic_places(topic), lang, KTO_PER_POST, used_photos)
        total = seo["editorial_rules"]["images_per_post"]
        usage = images.usage_counter(state)
        picked = images.pick(manifest, topic["img"], max(2, total - len(kto)), usage)
        refs = images.to_refs(picked, env.image_base, lang)
        refs += tour_photos.to_refs(kto, len(refs) + 1, lang)
        print(f"[info] ({lang}) 사진: 관광공사 {len(kto)}장 + 호텔 {len(picked)}장")

        chosen_figs = figures.pick(all_figures, topic, lang)
        fig_refs = figures.to_refs(chosen_figs, env.image_base.rsplit("/", 1)[0])
        if fig_refs:
            print(f"[info] ({lang}) 도표 {len(fig_refs)}개: "
                  f"{[f['id'] for f in chosen_figs]}")

        extra = season_note(month, lang) + facts_note(topic, lang) + scope_note(seo, lang)
        points = pick_points(hotel, state, lang)
        print(f"[info] ({lang}) 이번 글 장점: {[p['id'] for p in points]}")
        post = writer.generate(env, hotel_for_post(hotel, points, lang), seo, topic, refs, lang,
                               extra=extra, figure_refs=fig_refs)
        thumb = make_thumbnail(env, topic, post, lang, picked, used_photos,
                               f"{today:%Y-%m-%d}", args.dry_run)
        html = render.build(post, hotel, topic, refs, lang, figs=fig_refs, thumb=thumb)
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
        if not args.draft:
            published_today += 1
        if args.draft:
            settings.add_pending_title(created["id"], post["title"])

        results[lang] = {"title": post["title"], "url": url, "id": created["id"],
                         "labels": post["labels"]}
        entry[f"{lang}_topic"] = topic["id"]
        entry[f"{lang}_images"] = [p["file"] for p in picked]
        entry[f"{lang}_photos"] = [p["url"] for p in kto]
        entry[f"{lang}_points"] = [p["id"] for p in points]
        if thumb:
            entry[f"{lang}_thumb"] = thumb["url"]
        entry[lang] = results[lang]

        # 발행할 때마다 즉시 기록한다.
        # 두 언어를 다 끝낸 뒤 한 번에 저장하면, 뒤쪽에서 실패했을 때 앞서 발행한
        # 글의 기록이 사라져 다음 날 같은 주제를 또 발행하게 된다. (실제로 발생)
        # 같은 날 두 번째 실행(특집 글 추가 발행 등)이 아침 기록을 덮어쓰지 않도록
        # 이번 실행에서 만든 기록만 갱신한다.
        posts = state.setdefault("posts", [])
        if posts and posts[-1] is entry:
            pass
        else:
            posts.append(entry)
        settings.save_state(state)
        print(f"[ok] ({lang}) 기록 저장 (누적 {len(posts)}일)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
