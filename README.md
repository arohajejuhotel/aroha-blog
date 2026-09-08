# 호텔아로하 구글 블로그 자동 발행

매일 아침 **07:00 (한국시간)** 에 구글 블로그(Blogger)로 포스팅을 자동 발행한다.
같은 주제를 **한국어 1편 + 영어 1편**으로 발행하고, 두 글을 서로 링크한다.

## 콘텐츠 전략

호텔 홍보 글이 아니라 **사람들이 실제로 검색하는 제주·성산 여행 정보 글**이다.
호텔아로하는 정보의 흐름상 자연스러운 자리에서만 등장한다 (본문 내 2~3회, 분량의 20% 이하).

| 카테고리 | 비중 | 내용 |
|---|---|---|
| 성산여행정보 | 45% | 일출 시간, 우도 페리, 광치기 물때, 주차, 맛집 기준 — SEO 핵심 |
| 제주동부여행 | 35% | 공항 이동, 올레길, 비자림, 계절 콘텐츠 |
| 아로하이야기 | 20% | 객실·운영 관점 (여기서도 정보가 먼저) |

**AEO(AI 검색 노출) 장치** — 포스팅마다 자동으로 들어간다.

- `호텔아로하는 ~이다` 형식의 정의 문장 2개 이상 (AI가 인용하기 좋은 형태)
- 검색 질문에 그대로 답하는 `<h2>` 소제목
- FAQ 5개 + **FAQPage JSON-LD** (구글 리치결과 / AI 답변 인용 대상)
- **Hotel JSON-LD** — 주소·좌표·체크인 시간·편의시설·평점 없는 사실 정보
- **BlogPosting JSON-LD** + 한/영 상호 `sameAs` 링크

사진은 `02_사진` 폴더 원본 110장을 1400px로 리사이즈해 사용하며,
포스팅당 5장을 **덜 쓴 사진부터** 자동 선택해 중복 노출을 줄인다.
모든 사진에 한/영 alt 텍스트가 붙는다 (이미지 검색 유입).

## 구조

```
blog-automation/
├─ config/
│  ├─ hotel.json      호텔 팩트시트 (모델이 사실을 지어내지 못하게 하는 근거)
│  ├─ seo.json        키워드 맵 T1/T2/T3, 편집 원칙, 페르소나
│  └─ topics.json     주제 60개 (= 60일치). 소진되면 Claude가 자동으로 20개씩 보충
├─ assets/
│  ├─ img/            블로그용 리사이즈 사진 110장
│  └─ manifest.json   사진별 태그 + 한/영 alt
├─ src/
│  ├─ publish.py      메인 — 주제 선택 → 생성 → 발행 → 기록
│  ├─ writer.py       Claude 호출 (한/영 프롬프트, 검증, 재시도)
│  ├─ render.py       최종 HTML 조립 + JSON-LD
│  ├─ images.py       사진 선택 로직
│  └─ blogger.py      Blogger API v3 클라이언트
├─ scripts/
│  ├─ prepare_images.py    사진 리사이즈 + manifest 생성
│  ├─ get_refresh_token.py 구글 OAuth 토큰 발급 (최초 1회)
│  └─ find_blog_id.py      블로그 주소 → blogId 조회
├─ state/published.json    발행 이력 (중복 방지 + 사진 순환 근거)
└─ .github/workflows/daily-publish.yml   매일 07:00 KST 실행
```

---

# 세팅 (한 번만)

## 1. 구글 블로그 만들기

1. <https://www.blogger.com> 접속 → 호텔 계정 지메일로 로그인
2. **블로그 만들기** → 제목 `호텔아로하 | 성산 여행의 시작`
3. 주소는 원하는 것으로 (예: `arohajeju.blogspot.com`)
4. 설정 → **언어** 한국어, **검색엔진에 표시** 사용

> 계정 생성과 로그인은 직접 해야 한다.

## 2. Google Cloud — Blogger API 사용 설정

1. <https://console.cloud.google.com> → 새 프로젝트 (이름: `aroha-blog`)
2. **API 및 서비스 → 라이브러리** → `Blogger API v3` 검색 → **사용**
3. **OAuth 동의 화면** → 외부 → 앱 이름 `아로하 블로그 봇`, 지원 이메일 본인
   → **테스트 사용자**에 블로그를 운영할 지메일 주소 추가
4. **사용자 인증 정보 → 사용자 인증 정보 만들기 → OAuth 클라이언트 ID**
   → 애플리케이션 유형 **데스크톱 앱** → 생성
   → **클라이언트 ID** 와 **클라이언트 보안 비밀번호** 복사

## 3. refresh token 발급 (이 PC에서 1회)

```bash
pip install -r requirements.txt
python scripts/get_refresh_token.py --client-id "복사한ID" --client-secret "복사한비밀번호"
```

브라우저가 열리면 블로그 계정으로 로그인하고 허용 →
터미널에 출력되는 `GOOGLE_REFRESH_TOKEN` 값을 복사해 둔다.

> "이 앱은 확인되지 않았습니다" 경고가 뜨면 **고급 → (앱 이름)(으)로 이동** 을 누른다.
> 본인이 만든 앱이고 테스트 사용자에 본인만 등록되어 있으므로 정상이다.

## 4. blogId 확인

```bash
BLOGGER_BLOG_ID=0 GOOGLE_CLIENT_ID=... GOOGLE_CLIENT_SECRET=... GOOGLE_REFRESH_TOKEN=... \
python scripts/find_blog_id.py --whoami
```

