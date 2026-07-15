# CCC봇 연결 끊김 이슈 — 전체 이력 및 조치 기록

작성 시작: 2026-06-16  
최종 업데이트: 2026-07-15  
상태: **2차 근본 해결 완료** (시도 1 job 재부팅 부활 차단 + 자동복구 명령 수리)

---

## 환경 개요

```
맥미니 (24/7 홈서버, 절전 없음)
│
├── Antigravity IDE → 터미널에서 ccc --yolo 실행 (구 방식, 2026-06-19 이전)
│   └── ccc (Claude Code CLI)
│       └── bun server.ts (텔레그램 MCP 플러그인, ccc 자식 프로세스)
│
└── [신 방식, 2026-06-19 이후]
    Terminal.app → tmux 세션 "ccc" → ccc --yolo
        └── bun server.ts (동일)
```

- 사용자는 텔레그램(@songbongs_CCC_bot)으로 ccc에 메시지를 보냄
- bun이 죽으면 텔레그램 메시지가 ccc에 전달되지 않음
- `telegram_ops_collector.py` (launchd 관리): bun 감시 + 안전망

---

## 핵심 구조 이해 (왜 끊기는가)

bun(MCP)은 ccc의 **자식 프로세스**다. ccc가 없으면 bun도 없다.

```
Antigravity IDE 앱
  └── zsh 터미널
      └── ccc (claude --channels plugin:telegram)
          └── bun server.ts  ← 여기가 텔레그램 수신 담당
```

이 체인에서 **어느 하나라도 끊기면** bun이 사망한다.

끊기는 원인은 크게 세 가지:
1. **WarmLifecycle 서버 타임아웃**: Anthropic 서버가 유휴 세션을 강제 종료 (하루 1~2회 발생)
2. **외부 스크립트가 bun을 kill**: 잘못 만든 자동화가 bun을 직접 kill
3. **IDE 터미널 의존성**: IDE가 꺼지거나 터미널이 죽으면 ccc도 함께 사망

---

## 이슈 타임라인 및 조치 이력

### ❌ 시도 1 — 6시간마다 bun 강제 재시작 (2026-06 초)

**현상:** 정기적으로 연결이 끊겨 텔레그램 응답이 없어짐  
**시도:** `claude-telegram-reconnect.sh` + launchd `com.claude.telegram-reconnect.plist`로 6시간(06:32, 12:32, 18:32, 00:32)마다 bun을 kill하고 재시작  
**실패 이유:**
- bun을 외부에서 kill해도 ccc가 자동으로 재시작하지 않음
- 오히려 bun이 죽은 채 방치되는 상황이 반복됨
- "bun 미실행 상태"로 계속 통과하며 문제 악화  
**조치:** 2026-06-16 비활성화 (`launchctl unload`)  
**현재 상태:** plist 파일 잔존하나 unload됨. **절대 재활성화 금지**

---

### ❌ 시도 2 — 독립 수신기 + claude -p 처리 (2026-06-14)

**현상:** bun이 죽으면 메시지가 완전 유실됨  
**시도:** `telegram_ops_collector.py`를 만들어 bun 대신 텔레그램을 직접 폴링하고 메시지를 `claude -p`로 처리  
**실패 이유:**
- `claude -p`는 단순 메시지 하나도 2~3분 소요 (전체 Claude Code 세션을 새로 시작하기 때문)
- 같은 봇 토큰으로 두 프로세스가 동시 폴링 → 409 Conflict 충돌
- launchctl reload 시 인스턴스가 겹쳐 중복 처리 발생
- offset 미저장으로 재시작 시 과거 메시지가 재처리됨  
**결론:** CCC봇의 본질(양방향 대화, 현재 세션 맥락)이 파괴됨. `claude -p` 방식은 구조적으로 부적합  
**남긴 것:** ops_collector는 메시지 큐 저장 + 알림 발송 용도로 역할을 재정의하여 유지

---

### ❌ 시도 3 — MCP 연결 상태 외부 감지 (2026-06-15)

