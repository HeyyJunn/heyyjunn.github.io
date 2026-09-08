# HeyyJunn GitHub Pages / Velog 동기화 시스템 인수인계서

> 마지막 실측 및 전체 검증: 2026-09-08 (Asia/Seoul)
>
> 대상 저장소: `https://github.com/HeyyJunn/heyyjunn.github.io.git`
>
> 로컬 경로: `/Users/junn/heyyjunn.github.io`
>
> Thumbnail audit 시작 기준: `main` / `52346ef4f65012ba168baf1338925a702ec998d3`
>
> 기존 동기화/관리자 구현 기준 커밋: `cab0977370c0487445cca4b435ab3b1f71cd7960`

이 문서는 현재 저장소를 처음 넘겨받는 엔지니어 또는 LLM이 기존 설계 의도와 운영 상태를 훼손하지 않고 바로 작업을 이어갈 수 있도록 작성한 기술·운영 인수인계 문서다. 아래의 수치와 게시물 목록은 위 검증 시점의 스냅샷이며, 이후 Velog 원문이나 설정이 변경되면 `./blog status`, `./blog list`, `./blog dry-run` 결과를 우선한다.

## 1. 가장 먼저 알아야 할 현재 상태

초기 Velog 가져오기는 이미 수행된 상태다. 과거 메모 중 “초기 import를 아직 실행하지 않았다”는 설명이 남아 있다면 현재 저장소에는 적용되지 않는다. 현재 커밋된 `_posts`, `.velog-sync/state.json`, `assets/img/velog`을 권위 있는 기준으로 삼고 임의로 초기화하거나 롤백하지 않는다.

2026-09-08 실측 결과는 다음과 같다.

| 항목 | 현재 값 |
|---|---:|
| Velog 사용자 | `@ilwha` |
| GraphQL에서 확인한 공개 글 | 40개 |
| 현재 GitHub Pages 게시 글 | 13개 |
| GitHub에서 숨긴 글 | 27개 |
| 가져오기 제외 글 | 0개 |
| 다음 동기화 시 IMPORT | 0개 |
| 다음 동기화 시 UPDATE | 0개 |
| UNCHANGED | 13개 |
| 오류 / 경고 | 0개 / 0개 |
| state 레코드 | 40개 |
| 배포 가능한 visible 이미지 | 44개 (본문 33 + 목록 thumbnail 11) |
| visible 이미지 총 용량 | 7,062,707 bytes (본문 6,025,669 + thumbnail 1,037,038) |
| hidden 이미지 state 참조 / 실제 파일 | 158개 / 0개 |
| 로컬 작업 트리 | thumbnail feature commit/push 후 clean 상태인지 `git status --short`로 확인 |
| `main`과 `origin/main` | 커밋/푸시 후 동일함을 확인함. 현재 SHA는 `git rev-parse HEAD`로 확인 |
| 최신 전체 검사 | 89 tests, Jekyll build, HTML-Proofer, actionlint 모두 통과 |

라이브 `./blog status`에서 Velog GraphQL 전체 목록과 RSS 연결은 정상으로 확인됐다. 로컬 환경에는 GitHub CLI(`gh`)가 없어 GitHub Actions 자동 동기화 변수 및 최근 실행 상태는 관리 도구에서 확인하지 못한다. 이는 동기화 엔진 오류가 아니라 로컬 도구 부재다.

## 2. 절대 유지해야 하는 제품 규칙

### 2.1 Metadata mapping은 하나뿐이다

- Velog `series` → Chirpy `categories`
- Velog `tags` → 사용하지 않음

Velog 태그는 다음 어디에도 사용하지 않는다.

- 생성 Markdown front matter
- content hash 또는 metadata hash
- `.velog-sync/state.json`
- 관리 UI의 표·설정
- 변경 분류
- 사용자 문서의 “지원 기능” 목록

따라서 Velog에서 태그만 추가·삭제·이름 변경된 경우 결과는 반드시 `UNCHANGED`여야 한다. Markdown bytes, 의미 있는 state, Git commit이 바뀌면 안 된다. GraphQL query에서도 tags 필드는 제거되어 있다.

### 2.2 Tags UI를 복구하지 않는다

현재 `_tabs/tags.md`는 제거되어 있고 내비게이션에는 Categories, Archives, About만 있다. Tags 탭, Tags 내비게이션, `_tags` 관련 UI를 다시 만들지 않는다.

`_config.yml`의 `jekyll-archives`도 categories만 활성화하며 tag layout/permalink 설정은 제거했다. 이 상태로 Jekyll production build와 HTML-Proofer를 통과했다.

### 2.3 Velog가 관리 포스트의 원본이다

동기화로 만들어진 `_posts/*.md`를 직접 고치면 다음 동기화에서 원문 기준으로 복구될 수 있다. GitHub에만 필요한 수정을 넣으려면 변환기 코드 또는 명시적 override 설계를 추가해야 한다.

### 2.4 게시물 파일을 직접 지우지 않는다

Velog 원문이 남아 있으면 동기화 엔진은 삭제된 관리 파일을 drift로 판단해 복원한다. GitHub Pages에서만 내리려면 반드시 다음 중 하나를 사용한다.

```sh
./blog hide <번호|UUID|slug>
./blog ui
```

숨김은 Velog 원문과 state의 이미지 metadata를 보존하되, `_posts` 파일과 해당 UUID의 deployable 이미지 디렉터리를 제거한다. 숨김 UUID는 `.velog-sync/config.yml`의 `hidden_post_ids`에 저장되어 이후 동기화에서도 다시 생성되지 않는다. 숨김 해제 후 sync하면 GraphQL 원문을 기준으로 이미지를 다시 다운로드한다.

### 2.5 소스에서 사라진 글을 자동 삭제하지 않는다

Velog 전체 목록에서 더 이상 보이지 않는 UUID가 있어도 기존 state, Markdown, 이미지를 자동으로 삭제하지 않는다. 불완전 응답이나 일시 장애로 인한 데이터 손실을 막기 위한 의도적인 보존 정책이다.

## 3. 저장소 구성과 책임 범위

