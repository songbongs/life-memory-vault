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

### 5단계: 인덱스 업데이트

해당 memory_type에 맞는 Index 파일을 업데이트한다.

| memory_type | 업데이트할 Index |
|---|---|
| maintenance | `90_System/Index/Maintenance-MOC.md` |
| food_drink / trip | `90_System/Index/Life-Memory-MOC.md` |
| song / playlist | `90_System/Index/Music-MOC.md` |
| save (GitHub) | `90_System/Index/Ideas-MOC.md` |
| save (서비스·앱) | `90_System/Index/Ideas-MOC.md` |
| 모든 항목 | `90_System/Index/Life-Memory-MOC.md`의 "최근 추가된 노트" 섹션 |

Index 항목 추가 형식:
```markdown
- [[노트 경로|표시 제목]] — 한 줄 설명 (YYYY-MM-DD)
```

**⚠️ Index 갱신 규칙 (기존 구조 보존):**
- Index 파일을 **절대 통째로 덮어쓰지 말 것.** 먼저 기존 파일을 읽고, **해당 섹션에 항목만 추가**한다.
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
  "entities_updated": ["40_Notes/Things/내 차량.md"],
  "links_added": ["[[40_Notes/Things/내 차량]]"],
  "mocs_updated": ["90_System/Index/Maintenance-MOC.md", "90_System/Index/Life-Memory-MOC.md"]
}
```

### 6-2단계: Daily 인덱스 업데이트

새 structured note 생성 후, 해당 노트를 날짜 인덱스 파일에 링크한다.

- 파일 위치: `10_Daily/YYYY-MM-DD.md` (captured_at 날짜 기준, 없으면 오늘)
- 파일이 없으면 헤더(`date` frontmatter + `# YYYY-MM-DD`)를 만들고 추가
- 파일이 있으면 기존 내용 끝에 링크 추가 (이미 있으면 스킵)
- journal 타입 포함 **모든 타입** 추가 (분류 무관하게 날짜로 전체 검색 가능하도록)

형식:
```markdown
- [[40_Notes/Saves/AgentSpace — 인간+에이전트 협업 워크스페이스|AgentSpace]]
- [[30_Actions/Tasks/생활비 송금|생활비 송금]]
```

> 결정론적 lint(`scripts/mem.py lint`)는 `update_daily_index()` 함수가 자동 처리한다. AI lint 경로에서도 동일하게 반영해야 한다.

### 7단계: 기존 파일명 위반 정리 (rename pass)

새 raw note 처리 후, 볼트 전체 structured note 중 명명 규칙 위반 파일도 함께 수정한다.

#### 7-1. 위반 파일 탐지

아래 패턴이 파일명에 있으면 위반이다:
- `AI 프로젝트`, `AI design`, `AI plugins`, `AI util`, `AI tts`, `AI RAG`, `AI investment` 등 폴더·태그가 이미 표현하는 카테고리 접두어
- `LLMWIKI`, `적용후보`, `관심 프로젝트`, `memory`, `memo`, `메모`, `obsidian`, `song`, `노래`, `요리`, `공부대상`, `추천대상` 등 중복 정보
- 한·영 혼재 (`AI LLMWIKI 프로젝트`, `song playlist`) — 공식 제품명은 제외
- URL·도메인 포함 (`github.com/...`)
- 40자 초과

탐지 방법:
```bash
# 40_Notes/Saves/, 40_Notes/Music/, 40_Notes/Things/, 30_Actions/ 등 순회
find "{vault}/40_Notes" "{vault}/30_Actions" "{vault}/10_Daily" -name "*.md"
```

#### 7-2. 올바른 이름 결정

각 위반 파일에 대해 마커 JSON(`00_Inbox/Processed/*.json`)을 조회해 URL·enrich 제목을 확인하고 명명 규칙("파일 제목 명명 규칙" 섹션)을 적용한다.

- **GitHub 리포**: URL에서 `repo-name` 추출 → `{repo-name} — {한 줄 설명}`  
  설명은 enrich 제목 설명부 또는 노트 본문 첫 문장에서 추출
