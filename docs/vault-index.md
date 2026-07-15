# Vault Index

이 문서는 AI agent가 검색 범위를 좁히거나, 노트를 분류할 폴더를 결정할 때 참조하는 정적 가이드다.
사용자가 "어디를 찾아야 하는지" 판단할 때도 사용한다.

> 2026-07-15 갱신: 실제 폴더별 파일 수를 세어 현재 사용 중인 폴더와, 2026-06-14 무렵 구조 개편 이후
> 더 이상 쓰이지 않는 legacy 폴더를 구분했다. `prompts/ai-lint.md`의 "폴더 배치" 표가 실제 분류 기준의
> 원본(source of truth)이니, 폴더가 바뀌면 이 문서도 같이 갱신할 것.

## 현재 사용 중인 폴더 (분류·검색 1순위)

| 폴더 | 저장하는 것 | 검색 예시 |
|---|---|---|
| `00_Inbox/Raw/` | 처리되지 않은 원본 기록 | 최근 저장한 것 전체 |
| `00_Inbox/Processed/` | AI/rule-based lint 처리 마커 (.json) | 처리 이력 |
| `00_Inbox/Review/` | 불확실하게 분류된 노트, 검토 대기 | needs_review 항목 |
| `10_Daily/` | 일별 저널, 분류 애매한 일상 메모 (journal 타입) | 특정 날짜 기록, 그날 뭐 했지 |
| `20_Records/Maintenance/` | 차량, 가전, 집 등 유지보수/교체 기록 | 와이퍼 교체, 타이어, 에어컨 필터 |
| `20_Records/Ledger/` | 지출, 수입, 가계부 | 얼마 썼지, 비용 기록 |
| `20_Records/Health/` | 건강 기록, 병원, 약, 검진 | 병원 방문, 처방전 |
| `30_Actions/Tasks/` | 해야 할 일, 할일 목록 | 미완료 작업, 이번 주 할 일 |
| `30_Actions/Appointments/` | 약속, 예약, 일정 | 병원 예약, 미팅, 약속 |
| `30_Actions/Reminders/` | 반복 알림, 픽업 시간, 갱신일 | 버스 하차 시간, 만료일 |
| `40_Notes/Saves/` | **저장 노트 최대 폴더** — GitHub·웹서비스·아이디어·북마크 (save/project/product/idea 타입) | 나중에 써볼 서비스, 관심 GitHub 프로젝트 |
| `40_Notes/Music/` | 노래·플레이리스트 기록 (song/playlist 타입) | 저장한 노래, 플레이리스트 |
| `40_Notes/Things/` | 사용 중인 도구·기기의 가이드/사용법, 물건 자체 | Cokacdir 사용법, VNC 접속 주소, 내 차 |
| `40_Notes/Experiences/` | 맛집·카페·여행 경험 (food_drink/trip 타입) | 지난번 간 맛집, 여행 기록 |
| `40_Notes/People/` | 사람 관련 구조화 노트 (아직 생성 사례 없음, 향후 대비) | — |
| `40_Notes/Places/` | 장소 구조화 노트 | 자주 가는 곳 |
| `90_System/Index/` | **MOC(색인) 실제 위치** — Ideas-MOC, Life-Memory-MOC, Maintenance-MOC, Music-MOC, 홈 | 카테고리별 노트 목록, 전체 vault 지도 |
| `80_Assets/Extracts/` | enrich로 추출한 웹 원문 영구 보관본 | (직접 검색 대상 아님, 노트에서 링크로 참조) |
| `80_Assets/Originals/` | 텔레그램 원본 이미지·파일 | 첨부 사진 |
| `90_System/Rules/` | 학습된 분류 규칙 (learned-rules.json) | — |

## Legacy 폴더 — 2026-06-14 이후 갱신 없음, 검색 1순위에서 제외할 것

구조 개편(2026-06-14 전후) 이전에 쓰던 폴더다. 과거(6월 14일 이전) 기록을 찾을 때만 2차·3차로 확인.
`70_MOCs/`는 특히 `90_System/Index/`와 파일명이 겹치니 혼동하지 말 것 — `70_MOCs/`가 더 오래된 사본이다.

| 폴더 | 상태 |
|---|---|
| `10_Timeline/Daily/` | 6/14 이후 정지. 현재는 `10_Daily/` 사용 |
| `10_Timeline/Weekly/`, `10_Timeline/Monthly/` | 파일 없음, 미사용 |
| `20_Records/LifeAdmin/`, `Routine/` | 파일 없음, 미사용 |
| `30_Actions/Shopping/`, `Decisions/` | 파일 없음, 미사용 |
| `40_Entities/*` (People/Groups/Places/Things/Situations/Artists/Songs/Albums) | 6/7~6/10 무렵 초기 실험 데이터 몇 개만 있고 대부분 오분류 상태로 방치됨. 지금은 `40_Notes/*`가 실제 저장 위치 |
| `50_Experiences/*` | 파일 없음, 완전 미사용 (food_drink/trip은 이제 `40_Notes/Experiences/`) |
| `60_Ideas/Products/`, `Projects/`, `Playlists/` | 6/14 이전 저장 노트 21개 남아있음 (지금은 신규 저장이 전부 `40_Notes/Saves/`로 감). 오래된 항목 찾을 때만 확인 |
| `70_MOCs/` | 6/13 이후 갱신 안 됨. **`90_System/Index/`가 현재 진짜 MOC**, `70_MOCs/`는 보지 말 것 |

## 검색 범위 좁히기 가이드

### 유지보수/교체 관련
```
1차: 20_Records/Maintenance/
2차: 90_System/Index/Maintenance-MOC.md
```

### 음식/카페/맛집/여행
```
1차: 40_Notes/Experiences/
2차: 90_System/Index/Life-Memory-MOC.md ("최근 추가된 노트" 섹션)
```

### 음악
```
1차: 90_System/Index/Music-MOC.md
2차: 40_Notes/Music/
```

### 할 일 / 약속 / 리마인더
```
1차: 30_Actions/Tasks/, 30_Actions/Appointments/, 30_Actions/Reminders/
2차: 10_Daily/ (날짜 연결된 경우)
```

### 비용/구매
```
1차: 20_Records/Ledger/
```

### 도구 사용법 / 기기·물건
```
1차: 40_Notes/Things/
```

### 아이디어/서비스/앱/GitHub 프로젝트
```
1차: 40_Notes/Saves/ (현재 저장 위치, 대부분 여기)
2차: 90_System/Index/Ideas-MOC.md
3차(과거분만): 60_Ideas/Products/, 60_Ideas/Projects/ (2026-06-14 이전 저장분)
```

### 일상/저널
```
1차: 10_Daily/
```

## AI 검색 프로토콜

AI agent가 mem-seek를 실행할 때 권장 순서:

1. 이 문서에서 관련 폴더 파악 (Legacy 폴더는 "과거 기록 찾기"가 아니면 건너뛴다)
2. 해당 폴더의 MOC 파일 확인 — **`90_System/Index/`** 만 본다 (`70_MOCs/`는 legacy)
3. MOC의 노트 목록으로 대상 파일 결정
4. 대상 파일 전체 내용을 컨텍스트에 로딩
5. 의미 기반 합성 답변 생성 (출처 포함)

단순 키워드 검색만으로 답변하지 말 것. 관련 폴더 전체를 확인 후 답변할 것.
`mem.py seek`는 볼트 전체를 훑는 키워드 스코어링이라 폴더를 잘못 좁혀도 안전망 역할을 하지만,
1~2단계에서 legacy 폴더만 보고 "없다"고 잘못 결론 내지 않도록 주의한다.