| 경로 | 역할 |
|---|---|
| `blog` | 사용자용 단일 진입점. Python 가상환경과 의존성을 자동 준비한 뒤 관리 CLI 실행 |
| `scripts/blog_manager.py` | 한국어 CLI 명령 정의, 확인 프롬프트, UI/serve 실행 |
| `scripts/blog_admin/service.py` | CLI/UI 공용 서비스 계층, 설정 변경, 상태 조회, 빌드·검사·원격 실행 |
| `scripts/blog_admin/web.py` | localhost Flask 관리 화면과 JSON API, 백그라운드 작업 잠금 |
| `scripts/blog_admin/templates/index.html` | 관리 화면 단일 페이지 템플릿 |
| `scripts/blog_admin/static/` | 관리 화면 CSS와 JavaScript |
| `scripts/sync_velog.py` | 저수준 동기화 엔진 CLI (`--dry-run` 또는 apply) |
| `scripts/velog_sync/client.py` | Velog GraphQL 전체 목록/본문과 RSS 클라이언트 |
| `scripts/velog_sync/config.py` | YAML 설정 검증 및 dataclass 변환 |
| `scripts/velog_sync/images.py` | 이미지 검증·계획·다운로드·재사용·원자적 저장 |
| `scripts/velog_sync/markdown.py` | Markdown 정규화, 이미지 URL 변환, fence/math 검사 |
| `scripts/velog_sync/sync.py` | 분류, 렌더링, hash, drift 탐지, state 갱신을 담당하는 핵심 엔진 |
| `scripts/velog_sync/state.py` | state schema 검증, SHA-256, 결정적 JSON 직렬화, 원자적 text write |
| `.velog-sync/config.yml` | 운영 설정. 제외/숨김 UUID, series 매핑, 이미지 정책 포함 |
| `.velog-sync/thumbnail-overrides/<uuid>/` | Local Blog Manager에서 올린 GitHub 전용 미리보기 원본. Git에는 추적하지만 Jekyll 산출물에서는 제외 |
| `.velog-sync/state.json` | 40개 UUID의 고정 경로, hash, 이미지 매핑 등을 보관하는 동기화 ledger |
| `_posts/` | 현재 공개되는 13개 Chirpy Markdown 포스트 |
| `assets/img/velog/` | 게시 중인 13개 글의 deployable Velog 이미지 미러. hidden UUID 디렉터리는 배포에서 제외하기 위해 제거 |
| `_layouts/home.html` | Chirpy 7.6 홈 카드의 custom `post.thumbnail` 렌더링 최소 override |
| `.github/workflows/pages-deploy.yml` | push 빌드·배포, 수동 dry-run/apply, 조건부 예약 동기화 |
| `tests/test_velog_sync.py` | 소스/렌더링/이미지/분류/안전성 테스트 |
| `tests/test_blog_admin.py` | CLI, 설정, 숨김/제외, UI API, 동시 실행 방지 테스트 |
| `_config.yml` | Chirpy/Jekyll 및 배포 제외 경로 설정 |
| `_includes/favicons.html` | 커스텀 PNG favicon link와 cache-busting query |
| `favicon.ico` | 루트 fallback favicon |

`docs`는 `_config.yml`의 `exclude`에 포함되어 있으므로 이 인수인계서는 실제 사이트 산출물에 노출되지 않는다.

## 4. 전체 데이터 흐름

```text
Velog GraphQL 전체 목록
  ├─ UUID/제목/slug/발행·수정일/series/thumbnail 검증
  ├─ hidden / excluded / import_after 판정
  ├─ state hash와 로컬 파일 hash로 상세 본문 조회 필요성 판정
  └─ 필요한 글만 readPost GraphQL 조회
       ├─ raw Markdown 확인
       ├─ 본문 이미지와 독립적인 thumbnail 우선순위 결정
       ├─ 이미지 URL 추출 및 안전성 검사
       ├─ Velog series를 categories로 변환
       ├─ Chirpy front matter + 본문 렌더링
       └─ IMPORT / UPDATE / UNCHANGED / ERROR 분류

Velog RSS (최근 20개)
  └─ 최근 글 health/sanity check만 수행

apply이고 ERROR가 0개일 때만
  ├─ 본문 이미지와 활성 thumbnail 다운로드/재사용
  ├─ Markdown 원자적 저장
  └─ state 결정적 직렬화 및 원자적 저장
```

RSS는 전체 inventory가 아니다. GraphQL 전체 목록 조회가 실패하거나 불완전하면 RSS 20개로 전체를 대체하지 않고 작업을 중단한다.

## 5. Velog 소스 수집

### 5.1 GraphQL

- endpoint: `https://v3.velog.io/graphql`
- inventory operation: `velogPosts`
- detail operation: `readPost`
- page size: 20
- max pages: 1000
- 현재 관찰된 pagination: `20 → 20 → 0`
- retry: 3회, 0.4초 기반 지수 backoff
- timeout: 20초
- User-Agent: `heyyjunn-velog-sync/1`

전체 목록은 UUID 중복, 반복 cursor, 최대 페이지 도달, GraphQL `errors`, 누락/잘못된 필드, authoritative series 필드 누락을 오류로 처리한다. 상세 조회에서는 목록과 detail의 UUID 및 metadata가 맞는지도 검증한다. 공개 글만 처리하며 private 글은 건너뛴다.

GraphQL query는 의도적으로 tags를 요청하지 않는다.

### 5.2 RSS

- endpoint: `https://v2.velog.io/rss/@ilwha`
- 최근 20개만 제공된다는 전제로 사용
- GraphQL raw Markdown만 canonical body로 사용
- GraphQL detail 실패 시 해당 글은 `ERROR`로 보류하고 기존 글을 보존
- RSS HTML→Markdown body fallback은 fidelity 문제 때문에 제거됨
- RSS 장애는 기존 unchanged 글을 파괴하지 않으며 경고로 노출될 수 있음

## 6. 포스트 ID, 경로, front matter

### 6.1 ID와 고정 경로

Velog UUID가 유일한 안정 ID다. 번호는 현재 목록 표시용이라 바뀔 수 있고, slug는 사용자가 수정할 수 있으므로 state key로 사용하지 않는다.

신규 포스트 경로는 다음 형태다.

```text
_posts/YYYY-MM-DD-<sanitized-source-slug>.md
```

같은 경로가 이미 존재하면 UUID 앞 8자를 suffix로 붙인다. 한 번 state에 저장된 `post_path`는 제목이나 slug가 바뀌어도 유지한다. 경로는 `_posts` 아래의 `.md`인지 resolve 후 다시 검증해 path traversal을 막는다.

### 6.2 series가 있는 front matter

```yaml
---
title: "..."
date: 2025-01-01 12:34:56 +0900
last_modified_at: 2025-01-02 12:34:56 +0900
categories:
  - "[Python] Notion📚"
render_with_liquid: false
---
```

### 6.3 series가 없는 front matter

```yaml
---
title: "..."
date: 2025-01-01 12:34:56 +0900
last_modified_at: 2025-01-02 12:34:56 +0900
render_with_liquid: false
---
```

- `categories`는 series가 없으면 생략한다.
- `series_category_map`에 명시된 series는 1개 또는 2개의 category로 매핑할 수 있다.
- 제목과 category는 JSON 방식 double quote로 안전하게 escape한다.
- 수식 문법이 감지되면 `math: true`를 추가한다.
- `tags:`는 어떤 경우에도 생성하지 않는다.
- `render_with_liquid: false`로 Velog 본문 속 Liquid 유사 문법의 오동작을 막는다.
- 날짜는 `Asia/Seoul`로 변환한다.
- 최초 `published_at`은 고정 보존하고 `updated_at`은 `last_modified_at`에 반영한다.

### 6.4 목록 전용 미리보기 front matter와 우선순위

Velog thumbnail 또는 활성 GitHub override가 있으면 Chirpy 기본 `image:`가 아니라 다음 custom field를 추가한다.

```yaml
thumbnail:
  path: "/assets/img/velog/<uuid>/<hash>.jpg"
  alt: "게시물 제목"
```

thumbnail이 없으면 field 자체를 생략한다. alt fallback은 게시물 제목이며 AI로 생성하지 않는다. 우선순위는 반드시 `Velog thumbnail > GitHub 직접 지정 > 없음`이다. 본문 첫 이미지는 fallback이 아니다. Velog thumbnail이 새로 생기면 기존 override는 삭제하지 않고 비활성 보존하며, Velog thumbnail이 다시 null이 되면 그 override가 복귀한다. Velog thumbnail이 활성인 동안 dormant override만 바뀌어도 Markdown/state/render hash는 바뀌지 않는다.

