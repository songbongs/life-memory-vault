# AI Lint Prompt

Goal: raw note를 읽고 Obsidian vault의 structured note로 변환한다.
단순 분류가 아니라, 관련 엔티티 페이지 업데이트와 노트 간 연결까지 수행하는 Wiki Layer 구축이 목표다.

## 핵심 원칙

- `00_Inbox/Raw`의 원본 파일은 절대 수정하거나 삭제하지 않는다.
- 사실에 없는 내용을 추가하거나 추측으로 채우지 않는다.
- 확신이 없으면 `needs_review: true`로 표시하고 `00_Inbox/Review/`에 검토 노트를 남긴다.
- 처리 완료 후 반드시 `00_Inbox/Processed/`에 마커 JSON을 저장한다.
- **`memory_type`은 실제 저장 폴더와 반드시 일치해야 한다.** 파일을 폴더에 넣은 뒤 frontmatter를 업데이트하지 않으면 모든 도구가 잘못 동작한다.
- **파일명(확장자 제외) = H1 제목 정확히 일치.** 제목을 변경하면 파일명과 H1을 동시에 수정한다.

## 처리 단계 (반드시 순서대로)

### 1단계: Raw note 읽기 및 분석

- `00_Inbox/Processed/`를 확인해서 이미 처리된 raw note인지 확인 (마커 있으면 건너뜀)
- raw note의 텍스트, frontmatter, 첨부파일 정보를 파악
- `#태그` 형식 인라인 태그 추출 (`#private`, `#urgent`, `#task` 등)
- **학습된 규칙 확인(③d)**: `python3 scripts/rules.py active`로 active 규칙을 불러온다. raw 텍스트(소문자)에 규칙 `signal`이 포함되면 해당 `memory_type`/`folder`로 **확정(confidence: high, needs_review: false)**하고 Review를 건너뛴다. 가장 긴(구체적인) signal을 우선 적용한다.
- `memory_type` 결정 (학습 규칙 미매치 시 아래 분류 기준 참조)
- 관련 엔티티 파악 (사람, 장소, 물건, 아티스트 등 raw note에 등장하는 명사)
- **날짜 보강**: 텍스트의 날짜를 기록 저장일(captured_at) 기준으로 절대화해 frontmatter `dates`에 `YY.MM.DD`로 추가한다. 연도 없으면 올해, 월 없이 일만 있으면 저장 월, `오늘/내일/어제·지난달/다음달·작년/내년` 등 상대표현은 저장일 기준으로 환산. (결정론 도우미: `scripts/mem.py`의 `normalize_dates` 참조)

### 2단계: 기존 엔티티 페이지 탐색 및 업데이트

이 단계가 단순 분류와 Wiki Layer의 차이다.

- `40_Entities/` 하위 폴더에서 raw note에 등장하는 엔티티를 검색
  - 예: "차량 와이퍼 교체" → `40_Entities/Things/`에서 차량 관련 파일 탐색
  - 예: "아이유 밤편지" → `40_Entities/Artists/아이유.md` 탐색
- 기존 엔티티 페이지가 있으면: 새 이벤트/정보를 해당 파일에 추가
- 기존 엔티티 페이지가 없고 독립 엔티티로 관리할 가치가 있으면: 신규 엔티티 페이지 생성

엔티티 페이지 신규 생성 기준:
- 반복 등장할 가능성이 있는 사람, 물건, 장소, 아티스트
- 여러 기억이 연결될 수 있는 핵심 명사

### 3단계: Structured note 생성

적합한 폴더에 structured note 생성:

```yaml
---
memory_type: "[분류]"
source_raw: "[[00_Inbox/Raw/경로/파일명]]"
confidence: "high | medium | low"
needs_review: false
sensitivity: "normal | private"
tags:
  - 태그1
  - 태그2
related:
  - "[[관련 노트 경로]]"
entity_refs:
  - "[[40_Entities/Things/내 차량]]"
updated_at: "YYYY-MM-DDTHH:MM:SS"
lint_method: "ai"
dates:
  - "YY.MM.DD"
---

# [제목]

## 내용

[raw note 핵심 내용 정리]

## 출처

- [[00_Inbox/Raw/경로/파일명]]

## 관련

- [[관련 엔티티 또는 노트]]
```

### 4단계: 노트 간 [[wikilink]] 연결

- 생성된 structured note에서 엔티티 페이지로 `[[wikilink]]` 삽입
- 엔티티 페이지에서 새 이벤트 노트로 역링크 추가
- 같은 맥락의 이전 노트가 있으면 `related` 필드에 추가