- **웹서비스**: enrich 제목에서 서비스명 추출 → `{서비스명} — {핵심 기능}`
- **기타**: 노트 본문 H1·첫 문장 기반으로 간결하게 요약

#### 7-3. 이름 변경 실행

```bash
python3 scripts/mem.py reclassify "{현재 파일 상대경로}" --title "{새 제목}"
```

- 이동 없이 이름만 변경할 때는 `--type`을 생략한다
- wikilink 자동 업데이트는 `reclassify`가 처리함
- 변경이 불확실하면 건너뛰고 7-4에서 기록

#### 7-4. 처리 요약 리포트 생성

lint 완료 후 아래 형식으로 요약 출력 (job result에도 기록):

```
✅ AI Lint 완료 (YYYY-MM-DD)
처리: N건
- 생성된 노트: [파일명] (memory_type)
- 업데이트된 엔티티: [파일명]
- 업데이트된 MOC: [파일명]
- 파일명 정리: N건 수정 (이전→이후)
- 건너뜀 (불확실): N건
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
maintenance → 20_Records/Maintenance/
ledger → 20_Records/Ledger/
health → 20_Records/Health/
person → 40_Notes/People/
place → 40_Notes/Places/
thing → 40_Notes/Things/
song → 40_Notes/Music/              ← 노래, 아티스트 기준
playlist → 40_Notes/Music/          ← 플레이리스트도 동일 폴더, tag로 구분
food_drink → 40_Notes/Experiences/
trip → 40_Notes/Experiences/
save → 40_Notes/Saves/              ← GitHub·웹서비스·북마크·아이디어 통합
project → 40_Notes/Saves/           ← 하위 호환 (save와 동일 폴더)
product → 40_Notes/Saves/           ← 하위 호환 (save와 동일 폴더)
idea → 40_Notes/Saves/
journal → 10_Daily/                 ← 단순 일기·메모. 아래 제외 대상 참고
```

**`journal` (10_Daily) 분류 시 주의:**  
아래 성격의 메모는 Daily가 아닌 전용 폴더로 분류한다:
- 할일·루틴 → `task`
- 반복 일정·알림 (버스 하차, 픽업 시간 등) → `reminder`
- 접속 주소·기기 정보·명령어 → `thing`
- 사용 중 도구의 가이드·사용법 → `thing`
- 요리 레시피·음식 경험 → `food_drink`
- GitHub/개발 링크·웹서비스 북마크·아이디어 → `save`

### maintenance vs thing 구분 기준

| 구분 | memory_type | 예시 |
|------|-------------|------|
| 실제 수리·교체·정비 기록 | `maintenance` | 와이퍼 교체, 에어컨 청소, 집 수리 |
| 사용 중인 도구/앱의 가이드·설명서 | `thing` | Cokacdir 사용설명서, VNC 접속 주소, CCC 재시작 명령어 |
| 기기·물건 자체 엔티티 | `thing` | 맥미니, 차량, 냉장고 |

→ "유지보수 기록"과 "도구 가이드"를 혼동하지 말 것. Cokacdir 사용설명서는 `maintenance` 아닌 `thing`.

### save 태그 체계

`save` 타입 노트는 frontmatter `tags`에 아래 분류 태그를 추가해 내용을 구분한다.

| 태그 | 의미 | 예시 |
|------|------|------|
| `llmwiki` | 지식관리·옵시디언·그래프RAG 도구 | DocTology, SoDam-WikiMate, llm-wiki-skill |
| `rag` | RAG·벡터DB·에이전트 메모리 시스템 | LEANN, PixelRAG, Hindsight |
| `tts` | 음성합성·TTS 도구 | Supertonic |
| `agent` | AI 에이전트·오케스트레이션 | AgentSpace, 헤르메스, Memory Weft |
| `design` | 디자인·문서·이미지 도구 | Kami, Satgat, PerfectVector |
| `coding` | 개발도구·IDE·코드 에이전트 | Codex, ponytail, remote-pair |
| `plugin` | 브라우저 확장·봇·플러그인 | gptaku-plugins, NEIS 크롬 확장 |
| `github` | GitHub 리포지토리 | github.com/... URL 포함 |
| `webapp` | 웹서비스·SaaS·앱 북마크 | fascanner, Indie Radar |
| `invest` | 투자·주식·금융 도구 | vibe-investing, Trading Agent |
| `education` | 교육·학습·강의 자료 | NEIS, 쌤핀, LLM wiki 강의 |

