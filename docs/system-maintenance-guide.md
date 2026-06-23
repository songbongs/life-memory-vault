# 시스템 유지보수 가이드

작성: 2026-06-23  
대상: 이 시스템을 처음 보는 사람도 이해할 수 있게

---

## 1. 이 시스템이 하는 일 (한 줄 요약)

맥미니가 24시간 홈서버로 돌면서, 텔레그램으로 어디서든 AI(Claude)에게 말을 걸거나 메모를 저장할 수 있게 해준다.

---

## 2. 구성 요소 (한눈에)

```
맥미니 (24/7, 절전모드 없음)
│
├── [tmux 세션: ccc]  ← Terminal.app에서 실행 중
│     └── claude(ccc) --yolo
│           └── bun server.ts  ← CCC봇 텔레그램 수신 담당
│
├── [tmux 세션: claude-keepalive]
│     └── 4시간마다 ping → Claude 로그인 토큰 유지
│
├── [launchd] 캡처봇 (com.sangmin.life-memory-collector)
│     └── telegram_collector.py → 메모 자동 저장 (ccc와 무관, 매우 안정적)
│
├── [launchd] OPS 감시자 (com.life-memory.telegram-ops)
│     └── telegram_ops_collector.py → bun이 죽으면 30초 이내 자동 복구
│
└── [launchd] 메모리 볼트 자동화 3개
      ├── life-memory-ai     → 매일 23:00 AI 요약
      ├── life-memory-jobs   → 5분마다 작업 처리
      └── life-memory-lint   → 매일 22:00 메모 정리
```

**봇이 2개라 헷갈릴 수 있음:**

| 봇 | 역할 | 안정성 |
|---|---|---|
| **캡처봇** | 텔레그램 메시지 → 메모 저장 | 매우 안정 (launchd 단독 관리) |
| **CCC봇** (@songbongs_CCC_bot) | Claude AI와 대화 | ccc가 살아야 작동 |

---

## 3. 시행착오 이력 (왜 이 형태가 됐는가)

### ❌ 실패 1 — "6시간마다 봇을 껐다 켜면 되지 않을까?" (2026-06 초)

bun(CCC봇)을 6시간마다 강제로 껐다 켜는 스크립트를 만들었음.

**결과:** 껐는데 켜지지 않아서 오히려 더 자주 끊김. 완전히 역효과.

**지금:** 이 스크립트(`com.claude.telegram-reconnect`)는 **비활성화됨. 절대 다시 켜면 안 됨.**

---

### ❌ 실패 2 — "봇이 죽으면 다른 방법으로 메시지 처리하면 되지 않을까?" (2026-06-14)

bun이 죽어도 메시지를 놓치지 않으려고 별도 수신기를 만들어 `claude -p`로 처리하게 했음.

**결과:**
- 메시지 하나 처리에 2~3분 소요 (매번 새 Claude 세션 시작)
- 같은 봇 토큰으로 두 프로세스가 동시에 메시지를 받아가면서 충돌(409 에러)
- 과거 메시지가 재시작 때마다 다시 처리됨

**지금:** 이 방식 폐기. 단, 수신기 자체(ops_collector)는 "자동 복구 + 알림" 용도로만 재활용 중.

---

### ❌ 실패 3 — "외부에서 봇 연결 상태를 감지할 수 없을까?" (2026-06-15)

`lsof`, `pgrep` 등으로 MCP(봇) 연결 상태를 모니터링하려 했음.

**결과:** 소켓이 열려 있어도 MCP는 끊긴 상태일 수 있음. 외부에서 감지 자체가 불가능한 구조.

**지금:** 이 방향 포기.

---

### ❌ 실패 4 — "`claude auth status`로 토큰을 갱신하면 되지 않을까?" (2026-06-15)

**결과:** 그 명령은 파일을 읽기만 할 뿐 실제 API 호출이 없어서 토큰이 갱신되지 않음.