**현상:** bun 프로세스가 살아있어도 MCP가 끊긴 상태(응답 없음)가 있음  
**시도:** `lsof`, `pgrep`, 소켓 확인 등으로 MCP 연결 상태를 외부에서 모니터링  
**실패 이유:**
- MCP "끊김"은 ccc 내부 상태. `lsof`로 보면 소켓(fd)이 열려있어도 MCP는 standby일 수 있음
- **외부에서 감지 자체가 불가능한 구조**  
**결론:** 이 방향 자체가 막힌 길

---

### ❌ 시도 4 — claude auth status 로 토큰 갱신 (2026-06-15)

**시도:** launchd로 `claude auth status` 주기 실행  
**실패 이유:** 파일을 읽기만 할 뿐 실제 API 호출이 없어 토큰이 갱신되지 않음  
**올바른 방법:** `claude -p "ping" --output-format json --bare`

---

### ✅ 조치 1 — keepalive에 --bare 추가 (2026-06-17)

**현상:** keepalive 스크립트(`claude -p "ping"`)가 4시간마다 실행될 때마다 bun이 죽음  
**원인 파악:**
- `claude -p` 실행 시 `--bare` 플래그가 없으면 텔레그램 플러그인도 함께 로드됨
- 새 bun 인스턴스 기동 → 기존 bun과 봇 토큰 충돌(409) → 기존 bun 사망
- `claude -p` 세션 종료 시 새 bun도 사망 → 4시간마다 반복  
**수정:** `~/claude-auth-keepalive.sh`에 `--bare` 플래그 추가  
**효과:** 수정 이후 bun이 37시간+ 연속 생존 (이전 대비 극적 개선)

---

### ✅ 조치 2 — ops_collector 버그 수정 2건 (2026-06-19)

**버그 1: 미디어 메시지에서 빈 텍스트 저장**  
원인: 사진·스티커 등 text 필드 없는 메시지에서 `None`이 큐에 저장됨  
수정: `enqueue()`에 fallback 체인 추가 (caption → sticker emoji → `[미디어 메시지]`)

**버그 2: 크래시 시 메시지 유실**  
원인: offset을 enqueue 전에 저장 → 크래시 시 해당 메시지가 처리된 것으로 기록됨  
수정: enqueue 완료 후 offset 저장 (순서 변경)

---

### ✅ 조치 3 — tmux 전환 + 자동 복구 (2026-06-19, 오늘)

**근본 문제:** ccc가 Antigravity IDE 터미널에서 실행 중 → IDE 의존성, 불안정  
**해결 방향:** ccc를 독립된 tmux 세션으로 이전 + bun 사망 시 자동 복구

**구현 내용 (`scripts/telegram_ops_collector.py`):**
```
bun 사망 감지 (30초 이내)
    ↓
tmux send-keys -t ccc /reload-plugins Enter
    ↓ (20초 대기)
    ↓
bun 살아났나?
  예 → 무음 처리 (사용자 알림 없음)  ← 정상 케이스
  아니오 → 텔레그램 알림 발송 + 폴링 인수
```

**사용자 액션 (1회성 셋업):**
1. Antigravity IDE 터미널의 `ccc --yolo` 종료
2. Terminal.app 열기 → `tmux new-session -s ccc`
3. `ccc --yolo` 실행
4. `Ctrl+B D`로 탈출 후 Terminal.app 창 닫기 가능

**규칙:** Antigravity IDE 터미널에서 `ccc --yolo` 실행 금지 (bun 충돌 발생)

---

### 🔥 재발 사건 — 폐기된 "시도 1" job이 재부팅으로 부활 (2026-07-15)

**증상:** 2026-07-15 새벽, CCC봇 연결이 반복적으로 끊기고 "봇 꺼짐" 알림이 계속 발송됨. 05:29경 시작해 약 33분간 다운.

**원인 분석 — 두 결함이 겹쳐 실제 장애가 됨:**

