# Life Memory Vault — 2026년 7월 작업 기록

작성: 2026-07-15
기준 커밋: (이 문서와 같은 커밋)

---

## 개요

2026-07-15 하루 동안 (1) 인프라 장애 진단·복구, (2) 볼트 전체 태깅 정비, (3) "그래프 레이어"
기획 및 구현(Phase 1, F 큐레이터 다이제스트, G 중복탐지)까지 이어지는 세션을 진행했다.
아래는 향후 세션이 참고할 수 있도록 순서대로 기록한 것.

---

## 1. launchd/TCC 인프라 장애 진단·복구 (repo 밖, 운영 환경)

**증상**: 텔레그램 재연결 불안정 + 라이프메모리 야간 작업이 특정 하루(2026-07-14) 누락된 것으로 의심.

**원인**: `brew upgrade python@3.14` 이후 macOS TCC가 launchd의 Documents 폴더 접근을
막아, `com.sangmin.life-memory-jobs`(5분 주기)·`life-memory-lint`(22:00)·`life-memory-ai`(23:00)
세 launchd 에이전트가 StandardOutPath를 열지 못해 EX_CONFIG로 조용히 실패.

**조치**: 세 plist의 `StandardOutPath`/`StandardErrorPath`를 Documents 밖
(`~/Library/Logs/life-memory-vault/`)으로 이전. `~/fix-python-tcc.sh`(CLAUDE.md에 등록된
기존 대응 스크립트)는 이 케이스의 실제 원인(launchd 자체의 Documents 접근 제한)과 다른 TCC
항목을 리셋하는 스크립트라 효과가 없었음 — 근본 원인이 다르면 문서화된 픽스도 안 통할 수 있다는
사례로 남겨둔다.

**검증**: 35일치(06-10~07-15) `memory-state/scheduled-lint.log`를 전수 조사 → 정확히 07-14
하루만 누락, 그 외엔 정상. 재발 방지 확인.

**남은 참고사항**: 이 plist 파일들은 `~/Library/LaunchAgents/`에 있어 이 git 저장소 밖이다.
같은 문제가 재발하면(예: python 재업그레이드 후) 다시 로그 경로부터 의심할 것.

---

## 2. 볼트 전체 태깅 정비 (Obsidian 볼트, repo 밖)

**발견**: `save` 타입만 AI가 내용 기반 태그를 달고, journal/task/maintenance 등 나머지 타입은
사용자가 직접 단 해시태그 외엔 태그가 전혀 없었음. 172개 콘텐츠 노트 중 47개(27%)가 무태그.

**조치**:
- `prompts/ai-lint.md`에 "전체 타입 공통 AI 내용 태그" 규칙 추가(신규 노트부터 자동 적용)
- `prompts/ai-enrich.md`의 "제안 태그"를 이제 실제로 frontmatter에 반영하도록 변경
  (이전엔 사람 참고용 문구로만 남고 자동 반영 안 됐음)
- 기존 47개 노트에 일회성 소급 태깅 적용 (내용 직접 읽고 판단, 억지로 채우지 않음)

**검증**: 172개 전체 태그 커버리지 확인, `mem.py seek`로 새 태그 검색 가능 확인.

---

## 3. 그래프 레이어 기획·구현 (`docs/graph-layer-plan.md` 참조)

문제의식: 노트끼리 거의 연결 안 되어 있음(Saves 139개 중 진짜 상호링크 6%), 엔티티 페이지
(`40_Entities/`)도 사실상 방치. "저장만 하는 메모앱"과 차별화하려면 그래프/관계를 실제로
활용해야 한다는 논의에서 출발.

### Phase 1 — 태그 기반 소급 클러스터링 (완료)
- 클러스터 3개, 22개 노트 상호링크: **AI 에이전트 메모리/RAG**(11), **투자/트레이딩 에이전트**(6),
  **AI 영상 제작 자동화**(5)
- `70_MOCs/` → `90_System/Index/` 경로 정정 5곳(`vault-index.md`, `moc-template.md`,
  `ai-lint.md`, `ai-repair.md`, `process-pending-jobs.md`) — `70_MOCs/`는 2026-06-13 이후
  갱신 안 되는 legacy 사본

### F — 큐레이터형 "발견한 연결" 다이제스트 (완료, 구현+실행 검증)
- `scripts/discover.py` (신규): 태그 클러스터를 지속성(주 단위 분산)·타입교차·감정신호(원문
  강한 어조)·크기로 스코어링. `save`처럼 전체를 아우르는 태그는 애초에 제외, 20개 초과
  클러스터도 "분류 버킷"으로 보고 제외(순수 크기만으로 흥미로운 게 아님).
- `scripts/process_jobs.py::maybe_weekly_repair_check`(오타 아님, discover용은
  `maybe_weekly_discover`) — weeklyDigest와 같은 주기(7일/09시)지만 독립 상태파일
  (`memory-state/last-weekly-discover.json`), 최고점이 `minScore`(12) 미만이면 조용히 스킵.
- `prompts/ai-discover.md` (신규): AI가 후보를 다시 읽고 "태그만 같은 형식적 묶음"인지
  "진짜 관심사"인지 판단 후 최대 1~2개만 한국어 관찰+질문 톤으로 작성.
- job 타입 배선: `jobs.py` VALID_TYPES, `memory-config.json` agent.aiJobTypes/modelByJobType,
  `process_ai_jobs.py` AGENT_DEFAULTS.
