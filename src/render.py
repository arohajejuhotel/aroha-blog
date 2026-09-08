"""생성된 본문을 최종 Blogger HTML 로 조립한다.

- [[IMGn]] 자리표시자 -> <figure><img> (lazy loading, alt 포함)
- FAQ 섹션 + 예약 안내 박스 + 해시태그
- JSON-LD (Article / FAQPage / Hotel) — AEO·리치결과용
"""

import html
import json
import re

C = {
    "cream": "#F4F1EC",
    "ocean": "#3A3530",
    "teal": "#0A7A72",
    "mint": "#3ECAC0",
    "gold": "#E8C547",
}

TEXT = {
    "ko": {
        "faq_heading": "자주 묻는 질문",
        "info_heading": "호텔아로하 기본 정보",
        "address": "주소",
        "phone": "전화",
        "checkin": "체크인 / 체크아웃",
        "walk": "도보 거리",
        "booking": "네이버 예약",
        "booking_cta": "객실 확인하기",
        "map": "네이버 지도에서 보기",
        "other_lang": "English version of this post",
    },
    "en": {
        "faq_heading": "Frequently asked questions",
        "info_heading": "Hotel Aroha at a glance",
        "address": "Address",
        "phone": "Phone",
        "checkin": "Check-in / Check-out",
        "walk": "On foot",
        "booking": "Booking",
        "booking_cta": "Check availability",
        "map": "See it on the map",
        "other_lang": "이 글의 한국어 버전 보기",
    },
}


def _figure(url: str, alt: str) -> str:
    alt = html.escape(alt, quote=True)
    return (
        f'<figure style="margin:28px 0;text-align:center;">'
        f'<img src="{url}" alt="{alt}" loading="lazy" '
        f'style="max-width:100%;height:auto;border-radius:10px;" />'
        f'<figcaption style="font-size:13px;color:#8a8178;margin-top:8px;">{alt}</figcaption>'
        f"</figure>"
    )


def _figure_block(url: str, caption: str) -> str:
    cap = html.escape(caption, quote=True)
    return (
        f'<figure style="margin:30px 0;text-align:center;">'
        f'<img src="{url}" alt="{cap}" loading="lazy" '
        f'style="max-width:100%;height:auto;border:1px solid #e0d9cf;border-radius:10px;" />'
        f'<figcaption style="font-size:13px;color:#8a8178;margin-top:8px;">{cap}</figcaption>'
        f"</figure>"
    )


def _insert_figures(body: str, figs: list) -> str:
    for f in figs:
        body = body.replace(f"[[{f['id']}]]", _figure_block(f["url"], f["caption"]))
    # 모델이 쓰지 않은 도표는 본문 끝(FAQ 앞)에 붙인다
    for f in figs:
        if f["url"] not in body:
            body += "\n" + _figure_block(f["url"], f["caption"])
    return re.sub(r"\[\[FIG\d+\]\]", "", body)


def _insert_images(body: str, refs: list) -> str:
    for ref in refs:
        body = body.replace(f"[[{ref['id']}]]", _figure(ref["url"], ref["alt"]))
    # 혹시 남은 자리표시자는 제거
    return re.sub(r"\[\[IMG\d+\]\]", "", body)


def _faq_block(faq: list, lang: str) -> str:
    t = TEXT[lang]
    items = "".join(
        f'<div style="border-bottom:1px solid #e4ded5;padding:14px 0;">'
        f'<p style="margin:0 0 6px;font-weight:700;color:{C["ocean"]};">Q. {html.escape(f["q"])}</p>'
        f'<p style="margin:0;color:#5a534c;line-height:1.7;">A. {html.escape(f["a"])}</p>'
        f"</div>"
        for f in faq
    )
    return (
        f'<h2 style="margin-top:44px;">{t["faq_heading"]}</h2>'
        f'<div style="background:{C["cream"]};border-radius:12px;padding:8px 22px 18px;">{items}</div>'
    )