새 `save` 노트 생성 시 해당하는 태그를 frontmatter에 포함한다:
```yaml
tags:
  - save
  - llmwiki
  - github
```

태그는 복수 허용. 태그가 없는 경우 `save` 하나만 추가.

## 파일 제목 명명 규칙

raw note의 원문을 그대로 제목으로 쓰지 않는다. 아래 기준으로 간결한 제목을 생성한다.

### 금지 패턴 (모든 타입 공통)

- `AI 프로젝트`, `LLMWIKI`, `적용후보`, `관심 프로젝트`, `memory`, `song`, `노래`, `요리` 등 폴더·태그가 이미 표현하는 정보를 제목에 중복하지 않는다
- 한영 혼재 금지 (`song playlist`, `AI LLMWIKI 프로젝트`) — 제품 공식명은 예외 (`knowledge-manager`, `MemoryWeft`)
- URL·도메인을 제목에 포함하지 않는다 (`github.com/...`, `vercel.app` 형태 금지)
- 제목은 최대 40자 이내를 목표로 한다

### project / product 제목

- GitHub 리포: `{프로젝트명} — {한 줄 설명}`
  - 예: `ponytail — AI 코딩 도구`, `Hindsight — 에이전트 메모리 시스템`, `Memory Weft — AI 공유 메모리`
  - 한 줄 설명이 불명확하면 `{프로젝트명} (GitHub)` 형식도 허용: `Omnisearch 구글 통합 (GitHub)`
- 웹서비스·앱·SaaS: `{서비스명} — {핵심 기능}`
  - 공식 서비스명을 우선 사용 (URL이 아닌 페이지 본문·제목에서 확인)
  - 예: `Indie Radar — iOS 앱 시장 포화도 분석`, `imnotai — AI 한국어 윤문`, `주식 매수 관리 서비스`

### 일일 기록 (journal / 세미나 / 가이드)

- 세미나·발표 노트: `{이벤트명} — {발표자/주제}`
  - 예: `LLM Wiki 오픈세미나 — 김재경 발표자료`
- 도구 가이드·사용법: `{도구명} {가이드 주제}` 또는 `{도구명} — {사용 목적}`
  - 예: `토푸경 knowledge-manager 활용 가이드`, `토푸경 knowledge-manager 디스코드 봇 설정`

### 기타 타입 제목

- task: 동사 원형으로 시작 (`생활비 송금`, `지한 버스 확인`)
- reminder: 반복 주기 + 대상 (`지한 영어학원 버스 하차 시간`)
- food_drink: `{음식명} — {조리법/장소}` — `요리` 접두어 제거 (`통삼겹 — 에어프라이어 굽기`)
- thing: 기기/물건 이름 + 용도 (`맥미니 VNC 접속 주소`)
- thing (도구 가이드): `{도구명} — 사용설명서` 또는 `{도구명} — {가이드 주제}` (`Cokacdir — 사용설명서`)
- song: `{아티스트} — {곡명}` 형식. `노래저장`, `메모` 등 저장 행위 접두어는 제거 (`JUNGWOO — 클라우드 쿠쿠 랜드`)
- playlist: `플레이리스트` 또는 구체적 이름이 있으면 그 이름 — Songs/Playlists 폴더 간 중복 금지

## 태그 기준

frontmatter의 `tags` 필드에 추가한다. 인라인 `#태그`는 본문에서 제거하고 frontmatter로 통합한다.