### 5단계: MOC 업데이트

해당 memory_type에 맞는 MOC 파일을 업데이트한다.

| memory_type | 업데이트할 MOC |
|---|---|
| maintenance | `70_MOCs/Maintenance-MOC.md` |
| food_drink | `70_MOCs/Food-MOC.md` |
| song / artist / album / playlist / listening_log | `70_MOCs/Music-MOC.md` |
| person / group | `70_MOCs/People-MOC.md` |
| trip / visit | `70_MOCs/Travel-MOC.md` |
| idea / product | `70_MOCs/Ideas-MOC.md` |
| task / appointment / decision | `70_MOCs/Tasks-MOC.md` |
| health | `70_MOCs/Health-MOC.md` |
| 모든 항목 | `70_MOCs/Life-Memory-MOC.md`의 "최근 추가된 노트" 섹션 |

MOC 항목 추가 형식:
```markdown
- [[노트 경로|표시 제목]] — 한 줄 설명 (YYYY-MM-DD)
```

**⚠️ MOC 갱신 규칙 (기존 구조 보존):**
- MOC 파일을 **절대 통째로 덮어쓰지 말 것.** 먼저 기존 파일을 읽고, **해당 섹션에 항목만 추가**한다.
- 파일이 없으면 init 템플릿 골격을 먼저 만든 뒤 항목을 추가한다. 예: `Maintenance-MOC.md`는 `## 차량 / ## 가전·기기 / ## 집·시설` 카테고리 섹션을, `Life-Memory-MOC.md`는 카테고리별 MOC 링크 + `## 최근 추가된 노트` 섹션을 유지한다(`scripts/mem.py`의 `init` 템플릿 참조).
- 기존 섹션·다른 항목·헤더를 삭제하거나 축소하지 않는다(최소 stub로 만들지 말 것).

### 6단계: Processed 마커 저장

`00_Inbox/Processed/{raw_file_sha1_16}.json` 파일 저장:

```json
{
  "raw": "00_Inbox/Raw/...",
  "structured": "20_Records/Maintenance/...",
  "processed_at": "2026-06-01T22:00:00+09:00",
  "lint_method": "ai",
  "ai_model": "claude-sonnet-4-6",
  "plan": {
    "memory_type": "maintenance",
    "folder": "20_Records/Maintenance",
    "confidence": "high",
    "needs_review": false
  },
  "entities_updated": ["40_Entities/Things/내 차량.md"],
  "links_added": ["[[40_Entities/Things/내 차량]]"],
  "mocs_updated": ["70_MOCs/Maintenance-MOC.md", "70_MOCs/Life-Memory-MOC.md"]
}
```

### 7단계: 처리 요약 리포트 생성

lint 완료 후 아래 형식으로 요약 출력 (job result에도 기록):

```
✅ AI Lint 완료 (YYYY-MM-DD)
처리: N건
- 생성된 노트: [파일명] (memory_type)
- 업데이트된 엔티티: [파일명]
- 업데이트된 MOC: [파일명]
- needs_review: N건 → 00_Inbox/Review/ 확인 필요
- 실패: N건
```

job의 `chat_id`가 있으면 이 요약을 Telegram으로 발송한다.

## 분류 기준

### memory_type 결정 우선순위

0. **학습된 규칙(active) 최우선(③d)** — `scripts/rules.py active`의 signal이 텍스트에 포함되면 그 분류로 확정, Review 생략.
1. **`#태그` 인라인 힌트** — `#task`, `#maintenance`, `#private` 등
2. **파일 타입** — raw_type이 raw_pdf, raw_image 등이면 needs_review: true 기본 (학습 규칙이 매치돼도 미디어는 needs_review 유지)
3. **키워드 분석**:
   - 교체/정비/수리/maintenance/replace → `maintenance`
   - 구매/샀/쇼핑/가격/원/price → `purchase`
   - 할일/todo/해야/task → `task`
   - 예약/약속/일정/appointment/meeting → `appointment`
   - 카페/맛집/식당/restaurant/cafe → `food_drink`
   - 여행/trip/travel → `trip`
   - 아티스트 - 노래 패턴 / YouTube Music URL → `song` 또는 `listening_log`
   - playlist/플레이리스트 → `playlist`
   - github.com URL 포함 → `project` (GitHub 오픈소스/개발 프로젝트)
   - 나중에 써볼/사용해볼/tool/app/서비스(GitHub 아닌 웹서비스) → `product`
   - 아이디어/idea → `idea`
   - 병원/약/건강/처방 → `health`
   - 매주/매달/버스/하차/픽업 등 반복 일정·알림 → `reminder`
   - 실제 사용 중인 도구·앱의 사용설명서·가이드·명령어 → `thing` (maintenance 아님)
   - 그 외 → `journal`