`_layouts/home.html`만 `post.thumbnail`을 읽으며 post detail layout은 이 field를 읽지 않는다. 따라서 동일 URL이 Markdown 본문에도 실제로 있을 때의 본문 image를 제외하면 상세 글 위·아래에는 대표 이미지가 자동 표시되지 않는다.

## 7. 분류 상태와 파일 변경 의미

| 상태 | 의미 | apply 시 동작 |
|---|---|---|
| `IMPORT` | state에 없는 신규 공개 글 | 이미지와 새 Markdown을 만들고 state 추가 |
| `UPDATE` | GitHub 산출물에 영향을 주는 원문 변경 또는 로컬 drift | 고정 경로의 Markdown/이미지/state를 갱신 |
| `UNCHANGED` | 원문 산출물과 로컬 파일이 모두 일치 | 파일/state 변경 없음, commit 없음 |
| `EXCLUDED` | 아직 가져오지 않도록 설정된 글 | 생성하지 않음. 기존 관리 글을 삭제하는 기능은 아님 |
| `HIDDEN` | 한 번 관리된 글을 GitHub에서만 숨김 | Markdown과 deployable 이미지를 제거. state의 source/image metadata와 Velog 원문은 보존 |
| `ERROR` | 안전하게 처리할 수 없는 소스/본문 오류 | apply의 모든 쓰기를 시작하지 않고 반환 |

관리 화면에서는 각각 `새로 등록 예정`, `수정 예정`, `최신 상태`, `가져오지 않음`, `GitHub에서 숨김`, `오류`로 표시한다.

### 제외와 숨김의 차이

- 제외(`exclude`)는 아직 import되지 않은 글을 가져오지 않을 때 사용한다.
- 숨김(`hide`)은 이미 state로 관리 중인 글을 GitHub에서 내릴 때 사용한다.
- 아직 관리되지 않은 글에 hide를 시도하면 오류가 나며 exclude를 사용하라는 안내가 나온다.
- 이미 import된 글을 exclude 목록에 넣어도 기존 파일을 자동 삭제하지 않는다.

### drift 처리

state의 `rendered_sha256`과 실제 Markdown SHA-256이 다르거나 state가 참조하는 이미지가 없거나 hash가 다르면 상세 원문을 다시 읽고 `UPDATE`로 복구한다. 따라서 관리 파일을 손으로 고치는 방식은 지속되지 않는다.

## 8. state.json schema와 hash 원칙

현재 state file schema version은 `1`, render transformation schema는 `3`이다.

```json
{
  "schema_version": 1,
  "posts": {
    "<velog-uuid>": {
      "body_source": "graphql",
      "categories": ["..."],
      "content_hash": "sha256:...",
      "images": {
        "<remote-url>": {
          "content_type": "image/png",
          "path": "assets/img/velog/<uuid>/<url-sha256>.png",
          "sha256": "sha256:...",
          "size": 12345
        }
      },
      "metadata_hash": "sha256:...",
      "post_path": "_posts/YYYY-MM-DD-slug.md",
      "published_at": "...",
      "rendered_sha256": "sha256:...",
      "source_slug": "...",
      "source_updated_at": "...",
      "source_url": "...",
      "thumbnail": {
        "kind": "velog",
        "source_url": "https://velog.velcdn.com/...",
        "path": "assets/img/velog/<uuid>/<hash>.jpg",
        "sha256": "sha256:...",
        "content_type": "image/jpeg",
        "size": 12345
      },
      "title": "..."
    }
  }
}
```

`content_hash`에는 GitHub 산출물에 영향을 주는 값만 들어간다.

- UUID
- title
- normalized body
- resolved categories
- 고정 published timestamp
- updated timestamp
- image mapping
- resolved thumbnail의 kind/source/path/hash/MIME/size 또는 null
- transformation schema version

`metadata_hash`는 상세 본문을 다시 가져와야 하는지 빠르게 판정하기 위해 UUID, title, slug, source URL, released/updated timestamp, resolved categories와 실제 활성 thumbnail source를 사용한다. Velog thumbnail이 있으면 dormant override는 두 hash 모두에서 제외된다. slug-only 변경은 Markdown을 다시 쓰지 않고 state의 source metadata만 최신화한다.

Velog tags는 어떤 hash와 state에도 포함되지 않는다. tag-only 변경은 `UNCHANGED`여야 한다. JSON은 key 정렬, UTF-8, 2-space indent, 마지막 newline으로 결정적으로 직렬화한다. state write는 같은 디렉터리의 `.part` 임시 파일을 `fsync`한 뒤 `os.replace`하는 방식이다.

## 9. 이미지 미러링

기본 저장 형식은 다음과 같다.

```text
assets/img/velog/<post-uuid>/<sha256-of-full-source-url>.<extension>
```

핵심 정책은 다음과 같다.

- HTTPS URL만 허용
- 현재 허용 host는 `velog.velcdn.com` 하나
- 원격 허용 MIME: PNG, JPEG, GIF, WebP, AVIF, SVG
- 파일당 최대 25 MiB (`26214400` bytes)
- timeout 20초, retry 3회, planning worker 8개
- HEAD로 MIME/크기/redirect 최종 host를 검사한 후 apply에서 GET
- Content-Length뿐 아니라 실제 streaming byte 수도 상한 검사
- URL 전체 SHA-256을 파일명으로 사용
- UUID와 최종 경로를 resolve하여 traversal 차단
- 기존 파일의 SHA-256이 state와 일치하면 재다운로드하지 않음
- `.part`에 쓴 뒤 `fsync` + `os.replace`
- probe/download/MIME mismatch 실패 시 해당 이미지는 원격 URL을 유지하고 경고를 남김
- fenced code block 내부의 이미지처럼 보이는 텍스트는 변환하지 않음

같은 원격 이미지 URL이 여러 글에 쓰여도 포스트 UUID 디렉터리가 다르므로 글마다 별도 파일이 존재할 수 있다. 숨긴 글은 state의 158개 source body-image record를 유지하지만 deployable UUID 디렉터리는 제거한다. 현재 visible 13개 글에는 본문 이미지 33개와 목록 thumbnail 11개, 합계 44개만 로컬과 `_site`에 존재하며 hidden 이미지는 둘 다 0개다. unhide 시 GraphQL 원문을 다시 확인해 필요한 본문 이미지와 thumbnail을 다운로드한다.

### 9.1 Thumbnail과 manual override

