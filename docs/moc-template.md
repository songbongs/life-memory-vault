# MOC 템플릿 및 유지 규칙

AI lint가 새 structured note를 생성하거나 엔티티를 업데이트할 때 반드시 해당 MOC에 항목을 추가한다.

## MOC 파일 목록

| MOC 파일 | 담당 카테고리 |
|---|---|
| `70_MOCs/Life-Memory-MOC.md` | 전체 vault 진입점 |
| `70_MOCs/Music-MOC.md` | 음악 전체 |
| `70_MOCs/Maintenance-MOC.md` | 유지보수/교체 기록 |
| `70_MOCs/Food-MOC.md` | 맛집/카페/음식 경험 |
| `70_MOCs/People-MOC.md` | 사람/관계 |
| `70_MOCs/Travel-MOC.md` | 여행 |
| `70_MOCs/Ideas-MOC.md` | 아이디어/서비스/프로젝트 |
| `70_MOCs/Health-MOC.md` | 건강/병원 |
| `70_MOCs/Tasks-MOC.md` | 할 일/약속/결정 |

## MOC 항목 추가 형식

```markdown
## [카테고리명]

- [[노트 경로|표시 제목]] — 한 줄 설명 (YYYY-MM-DD)
```

예시:
```markdown
## 차량 유지보수

- [[20_Records/Maintenance/차량 와이퍼 교체 2026-06-01|와이퍼 교체]] — 전면+후면, 보쉬 (2026-06-01)
- [[20_Recrods/Maintenance/타이어 교환 2025-11|타이어 교환]] — 4개 전체 교체 (2025-11-15)
```

## AI lint의 MOC 업데이트 규칙

1. 새 structured note를 생성하면 해당 카테고리 MOC에 항목 추가
2. 기존 엔티티 페이지를 업데이트하면 Life-Memory-MOC의 마지막 업데이트 날짜 갱신
3. 새로운 카테고리가 생기면 이 파일에 MOC 파일 목록 추가
4. MOC 파일이 없으면 `70_MOCs/`에 신규 생성

## MOC가 없는 카테고리

MOC가 아직 없는 카테고리에 노트를 추가할 때는:
1. `70_MOCs/[카테고리]-MOC.md` 파일 생성
2. 이 문서의 MOC 파일 목록에 추가
3. Life-Memory-MOC.md의 목차에도 링크 추가