### 폴더 배치

```
task → 30_Actions/Tasks/
appointment → 30_Actions/Appointments/
reminder → 30_Actions/Reminders/        ← 반복 알림·픽업 시간·루틴 스케줄
purchase → 30_Actions/Shopping/
decision → 30_Actions/Decisions/
maintenance → 20_Records/Maintenance/
ledger → 20_Records/Ledger/
health → 20_Records/Health/
person → 40_Entities/People/
place → 40_Entities/Places/
thing → 40_Entities/Things/
artist → 40_Entities/Artists/
song → 40_Entities/Songs/          ← Artists/Songs 엔티티로 저장, Playlists 아님
album → 40_Entities/Albums/
trip → 50_Experiences/Trips/
food_drink → 50_Experiences/Food_Drink/
listening_log → 50_Experiences/Music/Listening_Log/
playlist → 60_Ideas/Playlists/
product → 60_Ideas/Products/       ← 웹서비스·앱·북마크 (GitHub 아닌 것)
project → 60_Ideas/Projects/       ← GitHub 오픈소스·개발 프로젝트
idea → 60_Ideas/Projects/
journal → 10_Timeline/Daily/       ← 단순 일기·메모. 아래 제외 대상 참고
```

**`journal` (10_Timeline/Daily) 분류 시 주의:**  
아래 성격의 메모는 Daily가 아닌 전용 폴더로 분류한다:
- 할일·루틴 → `task`
- 반복 일정·알림 (버스 하차, 픽업 시간 등) → `reminder`
- 접속 주소·기기 정보·명령어 → `thing`
- 사용 중 도구의 가이드·사용법 → `thing`
- 요리 레시피·음식 경험 → `food_drink`
- GitHub/개발 링크 → `project`
- 웹서비스 북마크 → `product`

### maintenance vs thing 구분 기준

| 구분 | memory_type | 예시 |
|------|-------------|------|
| 실제 수리·교체·정비 기록 | `maintenance` | 와이퍼 교체, 에어컨 청소, 집 수리 |
| 사용 중인 도구/앱의 가이드·설명서 | `thing` | Cokacdir 사용설명서, VNC 접속 주소, CCC 재시작 명령어 |
| 기기·물건 자체 엔티티 | `thing` | 맥미니, 차량, 냉장고 |

→ "유지보수 기록"과 "도구 가이드"를 혼동하지 말 것. Cokacdir 사용설명서는 `maintenance` 아닌 `thing`.

### product vs project 구분 기준

| 구분 | memory_type | 폴더 | 예시 |
|------|-------------|------|------|
| GitHub 오픈소스 리포지토리 | `project` | `60_Ideas/Projects/` | github.com/user/repo |
| 웹서비스·앱·SaaS 북마크 | `product` | `60_Ideas/Products/` | vercel.app, duckdns.org |
| YouTube 영상·강의 링크 | `project` | `60_Ideas/Projects/` | 개발/학습 관련이면 |

## 파일 제목 명명 규칙

raw note의 원문을 그대로 제목으로 쓰지 않는다. 아래 기준으로 간결한 제목을 생성한다.

### project / product 제목

- GitHub 리포: `{프로젝트명} — {한 줄 설명}.md`
  - 예: `ponytail — AI 코딩 도구.md`, `Hindsight — 에이전트 메모리 시스템.md`
- 웹서비스: `{서비스명} — {핵심 기능}.md`
  - 예: `fascanner — URL 스캐너.md`, `주식 매수 관리 서비스.md`
- URL이나 도메인을 제목에 포함하지 않는다 (`github.com/...` 형태 금지)
- `적용후보`, `관심 프로젝트`, `사용해 보고 싶은` 등의 접두어는 태그로 처리하고 제목에서 제거

### 기타 타입 제목

