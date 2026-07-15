# MOC 템플릿 및 유지 규칙

AI lint가 새 structured note를 생성하거나 엔티티를 업데이트할 때 반드시 해당 MOC에 항목을 추가한다.

> 2026-07-15: MOC 실제 위치는 `90_System/Index/`다. `70_MOCs/`는 2026-06-13 이후 갱신이
> 멈춘 legacy 사본이니 새로 만들거나 참조할 때 절대 쓰지 않는다.

## MOC 파일 목록

| MOC 파일 | 담당 카테고리 | 상태 |
|---|---|---|
| `90_System/Index/Life-Memory-MOC.md` | 전체 vault 진입점 | 존재, 활성 |
| `90_System/Index/Music-MOC.md` | 음악 전체 | 존재, 활성 |
| `90_System/Index/Maintenance-MOC.md` | 유지보수/교체 기록 | 존재, 활성 |
| `90_System/Index/Ideas-MOC.md` | 아이디어/서비스/프로젝트 | 존재, 활성 |
| `90_System/Index/Food-MOC.md` | 맛집/카페/음식 경험 | 미생성 (필요 시 아래 규칙대로 생성) |
| `90_System/Index/People-MOC.md` | 사람/관계 | 미생성 |
| `90_System/Index/Travel-MOC.md` | 여행 | 미생성 |
| `90_System/Index/Health-MOC.md` | 건강/병원 | 미생성 |
| `90_System/Index/Tasks-MOC.md` | 할 일/약속/결정 | 미생성 |

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
4. MOC 파일이 없으면 `90_System/Index/`에 신규 생성

## MOC가 없는 카테고리

MOC가 아직 없는 카테고리에 노트를 추가할 때는:
1. `90_System/Index/[카테고리]-MOC.md` 파일 생성
2. 이 문서의 MOC 파일 목록에 추가
3. Life-Memory-MOC.md의 목차에도 링크 추가
