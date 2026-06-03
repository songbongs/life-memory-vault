# 00_Inbox/Review 워크플로우

`00_Inbox/Review/`는 확정되지 않은 기억이 잠시 머무는 공간이다.
제텔카스텐의 fleeting note → permanent note 전환 전 검토 단계와 같다.

## Review 폴더에 들어오는 3가지 경로

### 1. AI lint가 낮은 confidence로 분류한 노트
AI lint가 `confidence: low` 또는 `needs_review: true`로 판단한 노트.
파일명 형식: `review-lint-YYYY-MM-DD-[원본 제목].md`

예시 상황:
- 맥락 없이 짧게 저장된 메모 ("나중에 확인", "이거 중요")
- 여러 카테고리에 걸쳐 있는 노트
- 이미지/PDF에서 OCR된 내용으로 의미 불명확

### 2. mem-seek 결과 중 저장할 가치가 있는 합성 답변
검색 결과가 재사용 가치가 있을 때 자동 또는 수동으로 저장.
파일명 형식: `seek-YYYY-MM-DD-[검색어].md`

예시:
- "내가 저장한 주식 서비스 목록" 검색 → 결과를 정리된 노트로 저장
- 여러 기억을 종합한 요약 ("내 차량 유지보수 이력 전체")

### 3. AI doctor가 이상을 감지하여 격리한 노트
doctor 실행 중 문제가 발견된 노트의 복사본 또는 참조.
파일명 형식: `doctor-YYYY-MM-DD-[이슈].md`

## Review 처리 방법

### 사용자에게 Review 건수 알림
- `/status` 또는 `/digest` 실행 시 Review 폴더 건수 포함
- Telegram digest 알림에 "검토 대기: N건" 포함

### Review 처리 워크플로우
1. `/doctor` 또는 AI에게 "Review 폴더 확인해줘" 요청
2. AI가 각 Review 파일의 처리 방향 제안
3. 사용자 확인 후 → AI repair로 최종 분류
4. 확정된 파일은 적합한 폴더로 이동
5. Review 파일은 처리 후 삭제 (원본 raw는 유지)

## Review 파일 포맷

```yaml
---
review_type: "lint_uncertain | seek_result | doctor_issue"
source_raw: "[[00_Inbox/Raw/...]]"
created_at: "YYYY-MM-DDTHH:MM:SS"
reason: "분류 불확실: task인지 reminder인지 모호"
suggested_folder: "30_Actions/Tasks"
---

# [제목]

## 원본 내용

[raw note 내용]

## AI 제안

[AI가 판단한 분류 근거와 제안]

## 검토 필요 사항

[사용자가 확인해야 할 것]
```