- inventory와 `readPost`에서 `thumbnail`을 모두 받고 UUID와 metadata 일치를 검증한다.
- 같은 UUID에서 thumbnail URL이 body image URL과 같으면 동일 plan/path/binary를 재사용한다.
- remote thumbnail은 CDN URL을 front matter에 직접 쓰지 않고 기존 `ImageMirror`로 local asset을 만든다.
- thumbnail은 critical asset이다. host/MIME/size/probe/download 검증 실패 시 기존 post를 보존하고 해당 outcome을 `ERROR`로 바꾼다.
- Local Manager 원본은 `.velog-sync/thumbnail-overrides/<uuid>/<content-sha256>.<ext>`에 저장한다. client filename은 버리고 PNG/JPEG/GIF/WebP/AVIF magic bytes와 MIME, 크기를 검증한다. SVG와 script성 upload는 받지 않는다.
- 활성 override만 `assets/img/velog/<uuid>/`로 materialize한다. Velog가 우선하게 되거나 override가 제거·교체되면 이전 state가 관리하던 deployable thumbnail만 prune하며 알 수 없는 파일은 지우지 않는다.
- hidden 글은 Markdown과 UUID deployable asset directory가 모두 없어야 한다. override 원본은 비공개 source 경로에 보존 가능하며 unhide sync에서 다시 결정한다.
- `_layouts/home.html`은 Chirpy 7.6 upstream home layout이 카드 image block을 include로 분리하지 않아 필요한 최소 override다. theme upgrade 시 upstream home layout과 diff를 반드시 재검토한다.
- `assets/css/jekyll-theme-chirpy.scss`의 `#post-list .thumbnail-col`은 안정적인 16:9 영역과 `object-fit: cover`를 제공한다. 같은 파일의 post body h1~h6 `font-weight: 700` scope를 유지해야 한다.

## 10. Markdown 변환 원칙과 알려진 콘텐츠 특성

GraphQL `readPost`가 `is_markdown=true`인 raw Markdown을 주 소스로 사용한다. 변환은 최소화한다.

- newline과 마지막 newline 정규화
- 실제 Markdown/HTML 이미지 참조만 로컬 경로로 교체
- fenced code block 내용 보존
- table, Liquid 유사 문자열, 3개/4개 backtick fence 보존
- 원문 오류를 추측해 자동 수리하지 않음

과거 전체 inventory 검사에서 UUID `461d37cf-5955-4b3a-9b6a-414c60fc9863`, slug `C-객체지향프로그래밍1-C언어-복습-Chapter-8-12`의 source line 300에 닫히지 않은 code fence가 감지된 적이 있다. 엔진은 이를 자동 수정하지 않고 경고만 내도록 설계되어 있다. 현재 state와 로컬 파일이 일치하므로 dry-run 경고는 0개이고, Jekyll/HTML-Proofer도 통과한다. 해당 원문이 다시 변경되어 상세 변환이 수행되면 경고가 재등장할 수 있으니 자동 보정 코드를 넣지 말고 Velog 원문을 우선 확인한다.

## 11. 현재 config.yml

운영 핵심값은 다음과 같다.

```yaml
velog:
  username: ilwha
  graphql_url: https://v3.velog.io/graphql
  rss_url: https://v2.velog.io/rss/@ilwha
  page_size: 20
  max_pages: 1000
timezone: Asia/Seoul
exclude_post_ids: []
hidden_post_ids: # 27개 UUID
import_after: null
series_category_map: {}
thumbnail_overrides: {}
images:
  enabled: true
  allowed_hosts:
    - velog.velcdn.com
  max_bytes: 26214400
  timeout_seconds: 20
  retries: 3
  workers: 8
```

세부 의미:

- `exclude_post_ids`: 신규 가져오기에서 제외할 UUID. 가장 권장되는 exclude 키
- `hidden_post_ids`: 이미 관리된 글을 GitHub에서 숨길 UUID
- 번호, slug, canonical URL 입력은 live inventory에서 UUID로 resolve한 뒤 `exclude_post_ids`에만 저장
- `import_after`: 신규 글에만 적용. 이미 state에 있는 글의 업데이트를 막지 않음
- `series_category_map`: series 이름별 1~2개 category override
- `thumbnail_overrides`: UUID별 GitHub 전용 thumbnail 원본 path. Local Manager만 안전하게 추가·교체·삭제
- 설정 UI의 username은 `@ilwha` 읽기 전용이며 import_after와 series mapping만 편집한다.
- exclude/hide는 게시물 관리 UI 또는 전용 CLI로 편집한다.

`ConfigStore`는 process 내부 lock을 잡고 임시 YAML을 작성해 실제 loader로 재검증한 다음 `os.replace`한다. 저장 실패 시 기존 config를 유지한다.

### 11.1 Git preflight와 publish 안전성

Local Blog Manager의 실제 쓰기 작업(sync, exclude, hide, unhide, settings)은 먼저 현재 폴더가 Git repository인지, branch가 `main`인지 확인하고 `git fetch --prune origin main`을 실행한다. 그 뒤 `HEAD...refs/remotes/origin/main`을 비교해 다음 네 상태를 구분한다.

- `current`: 로컬과 GitHub가 같음
- `ahead`: 로컬 commit만 있음
- `behind`: GitHub에 더 최신 commit이 있음
- `diverged`: 양쪽 이력이 갈라짐

behind/diverged/fetch 실패/비-main 상태에서는 쓰기를 중단한다. 자동 merge, reset, force push, stash는 없다. clean worktree이고 behind일 때만 사용자가 명시적으로 `update`를 실행해 `git pull --ff-only origin main`을 수행할 수 있다.

`publish`는 검사 전후로 두 번 fetch/compare하고 다음 allowlist만 `git add -A -- <명시 경로>`로 stage한다.

- `.velog-sync/config.yml`
- `.velog-sync/state.json`
- `.velog-sync/thumbnail-overrides`
- `_posts`
- `assets/img/velog`

unrelated dirty file이나 origin/main 이후의 local commit에 unrelated file이 있으면 자동 publish를 거부한다. `git add .`는 사용하지 않는다. 전체 check 실패 시 commit하지 않고, normal push 실패 시 만들어진 local commit을 보존한 채 사용자에게 ahead 상태를 알린다.

## 12. 사용자용 CLI

최초 실행 시 `./blog`가 `.venv-blog`를 만들고 `requirements-velog-sync.txt` hash가 바뀐 경우에만 패키지를 다시 설치한다. 현재 Python 의존성은 `PyYAML==6.0.2`, `Flask==3.1.2`다.

| 명령 | 기능 / 주의점 |
|---|---|
| `./blog help` | 전체 명령 도움말 |
| `./blog ui` | `127.0.0.1:8765` 관리 화면 실행 및 브라우저 열기 |
| `./blog ui --no-browser` | 브라우저 자동 실행 없이 UI 서버 시작 |
| `./blog list` | Velog 40개와 한국어 상태, UUID, slug, category, 이미지 수 표시 |
| `./blog status` | Velog/GitHub.io/Git/GitHub Actions 요약 |
| `./blog update` | clean worktree에서 origin/main이 앞선 경우에만 `pull --ff-only` |
| `./blog publish` | Git preflight와 전체 검사 후 허용된 관리 파일만 commit/push |
| `./blog dry-run` | 파일 변경 없이 실제 원격 상태와 분류 확인 |
| `./blog sync` | 로컬에 실제 반영. 신규 import가 있으면 `동기화` 입력 요구 |
| `./blog sync --yes` | 비대화형 실제 반영 |
| `./blog test` | 89개 Python unit test 실행 |
| `./blog build` | `.bundle-blog` 의존성 준비 후 `_site` 빌드 |
| `./blog check` | test → live dry-run → build → HTML-Proofer 순서의 전체 검사 |
| `./blog serve` | `127.0.0.1:4000` 로컬 Jekyll preview. 같은 서비스 인스턴스의 중복 실행 방지 |
| `./blog exclude list` | 제외된 글 표시 |
| `./blog exclude add <...>` | 번호/UUID/정확한 slug를 UUID로 resolve해 제외 |
| `./blog exclude remove <...>` | 제외 해제 |
| `./blog hide <...>` | GitHub에서만 숨김. 확인 시 `숨기기` 입력 |
| `./blog hide <...> --yes` | 비대화형 숨김 |
| `./blog unhide <...>` | 숨김 UUID 제거. 다음 sync에서 파일 복원 가능 |
| `./blog hidden` | 숨긴 글 표시 |
| `./blog remote-dry-run` | `gh`로 Actions dry-run dispatch |
| `./blog remote-sync` | 확인 후 Actions apply dispatch |
| `./blog remote-sync --yes` | 비대화형 원격 apply dispatch |