**원인 1 (근본): 6월에 폐기·금지한 "시도 1"(6시간 강제 kill) job이 재부팅으로 되살아남**
- 2026-06-16 조치 당시 `launchctl unload`만 하고 **plist 파일을 남겨둠 + `Disabled` 키 미설정**.
- macOS는 로그인/부팅 시 `~/Library/LaunchAgents/*.plist`를 **전부 자동 로드**함.
- **2026-07-14 17:28 재부팅** → 금지된 `com.claude.telegram-reconnect`가 조용히 재로드됨.
- 6시간 주기로 bun을 kill: 부팅 후 23:29, 05:29 두 차례 실행(`runs=2`, `reconnect.log`와 일치).
- 05:29:34 kill이 곧바로 장애로 이어짐 → ops 감지(05:29:56) → 자동복구 실패 → 알림 폭탄(05:40/05:50/06:01) → 06:03 복구.

**원인 2 (안전망 붕괴): `/reload-plugins` 자동복구 명령이 깨져 있어 100% 실패**
- `try_tmux_recovery()`가 `tmux send-keys`를 `-l`(리터럴) 없이 보내고 텍스트+Enter를 한 호출로 전송.
- 그 결과 입력이 `reload-plugins/reload-plugins`로 뭉개져 맨 앞 `/`가 사라짐 → 슬래시 명령이 아니라 일반 프롬프트로 처리됨 → ccc가 "그런 스킬 없음"으로 응답, 복구 실패.
- 즉 조치 3의 안전망이 구현 버그로 무력화된 상태였음. WarmLifecycle 타임아웃으로 인한 정상 사망까지 전부 장애로 번짐.

**조치 (2026-07-15):**

| # | 조치 | 상세 |
|---|---|---|
| A | 자동복구 명령 수리 | `try_tmux_recovery()`: `Escape` → `C-u`(입력줄 비우기) → `send-keys -l /reload-plugins`(리터럴) → `Enter`(분리 호출)로 변경. 백업 `scripts/telegram_ops_collector.py.bak-20260715_083139` |
| B | 시도 1 job 영구 제거 | `launchctl bootout` 후 plist·스크립트를 `.rollback/telegram-reconnect-removed-20260715_084755/`로 이동. **파일 자체가 없어 재부팅 자동로드 불가.** |
| C | 부팅 가드 추가 | `~/ccc-startup.sh`(부팅마다 실행)에 가드 삽입: `com.claude.telegram-reconnect`가 로드되어 있거나 plist가 재등장하면 즉시 `bootout` + `.disabled` 격리. 어떤 경로로든 부활해도 자가 차단. |

**교훈 / 재발 방지 규칙:**
- **폐기한 launchd job은 `unload`로 끝내지 말 것.** 반드시 **plist 파일을 삭제**하거나 `<key>Disabled</key><true/>`를 넣어 재부팅 자동로드를 원천 차단해야 한다. (이번 재발의 뿌리)
- tmux로 슬래시 명령을 보낼 때는 **반드시 `send-keys -l`(리터럴)** 을 쓰고 `Enter`는 별도 호출로 분리한다.

**후속 정리 — GitHub 반영 & 브랜치 통일 (2026-07-15):**
- 위 조치를 커밋하던 중, 저장소가 GitHub에 **6/19까지만 푸시**된 상태이고 로컬 커밋 4개가 미푸시임을 발견.
- 또한 브랜치가 둘로 분리: 기본 브랜치 `main`은 6/3 초기 상태에서 방치, 실제 작업은 전부 `master`에 존재(main보다 38커밋 앞섬, 갈라짐 0 → `master`가 `main`을 완전 포함).
- 정리: ① 미푸시 커밋 + 오늘 조치를 `master`에 커밋·푸시 → ② `main`을 `master`로 fast-forward 푸시(충돌 0) → ③ 중복 `master` 브랜치를 로컬·원격 모두 삭제하고 `main` 하나로 통일.
- 결과: 이후 **브랜치는 `main` 단일 운영**. 작업 종료 시 커밋+푸시까지 완료하는 것을 원칙으로 한다.

