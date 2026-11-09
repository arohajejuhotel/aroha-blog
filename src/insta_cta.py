# -*- coding: utf-8 -*-
"""인스타 캡션 끝에 붙는 행동 유도 한 줄 (2026-11-04).

팔로우·저장·계정 태그·언급·사진 태그·공유를 날마다 돌아가며 하나씩 붙인다.
같은 날 캐러셀과 릴스는 서로 다른 행동을 부탁하도록 순서를 어긋나게 둔다.
"""
import datetime as dt

ACCOUNT = "@hotel_aroha_jeju"

# 행동마다 문구 2개. 같은 행동이 돌아올 때 문구가 바뀐다.
CTAS = [
    ("follow", [f"제주 동쪽 소식이 궁금하시면 {ACCOUNT} 팔로우해 두세요 🌅",
                f"성산에서 매일 보는 제주, {ACCOUNT} 팔로우하고 같이 보세요 🌊"]),
    ("save", ["다음 제주 여행 때 꺼내 보시게 저장해 두세요 🔖",
              "가기 전에 다시 보시려면 저장 버튼 눌러 두세요 🔖"]),
    ("tag_account", [f"제주 여행 사진 올리실 때 {ACCOUNT} 태그해 주세요. 꼭 보러 갈게요 🙌",
                     f"이 근처 다녀오시면 게시물에 {ACCOUNT} 태그해 주세요 🙌"]),
    ("mention", [f"스토리에 {ACCOUNT} 언급해 주시면 반갑게 보러 갈게요 💬",
                 f"성산 여행 스토리 올리실 때 {ACCOUNT} 언급 한 번 부탁드려요 💬"]),
    ("photo_tag", [f"아로하에서 찍은 사진이 있다면 사진에 {ACCOUNT} 태그해 주세요 📸",
                   f"객실 창밖, 일출 사진 찍으셨다면 {ACCOUNT} 태그해서 보여 주세요 📸"]),
    ("share", ["같이 가고 싶은 분께 공유해 주세요 💌",
               "이번 제주 여행 함께할 분께 이 게시물 보내 주세요 💌"]),
]

# 같은 날 캐러셀과 릴스가 겹치지 않게 릴스는 절반만큼 밀린 행동을 쓴다
OFFSET = {"carousel": 0, "reel": len(CTAS) // 2}


def line(day: str, kind: str = "carousel") -> str:
    """day(YYYY-MM-DD)와 게시물 종류로 그날의 행동 유도 문구를 고른다."""
    n = dt.date.fromisoformat(day).toordinal() + OFFSET.get(kind, 0)
    _, texts = CTAS[n % len(CTAS)]
    return texts[(n // len(CTAS)) % len(texts)]


# 릴스·클립은 늘 '저장' + '팔로우' 두 줄을 함께 부탁한다 (2026-11-09). 문구만 날마다 돌아간다.
REEL_SAVE = ["🔖 다음 제주 여행 때 다시 보시게 저장해 두세요.",
             "🔖 가기 전에 꺼내 보시려면 저장 버튼 눌러 두세요."]
REEL_FOLLOW = [f"👉 {ACCOUNT} 팔로우하시면 성산·제주 동쪽 여행 정보를 계속 받아보실 수 있어요.",
               f"👉 {ACCOUNT} 팔로우해 두시면 다음 코스도 놓치지 않으세요."]
# 네이버 클립: 계정 아이디 없이 (채널 팔로우)
CLIP_SAVE = ["🔖 다음 제주 여행 때 다시 보시게 저장해 두세요.",
             "🔖 가기 전에 꺼내 보시려면 저장해 두세요."]
CLIP_FOLLOW = ["👉 팔로우하시면 성산·제주 동쪽 여행 정보를 계속 받아보실 수 있어요.",
               "👉 팔로우해 두시면 다음 코스도 놓치지 않으세요."]


def _insert(caption: str, add_lines: list) -> str:
    lines = caption.rstrip().split("\n")
    # 예약 안내('프로필 링크') 줄, 해시태그 줄, '사진:' 출처 줄 중 처음 나오는 곳 앞에 넣는다
    at = next((i for i, l in enumerate(lines)
               if "프로필 링크" in l or l.lstrip().startswith(("#", "사진:", "사진 :"))), len(lines))
    while at > 0 and not lines[at - 1].strip():
        at -= 1
    gap = [""] if at < len(lines) and lines[at].strip() else []  # 아래 해시태그와 한 줄 띄운다
    return "\n".join(lines[:at] + [""] + add_lines + gap + lines[at:])


def add_reel(caption: str, day: str, kind: str = "reel") -> str:
    """릴스(kind='reel')·네이버 클립(kind='clip') 캡션에 저장·팔로우 두 줄을 넣는다."""
    n = dt.date.fromisoformat(day).toordinal()
    save, follow = (CLIP_SAVE, CLIP_FOLLOW) if kind == "clip" else (REEL_SAVE, REEL_FOLLOW)
    return _insert(caption, [save[n % len(save)], follow[n % len(follow)]])


def add(caption: str, day: str, kind: str = "carousel") -> str:
    """캡션 본문 끝(해시태그·사진 출처 줄 앞)에 행동 유도 한 줄을 넣는다."""
    cta = line(day, kind)
    lines = caption.rstrip().split("\n")
    # 예약 안내('프로필 링크') 줄, 해시태그 줄, '사진:' 출처 줄 중 처음 나오는 곳 앞에 넣는다
    at = next((i for i, l in enumerate(lines)
               if "프로필 링크" in l or l.lstrip().startswith(("#", "사진:", "사진 :"))), len(lines))
    while at > 0 and not lines[at - 1].strip():
        at -= 1
    return "\n".join(lines[:at] + [cta] + lines[at:])
