# Vault Index

이 문서는 AI agent가 검색 범위를 좁히거나, 노트를 분류할 폴더를 결정할 때 참조하는 정적 가이드다.
사용자가 "어디를 찾아야 하는지" 판단할 때도 사용한다.

## 폴더별 용도 요약

| 폴더 | 저장하는 것 | 검색 예시 |
|---|---|---|
| `00_Inbox/Raw/` | 처리되지 않은 원본 기록 | 최근 저장한 것 전체 |
| `00_Inbox/Processed/` | AI/rule-based lint 처리 마커 (.json) | 처리 이력 |
| `00_Inbox/Review/` | 불확실하게 분류된 노트, 검토 대기 | needs_review 항목 |
| `10_Timeline/Daily/` | 일별 요약, 일기, 하루 회고 | 특정 날짜 기록 |
| `10_Timeline/Weekly/` | 주별 요약 | 이번 주 활동 |
| `10_Timeline/Monthly/` | 월별 요약 | 지난달 돌아보기 |
| `20_Records/Ledger/` | 지출, 수입, 가계부 | 얼마 썼지, 비용 기록 |
| `20_Records/Health/` | 건강 기록, 병원, 약, 검진 | 병원 방문, 처방전 |
| `20_Records/Routine/` | 반복 루틴, 습관 기록 | 운동, 식단, 수면 |
| `20_Records/Maintenance/` | 차량, 가전, 집 등 유지보수/교체 기록 | 와이퍼 교체, 타이어, 에어컨 필터 |
| `20_Records/LifeAdmin/` | 행정, 서류, 보험, 계약, 공공서비스 | 보험 갱신, 계약서, 주민등록 |
| `30_Actions/Tasks/` | 해야 할 일, 할일 목록 | 미완료 작업, 이번 주 할 일 |
| `30_Actions/Shopping/` | 구매 기록, 살 것 목록 | 구매한 것, 장바구니 |
| `30_Actions/Appointments/` | 약속, 예약, 일정 | 병원 예약, 미팅, 약속 |
| `30_Actions/Reminders/` | 리마인더, 알림 필요 항목 | 기념일, 만료일, 갱신일 |
| `30_Actions/Decisions/` | 결정 기록, 의사결정 근거 | 뭘 살지, 어디 갈지 결정 |
| `40_Entities/People/` | 사람 정보, 관계 메모 | 누구 연락처, 어떤 사람 |
| `40_Entities/Groups/` | 그룹, 조직, 커뮤니티 | 회사, 동호회, 가족 |
| `40_Entities/Places/` | 장소, 위치, 지역 | 자주 가는 곳, 주소 |
| `40_Entities/Things/` | 물건, 소유물, 장치 | 내 차, 노트북, 가전 |
| `40_Entities/Situations/` | 상황, 프로젝트 맥락 | 이직 준비, 이사 준비 |
| `40_Entities/Artists/` | 음악 아티스트 정보 | 가수, 밴드 |
| `40_Entities/Songs/` | 개별 곡 정보 | 노래 제목, 가사 메모 |
| `40_Entities/Albums/` | 앨범 정보 | 앨범명, 발매일 |
| `50_Experiences/Trips/` | 여행 기록 | 어디 여행, 숙소, 루트 |
| `50_Experiences/Food_Drink/` | 먹거리 경험 — 맛집, 카페, 베이커리, 음료 | 맛집 저장, 카페 리뷰 |
| `50_Experiences/Events/` | 콘서트, 전시, 행사 참여 기록 | 공연 관람, 축제 |
| `50_Experiences/Visits/` | 방문 기록, 장소 방문 경험 | 미술관, 서점, 공원 방문 |
| `50_Experiences/Music/Listening_Log/` | 음악 청취 기록, 플레이리스트 | 오늘 들은 음악, 분위기별 음악 |
| `50_Experiences/Music/Concerts/` | 공연, 콘서트 관람 기록 | 콘서트 후기 |
| `60_Ideas/Projects/` | 아이디어, 프로젝트 구상 | 만들고 싶은 것, 기획안 |
| `60_Ideas/Writing/` | 글쓰기, 작성 중인 글 | 블로그, 일기, 에세이 초안 |
| `60_Ideas/Products/` | 써보고 싶은 서비스/앱/도구 | 나중에 써볼 것, 추천받은 앱 |
| `60_Ideas/Questions/` | 답을 찾고 싶은 질문, 궁금한 것 | 왜 이럴까, 알아봐야 할 것 |
| `60_Ideas/Playlists/` | 음악 플레이리스트 구성 아이디어 | 드라이브 플레이리스트, 집중 음악 |
| `70_MOCs/` | 카테고리별 노트 목록 진입점 (MOC) | 전체 vault 지도 |
| `80_Assets/` | 원본 파일 (pdf, 이미지, 오디오, 영상) | 첨부파일, 스캔 이미지 |
| `90_System/` | 시스템 문서, 스키마, 로그 | 운영 기록, 설정 |

## 검색 범위 좁히기 가이드

### 유지보수/교체 관련
```
1차: 20_Records/Maintenance/
2차: 40_Entities/Things/ (내 차, 특정 기기 엔티티)
3차: 70_MOCs/Maintenance-MOC.md (있으면)
```

### 음식/카페/맛집
```
1차: 50_Experiences/Food_Drink/
2차: 40_Entities/Places/ (특정 장소 엔티티)
3차: 70_MOCs/Food-MOC.md (있으면)
```

### 음악
```
1차: 70_MOCs/Music-MOC.md (전체 음악 진입점)
2차: 40_Entities/Artists/, 40_Entities/Songs/
3차: 50_Experiences/Music/Listening_Log/
```

### 할 일 / 약속
```
1차: 30_Actions/Tasks/ 또는 30_Actions/Appointments/
2차: 10_Timeline/Daily/ (날짜 연결된 경우)
```

### 비용/구매
```
1차: 20_Records/Ledger/ (지출 기록)
2차: 30_Actions/Shopping/ (구매 목록)
```

### 사람/관계
```
1차: 40_Entities/People/
2차: 40_Entities/Groups/
```

### 아이디어/서비스/앱
```
1차: 60_Ideas/Products/ (써보고 싶은 서비스)
2차: 60_Ideas/Projects/ (직접 만들 아이디어)
```

### 여행
```
1차: 50_Experiences/Trips/
2차: 40_Entities/Places/ (여행지 엔티티)
```

## AI 검색 프로토콜

AI agent가 mem-seek를 실행할 때 권장 순서:

1. 이 문서에서 관련 폴더 파악
2. 해당 폴더의 MOC 파일 확인 (`70_MOCs/` 또는 폴더 내 `_index.md`)
3. MOC의 노트 목록으로 대상 파일 결정
4. 대상 파일 전체 내용을 컨텍스트에 로딩
5. 의미 기반 합성 답변 생성 (출처 포함)

단순 키워드 검색만으로 답변하지 말 것. 관련 폴더 전체를 확인 후 답변할 것.