---

## 현재 상태 (2026-07-15 갱신)

| 구성 요소 | 상태 | 설명 |
|---|---|---|
| ccc | Terminal.app tmux:ccc 세션 | IDE 독립적으로 실행 |
| bun (MCP) | ccc 자식 프로세스 | WarmLifecycle 타임아웃 시 ops_collector가 자동 복구 |
| ops_collector | launchd (상시 실행) | bun 감시 + 자동 복구 + 큐 저장 + 알림. **자동복구 명령 수리됨(2026-07-15)** |
| keepalive | tmux:claude-keepalive | 4시간마다 `claude -p "ping" --bare` |
| 캡처봇 | launchd (상시 실행) | ccc와 무관, 안정적 |
| ~~telegram-reconnect~~ | **완전 제거됨 (2026-07-15)** | 시도 1 job. plist·스크립트 삭제로 재부팅 자동로드 불가 |
| 부팅 가드 | `~/ccc-startup.sh` 내장 | telegram-reconnect 부활 감지 시 자동 bootout + `.disabled` 격리 |

---

## 향후 문제 발생 시 확인 순서

### 텔레그램 응답 없을 때

```bash
# 1. bun 살아있나 확인
pgrep -fl "bun server.ts"

# 2. 없으면 tmux 세션 확인
tmux ls

# 3. ccc 세션 접속
tmux attach -t ccc

# 4. /reload-plugins 수동 입력
/reload-plugins

# 5. 그래도 안 되면 ccc 재시작
# → Ctrl+C → ccc --yolo
```

### ops_collector 로그 확인

```bash
# 최근 로그 (자동 복구 시도 기록 포함)
tail -50 /tmp/telegram-ops-collector.log

# ops_collector 살아있나
pgrep -fl "telegram_ops_collector"
```

### 주의사항

- **Antigravity IDE 터미널에서 ccc --yolo 실행 금지** → bun 충돌
- **bun 외부 kill 금지** → ccc가 재시작하지 않아 연결 단절
- **keepalive에서 --bare 제거 금지** → 4시간마다 bun 사망 재발
- **`com.claude.telegram-reconnect` 재생성/재활성화 금지** → 시도 1의 실패 방식. 되살아나면 ccc-startup.sh 가드가 자동 격리함
- **폐기 launchd job은 `unload`만 하지 말 것** → plist 파일 삭제 또는 `Disabled` 키 필수 (안 그러면 재부팅 자동로드로 부활, 2026-07-15 재발 사례)
- **tmux 슬래시 명령 전송 시 `send-keys -l`(리터럴) 필수** → 없으면 입력 뭉개짐(`reload-plugins/reload-plugins`)
- ccc 재시작 시 이 세션의 대화 이력 사라짐 (memory에 기록된 것만 유지)

---

## 관련 파일

| 파일 | 역할 |
|---|---|
| `scripts/telegram_ops_collector.py` | bun 감시, tmux 자동 복구, 큐 저장, 알림 |
| `scripts/telegram_ops_send.py` | 텔레그램 직접 발송 (curl 래퍼) |
| `~/claude-auth-keepalive.sh` | 4시간 keepalive (`--bare` 필수) |
| `~/Library/LaunchAgents/com.claude.auth-refresh.plist` | keepalive launchd |
| `~/ccc-startup.sh` | 부팅 시 ccc tmux 세션 기동 + **telegram-reconnect 부활 차단 가드 내장** |
| ~~`~/Library/LaunchAgents/com.claude.telegram-reconnect.plist`~~ | **완전 제거됨 (2026-07-15)**. 백업: `.rollback/telegram-reconnect-removed-20260715_084755/` |
| `/tmp/telegram-ops-collector.log` | ops_collector 실시간 로그 |
| `scripts/.telegram-ops-queue.jsonl` | 메시지 큐 (bun 죽은 동안 저장) |