- task: 동사 원형으로 시작 (`생활비 송금`, `지한 버스 확인`)
- reminder: 반복 주기 + 대상 (`지한 영어학원 버스 하차 시간`)
- food_drink: `{음식명} — {조리법/장소}` (`통삼겹 에어프라이어`)
- thing: 기기/물건 이름 + 용도 (`맥미니 VNC 접속 주소`)
- thing (도구 가이드): `{도구명} — 사용설명서` 또는 `{도구명} — {가이드 주제}` (`Cokacdir — 사용설명서`)
- song: `{아티스트} — {곡명}` 형식. `노래저장`, `메모` 등 저장 행위 접두어는 제거 (`JUNGWOO — 클라우드 쿠쿠 랜드`)
- 제목은 최대 40자 이내를 목표로 한다

## 태그 기준

frontmatter의 `tags` 필드에 추가한다. 인라인 `#태그`는 본문에서 제거하고 frontmatter로 통합한다.

### 표준 태그 목록

| 카테고리 | 태그 |
|----------|------|
| 분류 | `관심`, `프로젝트`, `할일`, `루틴`, `일상` |
| 기술 | `AI`, `github`, `개발도구`, `오픈소스` |
| 적용여부 | `적용후보`, `사용중`, `보류` |
| 음악 | `음악`, `노래`, `플레이리스트` |
| 생활 | `음식`, `요리`, `기기`, `장소` |

### 태그 규칙

- 한국어/영어 혼용 금지: 같은 개념은 하나로 통일 (`AI` 또는 `ai` 중 하나만)
- `#AI`, `#에이전트`, `#RAG` 등 대문자는 고유명사·약어만 허용, 나머지는 소문자/한국어
- HEX 색상 코드(`#f5f4ed`, `#1B365D`)는 태그가 아님 — 본문에서 제거
- 태그는 최대 5개로 제한

## 텔레그램 분할 메시지 처리 (특별 규칙)

텔레그램은 긴 텍스트를 자동으로 여러 메시지로 분할한다. 이 경우 동일 문서의 조각들이 별개 raw note로 들어온다.

### 분할 메시지 판단 기준

아래 조건 중 2개 이상이면 분할 메시지로 간주한다:
- 같은 날짜, 수 초~수 분 이내 연속 캡처 (`captured_at` 기준)
- 내용이 문장 중간에서 끊기거나 연번(`1.`, `2.`, 섹션 번호 등)이 연속됨
- 동일한 문서 제목·헤더가 반복되지 않고 이어지는 구조
- 총 4,096자(텔레그램 메시지 한도)에 가까운 조각들

### 처리 방법

1. 분할 조각 전부를 읽어 원래 순서대로 이어 붙인다
2. **하나의 structured note로 병합 생성** — 조각마다 별도 노트 금지
3. frontmatter `source_raw`는 모든 조각의 raw 경로를 리스트로 기록:
   ```yaml
   source_raw:
     - "[[00_Inbox/Raw/.../조각1]]"
     - "[[00_Inbox/Raw/.../조각2]]"
   ```
4. 병합된 내용의 성격에 맞는 단일 `memory_type`·폴더 결정
5. 각 조각의 raw note마다 처리 마커를 저장 (`structured` 필드는 동일 파일 경로)

### 실제 사례 (Cokacdir)

Cokacdir 사용설명서가 7개 조각으로 들어왔을 때:
- ❌ 잘못된 처리: `20_Records/Maintenance/Cokacdir/`에 7개 별도 노트 생성, memory_type 제각각
- ✅ 올바른 처리: `40_Entities/Things/Cokacdir — 사용설명서.md` 1개로 병합, memory_type: `thing`

## 음악 기억 처리 (특별 규칙)

"아티스트 - 곡명" 패턴 또는 YouTube Music URL 감지 시:

1. `40_Entities/Artists/[아티스트명].md` 탐색 → 없으면 생성
2. `40_Entities/Songs/[곡명].md` 탐색 → 없으면 생성, artist 필드 추가
3. `50_Experiences/Music/Listening_Log/`에 청취 기록 노트 생성
4. 세 파일을 서로 `[[wikilink]]`로 연결
5. `70_MOCs/Music-MOC.md` 업데이트

## 주의사항

- `00_Inbox/Review/`에 검토 노트를 남길 때는 왜 불확실한지 이유를 한 줄로 적는다
- 민감 정보(`#private` 또는 sensitivity: private)는 Review 폴더나 넓은 접근 가능 폴더에 노출하지 않는다
- 같은 raw note를 두 번 처리하지 않는다 (processed 마커 확인 필수)
- rule-based lint(`mem.py lint`)가 이미 처리한 노트도 AI lint로 재처리 가능 (`lint_method: "rule_based"` 마커 있으면 개선 대상)
