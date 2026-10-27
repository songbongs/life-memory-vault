# life-memory-vault 작업 지침

## 쉬운 설명과 근거 원칙

- 사용자는 비개발자 바이브코딩 입문자다. 쉬운 말과 쉬운 예시로 설명한다.
- 감이나 추정으로 확정하지 않는다. 데이터, 코드, 실행 결과, 볼트 기록으로 확인한 것만 결론으로 말한다.
- 확인하지 못한 내용은 "확인 못 함" 또는 "추정"이라고 분리한다.

## 프로젝트 정체

이 프로젝트는 개인 기억을 모아두는 별도 Obsidian 볼트와, 그 볼트를 정리·점검하는 도구 모음이다.

- 원본 기록은 먼저 보존한다.
- 정리는 나중에 한다.
- 나중에 AI가 쉽게 다시 찾을 수 있게 만든다.

관련 운영 기록은 Google Drive의 `my-AI-Playground` 볼트에 있다:

```text
10_Projects/life-memory-vault/
```

작업 시작 전에는 그곳의 `00_Project Atlas.md`, 최근 `05_작업 로그.md`, 관련 `04_이슈와 해결 기록.md`를 먼저 확인한다.

## 절대 지킬 것

1. `00_Inbox/Raw`의 원본 노트는 고치거나 지우지 않는다.
2. 분류가 애매하면 마음대로 정하지 말고 `00_Inbox/Review`로 보낸다.
3. 원본과 이어지는 `source_raw` 링크를 보존한다.
4. 작업 큐를 처리했다면 상태를 `done` 또는 `failed`로 남긴다.
5. 로컬·무료 수단을 먼저 쓴다. 과금 API는 먼저 확인한다.
6. 노트를 옮기거나 이름을 바꾸면 `00_Inbox/Processed/*.json`의 `structured` 경로도 같이 고친다.
7. lint·enrich 뒤에는 프론트매터에 `tags:`가 중복으로 생기지 않았는지 확인한다.

## 자주 쓰는 점검 명령

```bash
python3 -B scripts/vault_audit.py
python3 scripts/mem.py doctor
python3 scripts/process_jobs.py --once --dry-run
```

`vault_audit.py`는 읽기 전용 점검이다. 모든 핵심 수치가 0이면 정상이다.

## 텔레그램/CCC 봇으로 받은 요청

텔레그램으로 작업 요청을 받은 상황이면, 작업 시작을 먼저 짧게 알린다.

예:

- "lint 정리할게요, 잠시만요 ⏳"
- "enrich 처리 시작합니다 ⏳"
- "확인해볼게요 ⏳"

오래 걸리는 명령은 백그라운드로 돌리고, 끝나면 결과를 보고한다.

## Python 권한 문제가 날 때

`Operation not permitted`, `python 권한`, `lint 권한 오류` 같은 문제가 나오면
`bash ~/fix-python-tcc.sh`를 바로 전경 실행하지 않는다.

먼저 다른 읽기 방법을 시도한다:

```bash
/bin/cat <파일>
/usr/bin/head -50 <파일>
/bin/cp <파일> <작업폴더>/
```

그래도 안 될 때만 사용자에게 권한 팝업 가능성을 알리고, 스크립트는 백그라운드로 실행한다.

## 작업 기록

이 프로젝트에서 실제 작업을 했으면 Google Drive 기록에 남긴다.

```text
10_Projects/life-memory-vault/05_작업 로그.md
```

되풀이될 만한 함정이면 이슈 기록에도 남긴다.

```text
10_Projects/life-memory-vault/04_이슈와 해결 기록.md
```