번호는 매번 원격 inventory 순서에서 만들어지므로 장기 자동화에는 UUID를 사용한다. 입력은 shell command로 평가되지 않고 subprocess도 argv list로 실행되어 shell injection을 피한다.

저수준 엔진은 다음처럼 직접 실행할 수도 있다.

```sh
.venv-blog/bin/python scripts/sync_velog.py --dry-run
.venv-blog/bin/python scripts/sync_velog.py
```

일반 사용자는 `./blog` 명령을 우선한다.

## 13. 로컬 관리 UI

실행:

```sh
./blog ui
# http://127.0.0.1:8765
```

localhost에만 bind되고 debug mode는 꺼져 있다. `_config.yml`이 `scripts`, `tests`, `.velog-sync`, `blog`, `.venv-blog`, `.bundle-blog`를 Jekyll 산출물에서 제외하므로 관리 UI와 설정/state는 production Pages에 포함되지 않는다.

화면 기능:

- 대시보드와 전체 상태 요약
- 게시물 검색, 상태/series 필터, 다중 선택
- 상세 modal: UUID, slug, Velog/GitHub URL, series/category, 날짜, path, 이미지 수, 경고
- 신규 글 가져오지 않기 / 제외 해제
- 관리 글 GitHub에서 숨기기 / 숨김 해제
- dry-run 및 실제 로컬 sync
- unit test, Jekyll build, HTML 검사, 전체 check
- 로컬 사이트 preview 실행
- 읽기 전용 Velog username, import 기준일, series→category mapping 설정
- origin/main 최신/ahead/behind/diverged 상태와 변경 파일 표시
- 안전한 fast-forward 가져오기와 GitHub publish
- GitHub Actions dry-run/apply 요청
- 현재 task와 최근 task history

주요 API:

| Method / path | 기능 |
|---|---|
| `GET /`, `/posts`, `/sync`, `/checks`, `/preview`, `/settings`, `/history` | SPA shell |
| `GET /api/status` | live preview + 저장소/연결 상태 |
| `GET /api/config` | 안전하게 노출할 운영 설정 |
| `POST /api/posts/exclude` | 선택 글 제외; backend `confirmed: true` 필요 |
| `POST /api/posts/unexclude` | 제외 해제 |
| `POST /api/posts/hide` | 관리 글 숨김; backend 확인 필요 |
| `POST /api/posts/unhide` | 숨김 해제 |
| `POST /api/settings` | import_after/series mapping 저장. username 변경 불가 |
| `POST /api/tasks/<kind>` | dry-run/sync/pull/publish/test/build/html/check/serve/remote 작업 시작 |
| `GET /api/tasks/current` | 현재 작업과 busy 상태 |
| `GET /api/tasks/history` | 이 프로세스에서 완료된 최근 작업 |

실제 sync, pull, publish, remote sync는 UI 확인창뿐 아니라 backend의 `confirmed: true`도 검사한다. TaskRunner는 process 단위 non-blocking lock으로 동시에 두 관리 작업이 실행되는 것을 막고, 작업은 daemon thread에서 실행한다. history는 메모리에만 있어 UI 프로세스를 재시작하면 사라진다.

GitHub CLI가 없거나 `gh auth status`가 실패하면 원격 버튼은 사용 불가 상태가 된다. 현재 로컬은 `gh`가 설치되어 있지 않다.

## 14. GitHub Actions 동기화 및 배포

workflow: `.github/workflows/pages-deploy.yml`

표시 이름: `Build, Sync, and Deploy`

### 트리거

- `main` 또는 `master` push: build/test site/deploy
- schedule: 매시간 `7, 22, 37, 52`분
- workflow dispatch: `dry-run` 또는 `apply`, 기본값 `dry-run`

schedule job은 repository variable `VELOG_SYNC_ENABLED`가 정확히 `true`일 때만 실행된다. 수동 `apply`는 이 변수와 무관하게 실행된다. GitHub가 장기 inactivity 뒤 scheduled workflow를 비활성화할 수 있으므로 Actions UI도 주기적으로 확인한다.

### 필요한 권한과 변수

workflow permissions:

- `contents: write`
- `pages: write`
- `id-token: write`

변경을 자동 commit하려면 repository variables가 필요하다.

- `BLOG_GIT_NAME`
- `BLOG_GIT_EMAIL`

값이 없으면 추측한 bot identity로 commit하지 않고 실패한다.

### 실행 순서

1. main checkout (`fetch-depth: 0`)
2. 모든 event에서 Python 3.13과 sync 의존성 설치
3. push와 수동 dispatch에서는 89개 unit test 실행; 15분 schedule에서는 반복하지 않음
4. manual dry-run이면 변경 미리보기
5. manual apply 또는 enabled schedule이면 실제 sync
6. 변경 경로가 `_posts/*`, `assets/img/velog/*`, `.velog-sync/state.json`뿐인지 검증
7. 변경 유무 판정
8. push 또는 sync 변경이 있을 때만 Ruby 3.4/Jekyll build와 HTML-Proofer
9. 검증된 sync 변경이 있을 때만 commit/push
10. 동일 run에서 Pages artifact upload/deploy

동기화 결과가 no-op이면 commit을 만들지 않고 scheduled/manual apply 배포도 건너뛴다. push 이벤트는 일반 사이트 변경 배포를 위해 항상 build/deploy한다. concurrency group은 `pages`, `cancel-in-progress: false`라 쓰기 도중 run이 취소되거나 서로 경합하지 않게 했다.

workflow가 만든 commit은 `_posts`, `.velog-sync/state.json`, `assets/img/velog`만 stage한다. 예상 밖 파일이 바뀌면 commit 전에 실패한다.

## 15. 실패 안전성과 원자성

현재 구현의 안전 경계는 다음과 같다.

- GraphQL inventory 불완전/오류 → apply write 시작 전 중단
- 한 개라도 post outcome이 `ERROR` → apply write 시작 전 반환
- dry-run → 파일시스템 변경 0
- Markdown/state/config → temp file + `fsync` + `os.replace`
- 이미지 → `.part` + `fsync` + `os.replace`
- unsafe post/image path → 거부
- body image 실패 → 해당 본문 URL을 원격으로 유지 + 경고
- active thumbnail 실패 → 기존 post를 보존하고 outcome `ERROR`
- source 삭제 → 로컬 자동 삭제 금지
- hidden → engine이 파일을 재생성하지 않음
- workflow → 예상 경로 외 변경 거부, build와 HTML 검사 후 commit