출력되는 숫자 ID가 `BLOGGER_BLOG_ID` 다.

## 5. Anthropic API 키

<https://console.anthropic.com> → API Keys → 키 생성 → 결제 수단 등록.
글 한 편당 비용은 수십 원 수준이다 (기본 모델 `claude-sonnet-5`).

## 6. GitHub 저장소 + 이미지 호스팅

Blogger API 는 사진 업로드를 지원하지 않으므로, 사진은 **GitHub Pages** 에서 서빙한다.

```bash
cd "G:/내 드라이브/08.AROHA/blog-automation"
git init && git add -A && git commit -m "init: 호텔아로하 블로그 자동화"
```

<https://github.com/new> 에서 저장소 `aroha-blog` 생성 (**Public** — Pages 무료 사용).
사진 외에 비밀 정보는 저장소에 들어가지 않는다 (`.env` 는 `.gitignore` 처리).

```bash
git remote add origin https://github.com/<깃허브아이디>/aroha-blog.git
git branch -M main && git push -u origin main
```

저장소 **Settings → Pages** → Source: `Deploy from a branch`,
Branch: `main` / `(root)` → Save. 1~2분 뒤 아래 주소로 사진이 열리는지 확인한다.

```
https://<깃허브아이디>.github.io/aroha-blog/assets/img/exterior-hotelout-01-<해시>.jpg
```

## 7. GitHub Secrets / Variables 등록

저장소 **Settings → Secrets and variables → Actions**

**Secrets** (New repository secret)

| 이름 | 값 |
|---|---|
| `ANTHROPIC_API_KEY` | 5단계에서 만든 키 |
| `BLOGGER_BLOG_ID` | 4단계 숫자 ID |
| `GOOGLE_CLIENT_ID` | 2단계 클라이언트 ID |
| `GOOGLE_CLIENT_SECRET` | 2단계 보안 비밀번호 |
| `GOOGLE_REFRESH_TOKEN` | 3단계 토큰 |

**Variables** (Variables 탭 → New repository variable)

| 이름 | 값 |
|---|---|
| `IMAGE_BASE_URL` | `https://<깃허브아이디>.github.io/aroha-blog/assets/img` |
| `ANTHROPIC_MODEL` | `claude-sonnet-5` (선택. 품질을 더 올리려면 `claude-opus-5`) |

## 8. 첫 실행 — 초안으로 검수

저장소 **Actions → Daily blog publish → Run workflow**
→ mode `draft` 선택 → 실행.

Blogger 관리 화면의 **초안**에 한/영 두 편이 올라온다.
읽어 보고 톤·사실관계가 맞으면 발행하고, 이후로는 매일 07:00 에 자동으로 돌아간다.

`dry-run` 을 고르면 발행 없이 HTML 미리보기만 Actions 아티팩트로 받는다.

---

# 일상 운영

## 자동

- 매일 07:00 KST 발행. 주제는 `config/topics.json` 순서대로, 그 달에 맞는 계절 주제 우선.
- 발행 후 `state/published.json` 이 자동 커밋된다 (다음 날 중복 방지).
- 주제 60개가 소진되면 Claude 가 새 주제 20개를 만들어 `topics.json` 에 추가한다.

## 수동 실행

| 하고 싶은 것 | 방법 |
|---|---|
| 특정 주제를 오늘 올리기 | Actions → Run workflow → topic 에 `s03` 입력 |
| 한국어만 | lang `ko` |
| 발행 전 검수 | mode `draft` |
| 글만 확인 | mode `dry-run` |

## 이 PC에서 직접 실행

`.env.example` 를 `.env` 로 복사해 값을 채운 뒤:

```bash
run_local.bat --dry-run
```

## 사진 추가했을 때

`02_사진` 폴더에 사진을 넣고:

```bash
python scripts/prepare_images.py --source "G:/내 드라이브/08.AROHA/02_사진"
git add -A && git commit -m "chore: 사진 추가" && git push
```

## 주제를 직접 추가/수정

`config/topics.json` 을 열어 항목을 추가한다.

```json
{"id":"s28","cat":"성산여행정보","ko":"주제 방향","en":"English angle",
 "kw_ko":"핵심 키워드","kw_en":"primary keyword",
 "q":["검색 질문"],"img":["sunrise-peak","exterior"],"months":[7,8]}
```

`months` 는 선택 사항이며, 해당 월에 우선 발행된다.
`img` 에 쓸 수 있는 태그: `exterior room deluxe standard family economy oceanview
kitchen lobby breakfast amenity surroundings sunrise-peak udo seopjikoji night`

---

# 발행 후 반드시 할 일

1. **Google Search Console** 에 블로그 등록 → 사이트맵 제출
   `https://<블로그주소>/sitemap.xml`
2. Blogger **설정 → 메타 태그 → 검색 설명 사용** 켜기
3. 2주쯤 뒤 Search Console 의 검색어 리포트를 보고, 실제로 노출되는 키워드를
   `config/seo.json` 의 T1/T2/T3 에 반영한다. 이게 가장 효과가 크다.

# 사실관계 주의

`config/hotel.json` 의 `verified_facts` 에 있는 정보(우도 페리 요금·시간, 일출 시각,
입장료 등)만 모델이 숫자로 단정한다. 나머지는 "확인이 필요하다"로 열어 두도록
프롬프트에 걸려 있다. 요금이나 운영 시간이 바뀌면 **`hotel.json` 을 먼저 고쳐야 한다.**
