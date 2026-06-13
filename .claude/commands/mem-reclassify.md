---
description: Life Memory Vault reclassify — fix a note's wrong category by natural language and learn it for next time
allowedTools: Bash, Read, Write, Edit, Glob, Grep
---

# mem-reclassify

사용자가 "이거 task 아니라 idea야"처럼 노트 분류가 틀렸다고 하면, 해당 노트를 올바른
`memory_type`으로 재분류하고 **학습 루프(③d)에 반영**한다. raw 원본은 절대 건드리지 않는다.

## 절차

1. **대상 노트 찾기**: 사용자가 경로를 주면 그대로. 아니면 `python3 scripts/mem.py seek "키워드"`
   로 후보를 찾아 확인한다(여러 개면 어느 것인지 사용자에게 물음).
2. **올바른 memory_type 파악**: task / idea / product / maintenance / appointment / food_drink …
   폴더 배치는 자동(타입별 기본 폴더).
3. **학습 키워드(signal) 정하기**: 이 분류를 결정한 핵심 키워드를 짧고 구체적으로
   (예: "프로젝트", "송금"). 사용자가 명시 안 하면 노트에서 추출하되 너무 일반적인 단어
   (예: "메모", "내용")는 피한다.
4. **dry-run으로 영향 확인** (변경 없음):
   ```bash
   python3 scripts/mem.py reclassify "<노트경로>" --type <새type> --signal "<키워드>"
   ```
   이동할 폴더와 갱신될 `[[wikilink]]` 수를 사용자에게 보여준다.
5. **적용**:
   ```bash
   python3 scripts/mem.py reclassify "<노트경로>" --type <새type> --signal "<키워드>" --apply
   ```
   노트를 새 폴더로 이동 + 마커 갱신 + 옛 `[[wikilink]]`를 새 경로로 전체 갱신 + signal 학습.
6. **결과 보고**: "X를 idea로 옮기고 '프로젝트' 키워드를 학습했어요. 같은 키워드가 한 번 더
   확인되면 다음부터 자동으로 idea로 분류됩니다."

## 주의

- signal은 학습의 핵심이다. **2회 일관 확인 시 자동 분류 규칙(active)으로 승격**되고, 모순되면
  (같은 키워드, 다른 분류) `blocked` 처리되어 자동 적용되지 않는다.
- MOC는 다음 AI lint에서 새 폴더 기준으로 더 다듬어질 수 있다.
- 확신이 없거나 노트가 여러 개로 모호하면 추측하지 말고 사용자에게 확인한다.

## 자연어 트리거

- "이거 task 아니라 idea야", "이 노트 분류 틀렸어", "X를 product로 바꿔줘"
- "방금 그거 idea로 다시 분류해줘"
- "this should be a task, not a note"
