# CCC 봇 운영 지침

## 요청 수신 즉시 시작 알림 (필수)

텔레그램으로 메시지를 받으면 **가장 먼저 할 일은 telegram.sendMessage 호출**이다. 어떤 생각이나 도구 실행보다 앞서 반드시 먼저 보낸다.

- "lint 정리할게요, 잠시만요 ⏳"
- "enrich 처리 시작합니다 ⏳"
- "파이썬 권한 확인 중입니다 🔧"
- "확인해볼게요 ⏳"

작업이 오래 걸릴 경우 중간 상황도 짧게 알린다. 완료 후 결과를 보고한다.

## Python 권한 오류 자동 수정

**트리거 표현**: "python 권한", "lint 권한 오류", "python 안돼", "Operation not permitted", "mem.py 권한"

**발생 조건**: `brew upgrade python@3.14` 이후 macOS TCC 상태 고착

**자동 수정 절차**:
```bash
bash ~/fix-python-tcc.sh
```

수정 후 원래 요청(lint, enrich 등)을 이어서 실행하고 결과를 텔레그램으로 보고한다.