### 표준 태그 목록

| 카테고리 | 태그 |
|----------|------|
| Save 분류 | `save`, `llmwiki`, `rag`, `tts`, `agent`, `design`, `coding`, `plugin`, `github`, `webapp`, `invest`, `education` |
| 음악 | `song`, `playlist` |
| 상태 | `사용중`, `보류`, `관심` |
| 공개범위 | `private` |
| 생활 | `음식`, `요리`, `기기`, `장소` |

### 태그 규칙

- Save 분류 태그(위 목록)는 영어 소문자로 통일
- 기존 `#AI`, `#프로젝트`, `#적용후보` 같은 중복 정보성 태그는 Save 분류 태그로 교체
- HEX 색상 코드(`#f5f4ed`, `#1B365D`)는 태그가 아님 — 본문에서 제거
- 태그는 최대 5개로 제한

### 전체 타입 공통: AI 내용 기반 태그 (2026-07-15 추가)

기존엔 `save` 타입만 위 표준 태그를 받고, 나머지 타입(journal/task/maintenance/food_drink/
appointment/reminder/thing/song 등)은 사용자가 직접 단 `#해시태그`가 없으면 태그가 하나도
안 붙었다. **모든 memory_type에 대해, lint 처리 시 AI가 raw note 내용을 읽고 자유형 한국어
키워드 태그를 최소 1개~최대 5개(위 "Save 분류" 태그와 합쳐 총 5개 한도) 추가한다.**

- 내용에서 핵심 주제·대상·카테고리를 뽑아 명사형 키워드로 (예: 와이퍼 교체 기록 → `차량`,
  `정비` / 파스타 맛집 후기 → `맛집`, `이탈리안`)
- 이미 사용자가 단 `#해시태그`나 위 표준 태그가 있으면 그것과 **중복되지 않게** 보충
- 지어내지 말 것 — raw note 본문에 실제로 드러난 주제만 태그로 뽑는다. 애매하면 태그 없이 둔다
  (억지로 5개 채우지 않는다)
- 태그는 frontmatter `tags` 리스트에 직접 쓴다 (제안만 하고 마는 게 아니라 실제로 반영)

## 기존 노트 소급 태깅 (일회성 백필, 2026-07-15)

위 "전체 타입 공통 태그" 규칙을 볼트에 이미 있는 구조화 노트에도 적용하는 일회성 작업.
신규 raw note lint와는 별개로, 이미 존재하는 노트를 대상으로 한다.

1. `40_Notes/`, `20_Records/`, `30_Actions/`, `10_Daily/` 등 구조화 노트 폴더를 전수 순회한다
2. 각 노트의 frontmatter `tags`를 확인해 위 공통 규칙 기준으로 비어있거나 부실하면 본문을 읽고
   내용 기반 태그를 추가한다 (기존 태그는 보존, 덮어쓰지 않고 보충)
3. 이미 적절한 태그가 있으면 건드리지 않는다 (헛수고 방지)
4. raw note나 frontmatter의 다른 필드(제목·폴더·분류)는 건드리지 않는다 — 태그 추가만 한다
5. 이 백필은 일회성이며, 이후로는 위 "전체 타입 공통" 규칙이 매 lint마다 자동 적용된다

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
5. `90_System/Index/Music-MOC.md` 업데이트 (2026-07-15: `70_MOCs/`는 6/13 이후 갱신 안 되는 legacy 사본이니 참조 금지)

## 주의사항

- `00_Inbox/Review/`에 검토 노트를 남길 때는 왜 불확실한지 이유를 한 줄로 적는다
- 민감 정보(`#private` 또는 sensitivity: private)는 Review 폴더나 넓은 접근 가능 폴더에 노출하지 않는다
- 같은 raw note를 두 번 처리하지 않는다 (processed 마커 확인 필수)
- rule-based lint(`mem.py lint`)가 이미 처리한 노트도 AI lint로 재처리 가능 (`lint_method: "rule_based"` 마커 있으면 개선 대상)