def _info_block(hotel: dict, lang: str) -> str:
    t = TEXT[lang]
    addr = hotel["address_ko"] if lang == "ko" else hotel["address_en"]
    walk = (hotel["walking_distance_ko"] if lang == "ko"
            else hotel["walking_distance_en"])[:3]
    rows = [
        (t["address"], html.escape(addr)),
        (t["phone"], hotel["phone"]),
        (t["checkin"], f'{hotel["checkin"]} / {hotel["checkout"]}'),
        (t["walk"], " · ".join(html.escape(w) for w in walk)),
    ]
    body = "".join(
        f'<tr><td style="padding:7px 14px 7px 0;color:{C["teal"]};font-weight:700;'
        f'white-space:nowrap;vertical-align:top;">{k}</td>'
        f'<td style="padding:7px 0;color:#4a443e;">{v}</td></tr>'
        for k, v in rows
    )
    # 언어별 예약 채널: 한국어는 네이버 예약(직접예약), 영어는 OTA(리뷰 축적)
    cta = hotel.get("cta", {}).get(lang, {})
    primary = cta.get("primary") or {"label": t["booking_cta"], "url": hotel["booking_url"]}
    secondary = cta.get("secondary") or {"label": t["map"], "url": hotel["map_url"]}

    buttons = (
        f'<a href="{primary["url"]}" rel="noopener nofollow" '
        f'style="display:inline-block;background:{C["teal"]};color:#fff;text-decoration:none;'
        f'padding:11px 22px;border-radius:8px;font-weight:700;">'
        f'{html.escape(primary["label"])}</a>'
    )
    if secondary.get("url"):
        buttons += (
            f'&nbsp;&nbsp;<a href="{secondary["url"]}" rel="noopener nofollow" '
            f'style="color:{C["teal"]};font-size:14px;">'
            f'{html.escape(secondary["label"])}</a>'
        )

    return (
        f'<div style="border:1px solid #e0d9cf;border-radius:12px;padding:22px;margin:40px 0 24px;">'
        f'<p style="margin:0 0 14px;font-size:13px;letter-spacing:.12em;text-transform:uppercase;'
        f'color:{C["teal"]};font-weight:700;">{t["info_heading"]}</p>'
        f'<table style="width:100%;border-collapse:collapse;font-size:15px;"><tbody>{body}</tbody></table>'
        f'<p style="margin:20px 0 0;">{buttons}</p>'
        f"</div>"
    )


def _cross_link(url: str, lang: str) -> str:
    if not url:
        return ""
    t = TEXT[lang]
    return (
        f'<p style="margin:8px 0 24px;font-size:14px;">'
        f'<a href="{url}" hreflang="{"en" if lang == "ko" else "ko"}" '
        f'style="color:{C["teal"]};">{t["other_lang"]} &rarr;</a></p>'
    )


def _hashtags(tags: list) -> str:
    clean = " ".join(t if t.startswith("#") else f"#{t}" for t in tags)
    return (
        f'<p style="margin:26px 0 0;color:#9a9188;font-size:13px;line-height:2;">'
        f"{html.escape(clean)}</p>"
    )


def _jsonld(post: dict, hotel: dict, topic: dict, lang: str,
            image_urls: list, cross_url: str) -> str:
    locale = "ko-KR" if lang == "ko" else "en-US"
    graph = [
        {
            "@type": "BlogPosting",
            "headline": post["title"],
            "description": post["meta_description"],
            "inLanguage": locale,
            "image": image_urls[:4],
            "keywords": topic["kw_ko"] if lang == "ko" else topic["kw_en"],
            "author": {"@type": "Organization", "name": hotel["name_ko"]},
            "publisher": {"@type": "Organization", "name": hotel["name_ko"]},
            "about": {"@type": "Hotel", "name":
                      hotel["name_ko"] if lang == "ko" else hotel["name_en"]},
        },
        {
            "@type": "FAQPage",
            "mainEntity": [
                {
                    "@type": "Question",
                    "name": f["q"],
                    "acceptedAnswer": {"@type": "Answer", "text": f["a"]},
                }
                for f in post["faq"]
            ],
        },
        {
            "@type": "Hotel",
            "name": hotel["name_ko"] if lang == "ko" else hotel["name_en"],
            "alternateName": hotel["name_en"] if lang == "ko" else hotel["name_ko"],
            "description": (hotel["concept_ko"] if lang == "ko" else hotel["concept_en"]),
            "telephone": hotel["phone"],
            "email": hotel["email"],
            "address": {
                "@type": "PostalAddress",
                "streetAddress": (hotel["address_ko"] if lang == "ko"
                                  else hotel["address_en"]),
                "addressRegion": "Jeju",
                "addressCountry": "KR",
            },
            "geo": {
                "@type": "GeoCoordinates",
                "latitude": hotel["geo"]["lat"],
                "longitude": hotel["geo"]["lng"],
            },
            "checkinTime": hotel["checkin"],
            "checkoutTime": hotel["checkout"],
            "url": hotel["booking_url"],
            "amenityFeature": [
                {"@type": "LocationFeatureSpecification", "name": a, "value": True}
                for a in (hotel["amenities_ko"] if lang == "ko"
                          else hotel["amenities_en"])
            ],
        },
    ]
    if cross_url:
        graph[0]["sameAs"] = [cross_url]
    data = {"@context": "https://schema.org", "@graph": graph}
    return ('<script type="application/ld+json">'
            + json.dumps(data, ensure_ascii=False) + "</script>")


def build(post: dict, hotel: dict, topic: dict, refs: list, lang: str,
          cross_url: str = "", figs: list = ()) -> str:
    """최종 Blogger 본문 HTML."""
    body = _insert_figures(post["body_html"], list(figs))
    body = _insert_images(body, refs)
    image_urls = [r["url"] for r in refs]
    parts = [
        '<div style="font-size:16px;line-height:1.85;color:#3a3530;">',
        _cross_link(cross_url, lang),
        body,
        _faq_block(post["faq"], lang),
        _info_block(hotel, lang),
        _hashtags(post["hashtags"]),
        "</div>",
        _jsonld(post, hotel, topic, lang, image_urls, cross_url),
    ]
    return "\n".join(p for p in parts if p)