전체 저장소를 하나의 transaction으로 묶는 구조는 아니다. 대신 fatal source 오류를 materialization 전에 모으고 각 파일을 원자적으로 교체한다. 이 경계를 바꾸는 경우 partial failure 테스트를 추가한다.

## 16. 테스트와 2026-09-08 검증 결과

### 16.1 2026-09-08 실제 Velog thumbnail audit

운영 파일을 수정하기 전에 `@ilwha`의 GraphQL inventory 20→20→0과 40개 `readPost`를 전부 읽기 전용으로 대조했다.

- 전체 40개: thumbnail 있음 19, 없음 21
- visible 13개: 있음 11, 없음 2
- hidden 27개: 있음 8, 없음 19
- inventory와 readPost thumbnail: 40개 모두 동일
- thumbnail이 같은 글의 Markdown body image URL과 동일: 0
- body에 없는 별도 thumbnail: 19
- host: 19개 모두 `velog.velcdn.com`
- CDN HEAD MIME: JPEG 12, PNG 1, `application/octet-stream`으로 응답한 `.avif` 6

`.avif` 6개는 현재 모두 hidden 쪽이지만 unhide에 대비해 허용 host의 `.avif` URL에 한해서 download bytes의 AVIF magic/brand를 다시 확인한다. 범용 MIME만 믿어 임의 파일을 허용하지 않는다.

### 16.2 검증 결과

`./blog check`를 thumbnail migration 후 현재 state에서 다시 실행했고 다음을 모두 통과했다.

1. Python unit tests: **89개 통과** (`Ran 89 tests ... OK`)
2. live Velog dry-run: IMPORT 0, UPDATE 0, UNCHANGED 13, EXCLUDED 0, HIDDEN 27, ERROR 0, 경고 0
3. Jekyll build: Chirpy site 정상 생성 (`_site`, 약 1.15초)
4. HTML-Proofer: 22 HTML files, 196 internal links, 12 files의 internal hash 확인, 성공

테스트 범위:

- GraphQL 20→20→0 pagination
- duplicate UUID, repeated cursor, malformed JSON, timeout, partial GraphQL errors
- 목록/detail UUID 및 metadata mismatch
- authoritative series null/누락
- tags 미수집·미비교 및 tag-only 변경 no-op
- Unicode YAML, categories 생략, tags front matter 금지
- Markdown fence, Liquid 유사 구문, table, math, RSS health check
- GraphQL detail 실패 시 기존 글 보존 및 RSS body fallback 금지
- 이미지 확장자/MIME, timeout, oversize, redirect host, traversal, `.part`, 재사용
- IMPORT→UNCHANGED 결정성, title/body/series update, path 고정, collision suffix
- exclusion, import_after, hidden, source deletion 보존
- dry-run zero mutation, Markdown/image drift 복구, unsafe state path 거부
- CLI parse 및 번호/UUID/slug resolve, shell-like 입력 거부
- atomic config update, exclude/hide/unhide 의미
- Git current/ahead/behind/diverged, fast-forward-only pull, publish allowlist
- failed check의 no-commit 및 failed push의 local commit 보존
- hidden 이미지 prune, visible 이미지 보존, unhide 재다운로드
- 한국어 UI routes/status, Tags UI 부재
- 위험 작업 backend confirmation, 작업 history, concurrent lock
- Velog thumbnail 있음/null, body image와 동일/별도, Velog→override→none 우선순위
- thumbnail add/change/remove, 고정 post_path, dormant override rendered no-op
- manual upload magic/MIME/size/UUID/path traversal, 원본 비공개 경로, publish allowlist
- home thumbnail/text-only card, post detail 자동 미표시, heading bold/Tags 회귀

변경 후 최소 검증 명령은 다음이다.

```sh
./blog check
git status --short
```

네트워크 없이 unit test만 빠르게 돌리려면:

```sh
./blog test
```

## 17. 현재 게시 중인 13개 포스트

아래는 state UUID, title, source slug, 고정 post path, state에 기록된 이미지 수다.

| UUID | 제목 | Velog slug | 고정 경로 | 이미지 |
|---|---|---|---|---:|
| `24104f88-d139-4945-b4d0-a020b26912b2` | [C++] 객체지향프로그래밍1 : C-language review (Chapter 3 - 7) | `C-객체지향프로그래밍1-C-language-review-Chapter-3-7` | `_posts/2024-11-02-C-객체지향프로그래밍1-C-language-review-Chapter-3-7.md` | 1 |
| `461d37cf-5955-4b3a-9b6a-414c60fc9863` | [C++] 객체지향프로그래밍1 : con(de, delegating)structor / overloading / include guard (Chapter 8 - 12) | `C-객체지향프로그래밍1-C언어-복습-Chapter-8-12` | `_posts/2024-11-09-C-객체지향프로그래밍1-C언어-복습-Chapter-8-12.md` | 3 |
| `3bbd2352-464c-4b86-be90-a7f08b232073` | [C++] 객체지향프로그래밍1 : Inheritance / Override / vptr,vtbl / downcasting (chapter 13 - 16) | `C-객체지향프로그래밍1-Inheritance-Override-vptrvtbl-downcasting-chapter-13-15` | `_posts/2024-11-10-C-객체지향프로그래밍1-Inheritance-Override-vptrvtbl-downcasting-chapter-13-15.md` | 1 |
| `2b9b7e47-2e14-4612-ab10-e6c81055dd8e` | [C++] 객체지향프로그래밍1 : Lambda Expression / Namespace / ADL / Nested Class (chapter 17 - 18) | `C-객체지향프로그래밍1-Lambda-Expression-Namespace-ADL-Nested-Class-chapter-17-18` | `_posts/2024-11-10-C-객체지향프로그래밍1-Lambda-Expression-Namespace-ADL-Nested-Class-chapter-17-18.md` | 4 |
| `efdd96a3-22b3-4e08-854f-46a6cbbd0514` | [ React.JS ] Mini Project - Todo List | `React.JS-Mini-Project-Todo-List` | `_posts/2025-01-26-React.JS-Mini-Project-Todo-List.md` | 3 |
| `039e20bd-5c5d-442a-8170-285a3f991802` | [ React.JS ] useReducer, useMemo, useCallback | `React.JS-useReducer-useMemo-useCallback` | `_posts/2025-02-02-React.JS-useReducer-useMemo-useCallback.md` | 0 |
| `7bd24f35-d6e6-471c-becc-2dbb512acc4d` | [Java] Dynamic Method Dispatch & V-Table (JVM) | `Java-Dynamic-Method-Dispatch-V-Table-JVM` | `_posts/2025-03-08-Java-Dynamic-Method-Dispatch-V-Table-JVM.md` | 2 |
| `37a2bbb0-0fe1-4a3b-8de3-405a08a9e1b7` | [Java] Polymorphism | `Java-Polymorphism` | `_posts/2025-03-14-Java-Polymorphism.md` | 0 |
| `cf211993-d985-4368-9091-dd1cb1b952a2` | [Java] Object Class, Immutable Object | `Java-Object-Class-Immutable-Object` | `_posts/2025-03-18-Java-Object-Class-Immutable-Object.md` | 0 |
| `e4107974-4393-4fec-84dd-318cdb9e56af` | [Java] Generic | `dvhiut7k` | `_posts/2025-03-24-dvhiut7k.md` | 0 |
| `ca010783-034c-45e4-9551-5aecfa373dbe` | [Spring] 내가 보려고 만든 MVC 기초흐름도 | `Spring-내가-보려고-만든-MVC` | `_posts/2025-05-06-Spring-내가-보려고-만든-MVC.md` | 3 |
| `8916fba7-4c88-4768-aa6a-374feba00f14` | [Spring] JPA | `Spring` | `_posts/2025-07-03-Spring.md` | 8 |
| `dbf10a73-b92c-48ca-8964-642ef5cdc591` | [Spring] Spring Boot 기본 용어 정리 | `Spring-Spring-Boot-기본-용어-정리` | `_posts/2025-07-09-Spring-Spring-Boot-기본-용어-정리.md` | 8 |