**올바른 방법:** `claude -p "ping" --output-format json --bare`

---

### ❌ 실패 5 — keepalive에서 `--bare` 빠뜨림 (2026-06-17 발견)

4시간마다 Claude에 ping을 보내 토큰을 유지하는 건 맞는 방향이었으나, `--bare` 플래그를 빠뜨렸음.

**결과:**
- ping 실행 시 텔레그램 플러그인도 같이 로드됨
- 새 bun이 뜨면서 기존 bun과 봇 토큰 충돌 → 기존 bun 사망
- 4시간마다 반복됨

**수정:** `~/claude-auth-keepalive.sh`에 `--bare` 추가 → 이후 bun이 37시간+ 연속 생존.

---

### ✅ 근본 해결 1 — IDE 터미널 의존성 제거 (2026-06-19)

원래 ccc를 Antigravity IDE 터미널에서 실행했는데, IDE가 꺼지면 ccc도 함께 죽는 구조.

**해결:** ccc를 `tmux` 독립 세션(`ccc`)으로 이전. Terminal.app이 켜져 있든 아니든 상관없이 유지됨.

---

### ✅ 근본 해결 2 — 자동 복구 (2026-06-19)

bun이 서버 타임아웃 등으로 가끔 죽는 건 막을 수 없음. 대신 죽으면 30초 이내 자동 복구하도록 `ops_collector`가 tmux ccc 세션에 `/reload-plugins`를 자동으로 입력함.

**복구 성공 시:** 조용히 처리, 알림 없음.  
**복구 실패 시:** 텔레그램으로 알림 → 수동 개입 요청.

---

## 4. 지금 상태 (2026-06-23 기준)

| 구성 요소 | 상태 | 확인 방법 |
|---|---|---|
| CCC봇 (bun) | 실행 중 | `pgrep -fl "bun server.ts"` |
| Claude(ccc) | tmux:ccc 세션에서 실행 중 | `tmux attach -t ccc` |
| keepalive | tmux:claude-keepalive 실행 중 | `tmux ls` |
| 캡처봇 | launchd로 상시 실행 중 | `pgrep -fl "telegram_collector.py"` |
| OPS 감시자 | launchd로 상시 실행 중 | `pgrep -fl "telegram_ops_collector.py"` |

---

## 5. 케이스별 대응 가이드

### 케이스 A — 텔레그램 CCC봇 응답이 없을 때

대부분 자동 복구가 30초 이내에 처리함. 1~2분 기다려도 안 되면 아래 순서로.

```bash
# 1. bun 살아있나 확인
pgrep -fl "bun server.ts"

# 2. bun 없으면 → tmux ccc 세션 접속
tmux attach -t ccc

# 3. 세션 안에서 이 명령 입력
/reload-plugins

# 4. 그래도 안 되면 → ccc 재시작
# → 세션 안에서: Ctrl+C 누르고 → claude 다시 실행
# → 재시작 후 bun 자동 시작됨
```

⚠️ **주의:** bun을 직접 kill(`kill`, `pkill` 등)하면 ccc가 자동으로 재시작하지 않아 더 오래 끊김.

---

### 케이스 B — 맥미니가 재부팅됐을 때

**모든 것이 자동으로 복구됨.** 별도 조치 불필요.

| 구성 요소 | 재부팅 후 복구 방법 |
|---|---|
| ccc tmux 세션 | `com.claude.ccc-session` launchd가 자동 시작 |
| claude-keepalive tmux 세션 | `com.claude.auth-refresh` launchd가 자동 시작 |
| 캡처봇, OPS감시자, 메모리볼트 자동화 | 각자 launchd가 자동 시작 |

재부팅 후 1~2분 뒤 텔레그램 CCC봇에 메시지를 보내서 응답이 오는지만 확인하면 됨.

**ccc가 충돌/종료됐을 때도 30초 후 자동 재시작됨.** (재시작 루프가 tmux 세션 안에 내장되어 있음)