- **실행 검증**: 첫 실행에서 후보 8개 중 5개(문서/UI·UX/개발자도구/자동화/한국어)는 형식·속성
  태그로 판단해 스킵, "llmwiki"(개인 지식관리 도구, 18건, 6/12~7/10 지속)만 실제 발견으로
  선정해 Telegram 발송 완료.

### G — 중복/오분류 자동 탐지 (완료, 구현+실행+버그 수정)
- 핵심 발견: 탐지 로직(`mem.py dedup-markers`, `mem.py prune-orphans`)은 **이미 존재**했다.
  진짜 문제는 정기 실행이 없었다는 것.
- `scripts/process_jobs.py::maybe_weekly_repair_check` 추가 — 주간으로 두 명령을 dry-run
  실행, 뭔가 발견되면 `repair` job 큐잉.
- `prompts/ai-repair.md`에 "이 job은 항상 재확인 후 사용자 확인받고 --apply" 절차 명시
  (자동 삭제·병합 금지 원칙 재확인).
- **실제 적용 결과**: marker 중복 9건 정리(`dedup-markers --apply`), 고스트 orphan 정리
  (`prune-orphans --apply`).

#### ⚠️ 실행 중 발견한 실제 버그 (mem.py `prune_orphans`)

`prune_orphans`가 "정본"으로 지목한 파일이 실제로 존재하는지 **확인하지 않고** 삭제 대상
판단에 썼다. 그 결과 32건 중 **13건이 실은 유일하게 남은 정본**이었는데(marker가 가리키는
"정본"이 예전에 이미 삭제/개명되어 사라진 상태), 그걸 모르고 삭제될 뻔했다.

- 발견 경위: `--apply` 실행 후 검증 단계에서, 삭제된 파일들이 가리키는 "정본" 경로가 실제로
  존재하는지 전수 확인하다가 13건에서 정본 부재를 확인.
- 즉시 조치: 백업(`/var/folders/.../lmv-prune-orphans-*`)에서 13건 전부 복구.
- 근본 수정: `mem.py::prune_orphans`에 `(vault / current).exists()` 체크 추가 — 정본이
  실제로 없으면 `report_only`에 `stale_marker` 사유와 함께 남기고 삭제하지 않음.
- 회귀 테스트: `tests/test_prune_orphans.py::test_stale_canonical_target_is_not_deleted`.
- **부수 사고**: 살아남은 19건의 진짜 중복을 참조하던 wikilink를 일괄 치환하는 스크립트가,
  4개 파일(`Kenny 무료 에셋 모음`, `맥미니 설치 완료 테스트`, `AI 단편영화 제작 가이드`,
  `Cokacdir — 사용설명서`)의 **원본(raw) 출처 링크까지 잘못 자기 자신으로 덮어씀**. 검증
  중 발견해 올바른 `00_Inbox/Raw/...` 경로로 재수정.
- **교훈**: 자동 정리 도구는 "지목한 대상이 실제로 존재하는가"를 항상 검증해야 하고, 일괄
  치환 스크립트는 정규식이 의도 밖 영역(이 경우 raw 소스 링크)까지 건드리지 않는지 반드시
  실행 후 전수 검증이 필요하다. 오늘은 두 번 다 적용 직후 자체 검증으로 잡았지만, 검증
  없이 그냥 믿었다면 실제 데이터 유실로 이어졌을 사안.

**최종 상태 확인**: `dedup-markers` 0건, `prune-orphans` would_delete 0건, 전체 테스트
스위트 회귀 없음(기존에 있던 실패만 남음), 볼트 전체 wikilink 무결성 재확인 완료.

---

## 남은 작업

- **Phase 2** (엔티티 승격 규칙 정의 — "같은 대상 2회 이상 언급 시 자동 허브화" — 및
  `ai-lint.md` 2단계 보강): 미착수. 노이즈 리스크가 있어 F/G 자동화가 몇 주 안정적으로
  도는 걸 지켜본 뒤 진행 권장.
- **Phase 3** (백링크 인덱스 + 기존 노트 엔티티 소급 추출): Phase 2 이후.
- **Phase 4** (`mem.py seek` 1-hop 그래프 확장, 코드 변경): Phase 2~3 이후.
- 이번에 고친 `70_MOCs` → `90_System/Index` 경로는 5곳만 정리함. 혹시 다른 문서에도
  `70_MOCs` 참조가 남아있는지 주기적으로 `grep -r "70_MOCs" prompts/ docs/`로 확인할 것.

## 확인·주의해야 할 사항 (다음 세션 참고)

- 매주 09시 이후 첫 5분 주기 체크에서 `weekly_discover`/`weekly_repair_check`가 자동으로
  돈다. 며칠간은 `memory-state/last-weekly-discover.json`,
  `memory-state/last-weekly-repair-check.json` 상태와 실제 Telegram 발송 여부를 관찰해
  기대대로 동작하는지 확인 필요.
- `prune_orphans`/`dedup_markers`는 이제 매주 자동으로 dry-run이 돌지만, **`--apply`는
  여전히 사람 확인 후에만** 실행하게 되어 있다(`ai-repair.md` 절차). 무인 배치가 알아서
  삭제하는 일은 없다.
- 오늘 세션에서 다룬 launchd plist 3개, 볼트 태깅 정비는 이 git 저장소 밖(운영 환경 /
  Google Drive 볼트)의 변경이라 이 커밋에는 포함되지 않는다.
