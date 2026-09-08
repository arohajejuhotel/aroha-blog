"""환경 변수와 설정 파일 로딩."""

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "config"
STATE_DIR = ROOT / "state"
ASSETS_DIR = ROOT / "assets"

STATE_FILE = STATE_DIR / "published.json"
TOPICS_FILE = CONFIG_DIR / "topics.json"
MANIFEST_FILE = ASSETS_DIR / "manifest.json"


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def hotel():
    return _load(CONFIG_DIR / "hotel.json")


def seo():
    return _load(CONFIG_DIR / "seo.json")


def topics():
    return _load(TOPICS_FILE)


def manifest():
    if not MANIFEST_FILE.exists():
        raise SystemExit(
            "assets/manifest.json 이 없습니다. 먼저 scripts/prepare_images.py 를 실행하세요."
        )
    return _load(MANIFEST_FILE)["images"]


def state():
    if not STATE_FILE.exists():
        return {"posts": []}
    return _load(STATE_FILE)


def save_state(data):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8"
    )


def save_topics(data):
    TOPICS_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8"
    )


ENV_FILE = ROOT / ".env"
_dotenv_loaded = False


def load_dotenv() -> None:
    """로컬 실행 편의를 위해 .env 를 환경 변수로 읽어들인다.

    이미 설정된 환경 변수를 덮어쓰지 않는다 (GitHub Actions 의 시크릿이 우선).
    """
    global _dotenv_loaded
    if _dotenv_loaded or not ENV_FILE.exists():
        _dotenv_loaded = True
        return
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'").strip()
        if key and value and key not in os.environ:
            os.environ[key] = value
    _dotenv_loaded = True


def env(name: str, default=None, required: bool = False) -> str:
    load_dotenv()
    value = os.environ.get(name, default)
    # GitHub Secrets 에 붙여넣을 때 줄바꿈·공백이 딸려 들어가는 일이 잦다.
    # 그대로 두면 HTTP 헤더가 깨져 연결 오류처럼 보인다.
    if isinstance(value, str):
        value = value.strip()
    if required and not value:
        raise SystemExit(
            f"환경 변수 {name} 가 설정되지 않았습니다. "
            f"(.env 파일 또는 GitHub Secrets 확인)"
        )
    return value


class Env:
    """실행에 필요한 시크릿/설정 묶음."""

    def __init__(self):
        self.anthropic_key = env("ANTHROPIC_API_KEY", required=True)
        self.model = env("ANTHROPIC_MODEL", "claude-sonnet-5")
        self.blog_id = env("BLOGGER_BLOG_ID", required=True)
        self.client_id = env("GOOGLE_CLIENT_ID", required=True)
        self.client_secret = env("GOOGLE_CLIENT_SECRET", required=True)
        self.refresh_token = env("GOOGLE_REFRESH_TOKEN", required=True)
        # 이미지 CDN 베이스 URL (끝에 / 없이). 예: https://user.github.io/aroha-blog/assets/img
        self.image_base = env("IMAGE_BASE_URL", required=True).rstrip("/")