## 18. 현재 숨긴 27개 포스트

아래 UUID는 `.velog-sync/config.yml`의 `hidden_post_ids`에 있다. state의 source/image metadata는 유지되지만 해당 `post_path`와 `assets/img/velog/<uuid>/` 디렉터리는 현재 없어야 한다.

| UUID | 제목 | Velog slug | 이미지 |
|---|---|---|---:|
| `e60346c7-7e0f-422a-8440-afc70b82346e` | [Baekjoon] #10950 #2439 ( C, phase3 반복문 ) | `C백준단계별-Ph3반복문10950-2439` | 0 |
| `83fe9fad-8d96-45a6-abe6-b7494c77aee5` | [C] Code📁 : 과제_배열 | `CASGMT-과제배열` | 3 |
| `4f176559-46f2-419f-a89e-68a038ce2470` | [C] Code📁 : 과제_배열로 문자열 다루기 | `CAssg-과제배열로-문자열-다루기` | 4 |
| `f1179499-6429-4c16-a458-4348d4abadc6` | [C] Code📁 : 과제_파일과 스트림 | `CASGMT-과제파일과-스트림` | 3 |
| `4030a68a-c42e-4bae-bb76-eb1383fa2937` | [C] Notion📚 : 비트연산과 응용 | `CNotion-비트연산과-응용` | 13 |
| `f8101d7b-45b5-4d37-ab06-fd05b84db18d` | [C] Notion📚 : 재귀호출 | `C-Notion-재귀호출` | 13 |
| `b97398b8-6e23-425c-b711-df385c52df3d` | [C] Notion📚 : 포인터_역참조 연산자 선언/사용 | `C-Notion-포인터역참조-연산자-선언사용` | 1 |
| `9d548c10-6db3-4227-b502-975621e744c4` | [C] Notion📚 : 포인터 | `C-Notion-포인터` | 31 |
| `e8884404-ad18-4962-abd0-7d19a3621435` | [C] Notion📚 : 구조체 포인터 | `C-Notion-구조체-포인터` | 6 |
| `8a76357b-7283-4b46-9d59-4703eb17fc86` | [C] Notion📚 : 메모리의 동적할당 | `C-Notion-메모리의-동적할당` | 40 |
| `5d1c1d78-4962-4ae5-a301-e497e9dab006` | [파이썬] Notion📚 : 파이썬의 기본 요소들 01 | `Py-Notion-파이썬의-기본-요소들` | 12 |
| `e600c7b4-3b59-4267-a271-a1a03746a278` | [Py] Notion📚 : ch2 파이썬의 기본 요소들 | `Py-Notion-Ch2-파이썬의-기본-요소들` | 2 |
| `dd6f0b3c-f494-4381-b6ff-8d0e42b1bf25` | [Py] Code📁 : ch3 01_몸풀기문제들_실습용 | `Py-Code-01몸풀기문제들실습용` | 10 |
| `c02eb9b7-1547-4eec-aca1-b97a46d963cb` | [Py] Code📁 : ch3 02_별찍기 | `Py-Code-ch3-02별찍기` | 7 |
| `c0fcedbd-61b6-4a6e-962f-a6f05355724c` | [Data_Structures] Selection Sort | `DataStructures-Selection-Sort` | 2 |
| `36075444-0733-4eb6-a72a-3fceb379d7a6` | [Data_Structures] Bubble Sort | `DataStructures-Bubble-Sort` | 2 |
| `9659c4f8-18da-4a2b-9a4a-eb9e0b17bf30` | [Data_Structures] Insertion Sort | `DataStructures-Insertion-Sort` | 2 |
| `8e450883-2969-47c9-a4a9-6f3c6956eab8` | [Py] Notion📚 : 파이썬의 컨테이너 별 메서드와 함수 | `Py-Notion-파이썬의-컨테이너-별-메서드와-함수` | 0 |
| `83861c49-4732-49dd-8fa1-4fa847c150e7` | [Python] Ch3 (code) - 03 문제 세트1 | `Python-Ch3-code-03-문제-세트1` | 0 |
| `96b10ddb-5d6d-4f74-9d6f-ea423445cfd4` | [Python] Ch3 (code) - 04 문제 세트2 | `Py-Code-ch3-03문제세트2` | 1 |
| `eff33e2b-cd18-49b3-a912-8c571eedf8c5` | [Python] Ch3 (code) - 05 시간과 날짜 | `Python-Ch3-code-05-시간과-날짜` | 0 |
| `31f0f369-b238-4fce-b631-950a6d2ffb4c` | [Python] Ch3 (code) - 06 난수 | `Py-Code-ch3-06난수` | 1 |
| `43ad63c7-222f-4f84-87af-c4c155422f0a` | [Python] Ch3 (code) - 07 리스트 컴프리헨션 | `Python-Chap3-07-리스트컴프리헨션` | 0 |
| `48700130-8ff0-493d-ad8c-0a54d9a3896a` | [Data_Structures] Sequential Search (순차탐색) | `DataStructures-Sequential-Search-순차탐색` | 0 |
| `66f7be36-5b6e-4cd8-89bb-903a7367b80e` | [Data_Structures] String Compression | `DataStructures-String-Compression` | 0 |
| `df6217ea-4645-4ab0-a830-a6b375c9a2f2` | [Data_Structures] Binary Search (이진탐색) | `DataStructures-Binary-Search-이진탐색` | 1 |
| `7460c503-b467-4aec-8a2d-aea1d40a1094` | [Baekjoon] #11720 ( C++, phase5 문자열) | `Code-백준Ph5문자열11720` | 4 |

숨김을 해제하려면 UUID를 사용하는 것이 가장 안전하다.

```sh
./blog unhide <uuid>
./blog dry-run   # UPDATE 또는 IMPORT 성격의 복원 계획 확인
./blog sync
./blog check
```

## 19. Chirpy 사이트와 favicon 현황

- theme: `jekyll-theme-chirpy` 7.6 계열 (`Gemfile.lock` 기준)
- site URL: `https://heyyjunn.github.io`
- timezone: `Asia/Seoul`
- 현재 탭: Categories(order 1), Archives(order 2), About(order 3)
- Tags 탭 파일은 없음
- PWA가 켜져 있고 cache도 활성화됨

게시물 본문의 Markdown heading은 `assets/css/jekyll-theme-chirpy.scss`의
`article[data-toc] > .content` scope에서만 h1부터 h6까지 `font-weight: 700`을
적용한다. heading 내부 anchor도 같은 굵기를 사용하며, 글자 크기 hierarchy나
Markdown 원문은 바꾸지 않는다. 이 selector는 sidebar, navbar, 탭 페이지,
Local Blog Manager에는 적용되지 않는다.