수동으로 ccc를 완전히 멈추고 싶을 때:
```bash
tmux kill-session -t ccc
```
다시 자동 시작하고 싶으면:
```bash
launchctl kickstart gui/$(id -u)/com.claude.ccc-session
```

---

### 케이스 C — Claude 로그인이 풀렸을 때 (23:00 배치 실패 알림이 왔을 때)

캡처봇으로 "⚠️ 예약 작업 실패" 메시지가 오면 로그인이 풀린 것.

```bash
# 1. tmux ccc 세션에 접속
tmux attach -t ccc

# 2. 세션 안에서 재로그인
claude login

# 또는 Claude Code 앱에서 재로그인 후 터미널 세션 재시작
```

재로그인 후 다음 23:00 배치가 밀렸던 작업을 자동으로 처리함.

---

### 케이스 D — 캡처봇(메모 저장 봇)이 응답 없을 때

캡처봇은 launchd가 관리해서 거의 안 죽지만, 혹시 안 되면:

```bash
# 상태 확인
launchctl list | grep life-memory-collector

# 강제 재시작
launchctl kickstart -k gui/$(id -u)/com.sangmin.life-memory-collector

# 또는 수동 실행
python3 /Users/mini-song/Documents/AI-PlayGround/life-memory-vault/scripts/telegram_collector.py --loop
```

---

### 케이스 E — 시스템 전체 상태 점검하고 싶을 때

```bash
# 1. tmux 세션 2개 살아있나
tmux ls

# 2. 핵심 프로세스 3개 살아있나
pgrep -fl "bun server.ts"
pgrep -fl "telegram_collector.py"
pgrep -fl "telegram_ops_collector.py"

# 3. launchd 에이전트 6개 상태 (가운데 숫자가 0이면 정상, -이면 대기)
launchctl list | grep -E "claude|life-memory|sangmin"

# 4. 메모리 볼트 전체 상태 요약
cd /Users/mini-song/Documents/AI-PlayGround/life-memory-vault
python3 scripts/mem.py doctor
```

---

## 6. 절대 하면 안 되는 것

| 행동 | 이유 |
|---|---|
| bun을 직접 kill (pkill, kill 명령) | ccc가 자동 재시작 안 함, 연결 단절 |
| Antigravity IDE 터미널에서 `claude` 실행 | 봇 토큰 충돌로 bun 사망 |
| `com.claude.telegram-reconnect` launchd 재활성화 | 실패 스크립트, 오히려 bun 반복 사망 |
| keepalive 스크립트에서 `--bare` 제거 | 4시간마다 bun 사망 재발 |

---

## 7. 주요 파일·스크립트 위치

| 역할 | 경로 |
|---|---|
| CCC봇 자동 복구 스크립트 | `scripts/telegram_ops_collector.py` |
| 캡처봇 스크립트 | `scripts/telegram_collector.py` |
| Claude 토큰 유지 스크립트 | `~/claude-auth-keepalive.sh` |
| OPS 감시자 로그 | `/tmp/telegram-ops-collector.log` |
| keepalive 로그 | `/tmp/claude-keepalive.log` |
| 메모리 볼트 AI 작업 로그 | `memory-state/launchd-ai-jobs.log` |
| 메모리 볼트 일반 작업 로그 | `memory-state/launchd-jobs.log` |
| 메시지 백업 큐 | `scripts/.telegram-ops-queue.jsonl` |

---

## 8. 빠른 체크리스트 (문제가 생겼을 때 순서대로)

1. `tmux ls` → ccc, claude-keepalive 세션 있나?
2. `pgrep -fl "bun server.ts"` → CCC봇 살아있나?
3. 없으면 → `tmux attach -t ccc` → `/reload-plugins`
4. 그래도 안 되면 → 세션 안에서 `Ctrl+C` → `claude` 다시 실행
5. 재부팅 후라면 → `tmux new-session -s ccc` → `claude` 실행