favicon은 두 경로가 있다.

- 주 favicon: `assets/img/favicons/favicon.png`
- fallback: repository root의 `favicon.ico`
- 실제 head include: `_includes/favicons.html`
- 현재 PNG URL에는 `?v=20260908-2` cache-busting query가 붙어 있음

브라우저에서 favicon 변경이 바로 안 보일 때는 다음 순서로 확인한다.

1. 배포된 HTML `<head>`가 `/assets/img/favicons/favicon.png?v=20260908-2`를 가리키는지 확인
2. 해당 URL을 직접 열어 새 이미지가 배포됐는지 확인
3. Chrome/Safari favicon cache, PWA/service worker cache, 기존 탭 cache를 제거하거나 private window에서 확인
4. 다음 변경에서는 query version을 다시 올림
5. `/favicon.ico` fallback도 원하는 이미지와 일치하는지 확인

이 favicon 구성은 2026-09-08 전체 Jekyll/HTML 검사에서 정상 통과했다.

## 20. 일상 운영 절차

### 변경 사항만 확인

```sh
cd /Users/junn/heyyjunn.github.io
./blog status
./blog dry-run
```

IMPORT/UPDATE가 0이면 sync나 commit이 필요 없다.

### 로컬에서 실제 동기화

```sh
./blog dry-run
./blog sync
./blog check
git status --short
git diff --stat
git diff -- .velog-sync/state.json _posts
```

이미지는 binary라 `git diff --stat assets/img/velog` 중심으로 확인한다. 검토가 끝난 뒤에만 사용자가 원하는 commit/push 정책에 따라 처리한다.

### GitHub에서만 게시물 숨김

```sh
./blog list
./blog hide <uuid>
./blog status
./blog check
```

hide는 config, `_posts`, 해당 UUID의 deployable 이미지를 바꾸므로 commit 대상이다. state의 source/image metadata는 유지한다.

### 새 글을 처음부터 제외

```sh
./blog exclude add <uuid>
./blog dry-run
```

### 원격 자동화 사용

```sh
# gh 설치 및 로그인 후
./blog remote-dry-run
./blog remote-sync
```

또는 GitHub Actions UI에서 workflow dispatch의 mode를 고른다. apply 전에 dry-run 로그를 먼저 보는 것이 기본 운영 절차다.

## 21. 하지 말아야 할 작업

- 새 repository나 새 프로젝트를 만들지 않는다.
- `_posts`의 관리 파일을 직접 삭제해 숨김을 구현하지 않는다.
- Velog tags를 categories나 tags front matter로 동기화하지 않는다.
- `_tabs/tags.md` 또는 Tags navigation을 복구하지 않는다.
- RSS 20개를 전체 inventory처럼 취급하지 않는다.
- state의 UUID key나 고정 `post_path`를 이유 없이 재생성하지 않는다.
- 숨긴 글의 state image metadata는 보존한다. deployable image directory만 제거한다.
- source에서 사라진 글을 자동 삭제하지 않는다.
- image allowed host/size/path 검증을 우회하지 않는다.
- 동기화 후 Jekyll build/HTML 검증 전에 자동 commit하도록 workflow 순서를 바꾸지 않는다.
- 사용자 작업이 섞인 dirty worktree를 일괄 reset/checkout하지 않는다.
- `.velog-sync/state.json`에 실행 시각처럼 매번 바뀌는 값을 넣어 no-op commit을 만들지 않는다.

## 22. 알려진 한계와 후속 확인 사항

현재 구현은 기능적으로 완료되어 있고 전체 검사를 통과하지만 다음 운영 사항은 로컬 코드만으로 확정할 수 없다.

1. **GitHub Actions 설정 상태**: 로컬에 `gh`가 없어 `VELOG_SYNC_ENABLED`, `BLOG_GIT_NAME`, `BLOG_GIT_EMAIL`, 최근 run 결과를 확인하지 못했다. GitHub UI 또는 `gh` 설치 후 확인해야 한다.
2. **예약 실행 활성 여부**: workflow 코드가 있어도 `VELOG_SYNC_ENABLED=true`가 아니면 schedule은 의도적으로 아무 일도 하지 않는다.
3. **UI task history 영속성**: 현재 메모리 전용이다. 브라우저/서버 재시작 후 과거 history가 필요한 요구가 생기면 별도 로컬 ledger 설계가 필요하다. sync state에 섞으면 안 된다.
4. **전체 트랜잭션 부재**: fatal source 오류는 쓰기 전에 막지만, 여러 파일을 하나의 filesystem transaction으로 묶지는 않는다. 현재 atomic-per-file 정책과 테스트 범위를 이해하고 변경한다.
5. **브라우저 자동화 환경**: 2026-09-08 검증에서는 브라우저 런타임 초기화 제한으로 화면 자동 조작까지 수행하지 못했다. Flask 실제 HTTP/API 응답, JavaScript syntax, UI unit test로 회귀 검증했다.

## 23. 다음 담당자의 시작 체크리스트

1. 현재 디렉터리가 `/Users/junn/heyyjunn.github.io`인지 확인한다.
2. `git status --short`로 사용자 변경을 먼저 확인하고 보존한다.
3. `git log -1 --oneline --decorate`로 이 문서의 구현 반영 커밋 이후 변경을 확인한다.
4. `./blog status`로 Velog 연결과 게시/숨김 수를 확인한다.
5. `./blog dry-run`으로 IMPORT/UPDATE/ERROR를 확인한다.
6. 동기화 엔진을 바꾼다면 관련 unit test를 먼저 추가하거나 갱신한다.
7. `./blog check`를 통과시킨다.
8. `git diff`에서 허용한 파일만 바뀌었는지 검토한다.
9. tags 비사용, hidden 보존, source 삭제 보존 불변식을 다시 확인한다.
10. GitHub Actions 관련 변경이면 GitHub 변수와 실제 run 결과도 별도로 확인한다.

## 24. 완료 정의

이 시스템의 정상 상태는 단순히 스크립트가 종료되는 것이 아니라 다음을 모두 만족하는 상태다.

- GraphQL 전체 inventory가 완전하게 검증됨
- 모든 공개 글이 IMPORT/UPDATE/UNCHANGED/EXCLUDED/HIDDEN 중 의도한 상태로 분류됨
- `ERROR=0`
- Velog series만 Chirpy category로 반영됨
- tags가 output/state/hash/UI에 없음
- 목록 thumbnail 우선순위가 Velog > GitHub override > none이며 본문 첫 이미지 fallback이 없음
- thumbnail metadata가 home/list에만 렌더링되고 post detail에 자동 삽입되지 않음
- 숨긴 글이 재생성되지 않음
- 변경 없는 run이 Markdown/state/commit을 만들지 않음
- 이미지가 허용 정책 안에서 미러링되거나 실패 시 원격 URL로 안전하게 남음
- 89개 unit test 통과
- Jekyll production build 통과
- HTML-Proofer 통과
- workflow가 검증 뒤에만 commit/deploy함

현재 저장소는 2026-09-08 기준 이 완료 조건을 충족한다. 다만 GitHub-hosted Actions의 repository variable과 최근 실행 결과는 로컬에 `gh`가 없어서 별도 확인이 필요하다.
