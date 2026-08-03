# 시스템 유지보수 가이드

작성: 2026-06-23  
최종 업데이트: 2026-07-28  
대상: 이 시스템을 처음 보는 사람도 이해할 수 있게

> 📌 **2026-07-23부터 keepalive(4시간마다 ping)는 없어졌다.** 아래 "실패 4·5"의 keepalive 관련 내용은 과거 이력이다. 지금은 **키체인 직접 로그인 + 매일 새벽 4시 전체 재시작** 방식이다. 자세한 내용은 "근본 해결 3" 절 참조.

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
├── [launchd] 일일 재시작 (com.claude.ccc-daily-restart)
│     └── 매일 04:00 ccc를 통째로 재시작 → 로그인 토큰도 함께 갱신
│        ※ 예전의 claude-keepalive(4시간 ping) 세션은 2026-07-23 폐지됨
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

**지금:** 이 스크립트(`com.claude.telegram-reconnect`)는 **완전 제거됨(2026-07-15). 절대 다시 만들면 안 됨.**

> ⚠️ **2026-07-15 재발 사건:** 2026-06엔 `launchctl unload`만 하고 plist 파일을 남겨둔 탓에, **2026-07-14 재부팅 시 자동으로 다시 로드**되어 6시간마다 bun을 kill → 봇 반복 끊김(약 33분 다운)이 재발했다. 이후 ① plist·스크립트를 파일째 삭제하고 ② `~/ccc-startup.sh`에 "부활 감지 시 자동 격리" 가드를 추가해 원천 차단했다. 교훈: **폐기 job은 unload가 아니라 파일 삭제/`Disabled` 키로 끝내야 한다.** 상세는 `telegram-mcp-connection-issues.md`의 "재발 사건" 절 참조.

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

**당시의 올바른 방법:** `claude -p "ping" --output-format json --bare`

> ⚠️ **지금은 이 ping 방식 자체를 안 쓴다(2026-07-23 폐지).** 토큰 유지는 "근본 해결 3"의 키체인 직접 로그인 + 매일 재시작이 담당한다.

---

### ❌ 실패 5 — keepalive에서 `--bare` 빠뜨림 (2026-06-17 발견)

4시간마다 Claude에 ping을 보내 토큰을 유지하는 건 맞는 방향이었으나, `--bare` 플래그를 빠뜨렸음.

**결과:**
- ping 실행 시 텔레그램 플러그인도 같이 로드됨
- 새 bun이 뜨면서 기존 bun과 봇 토큰 충돌 → 기존 bun 사망
- 4시간마다 반복됨

**수정:** `~/claude-auth-keepalive.sh`에 `--bare` 추가 → 이후 bun이 37시간+ 연속 생존.

> ⚠️ **이 keepalive는 2026-07-23에 없앴다.** 위 내용은 과거 이력. "근본 해결 3" 참조.
> 다만 **교훈은 지금도 유효**하다: claude를 따로 실행하는 자동화가 텔레그램 플러그인을 같이 띄우면, 같은 봇 토큰으로 수신기가 하나 더 떠서 **기존 봇을 죽인다.**
>
> ※ **2026-08-03 정정:** 위 원칙 자체는 유효하나, "2026-07-28 cokacdir 사건이 정확히 같은 구조였다"는 부분은 **확인되지 않았다.** 그날 검증된 것은 cokacdir의 bun 때문에 감시가 "살아있음"으로 **오판**한 것까지이고, cokacdir가 409로 운영봇을 죽였다는 근거는 없다. 재조사 결과는 `telegram-mcp-connection-issues.md`의 "조치 6" 참조.
>
> 📱 **2026-08-03 실측 — 그럼 이 맥에서 클로드코드를 어떻게 쓰나:**
> **클로드 데스크탑 앱의 코드 세션은 안전하다**(앱이 자체 내장본을 써서 터미널 쪽 플러그인 설정을 따르지 않음).
> 터미널에서 굳이 쓸 때는 `claude --strict-mcp-config --mcp-config '{"mcpServers":{}}'`.
> 그냥 `claude`는 수신기가 떠서 충돌하고, `--bare`는 키체인 인증을 건너뛰어 로그인이 안 된다.
> 빠른 점검: `pgrep -f "bun server.ts"` — 1개면 정상, 2개 이상이면 충돌.
> 상세는 `telegram-mcp-connection-issues.md`의 **"조치 8"**.
>
> ✅ **2026-08-03 종결:** 그날 하루 종일 이어진 409는 **맥 외부의 경쟁 폴러**가 원인이었다.
> 봇을 완전히 정지시킨 상태의 실제 롱폴링 실험(3/3 409)과 후보 4개 개별 정지 실험(전부 무혐의)으로 확정했고,
> **봇 토큰 재발급으로 해결**됐다(교체 후 409 0건). 진단 절차와 시행착오는
> `telegram-mcp-connection-issues.md`의 **"조치 7"** 참조. 재발 시 그 프로토콜을 따를 것.

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

### ✅ 근본 해결 3 — keepalive 폐지, "로그인 방식 수정 + 매일 재시작"으로 교체 (2026-07-22~23)

**이전 방식의 문제 — 반복 로그아웃**

예전엔 Claude 로그인 정보(갱신용 토큰)를 키체인에서 꺼내 환경변수로 넣어주고 실행했다. 그런데 Claude가 보안상 토큰을 주기적으로 새것으로 바꾸는데(회전), **주입된 건 옛날 토큰 그대로**라 유효기간이 끝나면 갱신에 실패했다. 이게 반복 로그아웃의 원인이었다.

비유하자면, 자동문 출입증을 복사해서 들고 다녔는데 원본 출입증이 갱신될 때마다 복사본은 그대로라 결국 문이 안 열리는 상황이다.

**바꾼 것 (3가지)**

| # | 무엇을 | 어떻게 |
|---|---|---|
| 1 | 로그인 방식 (2026-07-22) | 환경변수 주입을 **없앴다**. Claude가 macOS 키체인을 직접 읽고, 토큰이 바뀌면 키체인에 직접 되쓰게 했다. → 복사본 없이 원본만 쓰는 방식. `~/run-ccc.sh` |
| 2 | 매일 재시작 신설 (2026-07-22) | `com.claude.ccc-daily-restart` → 매일 **새벽 4시**에 ccc를 통째로 재시작(`~/ccc-daily-restart.sh`). 재시작 시 로그인도 새로 이뤄진다 |
| 3 | keepalive 폐지 (2026-07-23) | 위 두 가지가 역할을 대신하므로 4시간 ping을 껐다. plist를 `com.claude.auth-refresh.plist.disabled-20260723`으로 개명해 격리 |

**그래서 지금 정상 상태는:**
- `tmux ls`에 **`ccc` 세션 하나만** 보이는 게 정상이다. `claude-keepalive`는 없어야 한다.
- `/tmp/claude-keepalive.log` 파일도 없는 게 정상이다.
- 대신 `/tmp/ccc-startup.log`에 매일 04:00 재시작 기록이 쌓인다. (2026-07-27·28 정상 확인)

**한 가지 주의 — 재시작이 "됐는지 확인"하는 로직을 건드리지 말 것**

처음엔 그냥 `/exit`만 보내고 끝냈는데, **하루걸러 실패**했다(7/17·19·21 성공 / 7/16·18·20·22 무반응). 입력창에 글자가 남아 있거나 작업 중이면 Enter가 안 먹힌 것으로 보인다. 그래서 지금은 ① 보내고 → ② 진짜 재시작됐는지 확인 → ③ 안 됐으면 다시 시도 → ④ 그래도 안 되면 프로세스를 종료해 자동 재기동 루프에 맡기는 4단계로 되어 있다.

> ℹ️ **추정 표시:** "로그인 방식을 바꿨기 때문에 keepalive를 껐다"는 인과관계는 어느 문서에도 명시돼 있지 않다. 세 조치의 날짜가 7/22~23으로 붙어 있고 역할이 겹친다는 점에서 그렇게 판단한 것이다. 파일·주석으로 확인되는 사실은 "무엇을 바꿨나" 표까지다.

---

## 4. 지금 상태 (2026-07-28 기준)

| 구성 요소 | 상태 | 확인 방법 |
|---|---|---|
| CCC봇 (bun) | 실행 중 | `pgrep -fl "bun server.ts"` |
| Claude(ccc) | tmux:ccc 세션에서 실행 중 | `tmux attach -t ccc` |
| ~~keepalive~~ | **폐지됨 (2026-07-23)** — 없는 게 정상 | `tmux ls`에 `ccc`만 보이면 정상 |
| 일일 재시작 | launchd 등록됨 (매일 04:00) | `launchctl list \| grep ccc-daily-restart` |
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
| ccc tmux 세션 | `com.claude.ccc-session` launchd가 자동 시작 (`~/ccc-startup.sh`) |
| ~~claude-keepalive tmux 세션~~ | **해당 없음.** 2026-07-23 폐지 — 재부팅 후에도 생기지 않는 게 정상 |
| 일일 재시작 | `com.claude.ccc-daily-restart` launchd가 자동 등록 (매일 04:00) |
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
# 1. tmux 세션 확인 — ccc 하나만 있으면 정상 (keepalive는 2026-07-23 폐지)
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
| `com.claude.telegram-reconnect` 재생성·재활성화 | 실패 스크립트, 오히려 bun 반복 사망 (2026-07-15 재발) |
| 폐기 launchd job을 `unload`만 하고 plist 방치 | 재부팅 자동로드로 부활 → 파일 삭제 또는 `Disabled` 키 필수 |
| tmux 슬래시 명령을 `send-keys -l` 없이 전송 | 입력 뭉개져 슬래시 명령 미인식 |
| ~~keepalive 스크립트에서 `--bare` 제거~~ | **무효** — keepalive 자체가 2026-07-23 폐지됨 |
| `com.claude.auth-refresh` 다시 켜기 (`.disabled-20260723` 이름 되돌리기) | 폐지된 keepalive job. 되살리면 4시간마다 별도 Claude 세션이 떠서 봇 충돌 위험 재발 |
| `~/run-ccc.sh`에 로그인 토큰을 환경변수로 다시 주입 | 반복 로그아웃의 원인이었음 (2026-07-22 제거) |
| `~/ccc-daily-restart.sh`의 재시작 확인 로직을 단순화 | 단순 `/exit` 전송만 하면 하루걸러 실패함 (7/16~22 기록) |
| **claude를 따로 실행하는 자동화에서 텔레그램 플러그인을 함께 로드** | 같은 봇 토큰으로 수신기가 하나 더 떠서 기존 봇을 죽이고 메시지까지 가로챔. ※ 2026-06-17 keepalive 사례로 확인된 위험. "2026-07-28 cokacdir 사건"을 근거로 들던 서술은 2026-08-03 재조사에서 미검증으로 판명돼 철회함(금지 자체는 유지) |
| **`bash ~/fix-python-tcc.sh` 를 전경(foreground)에서 실행** | macOS 권한 팝업을 기다리며 무한 정지 → 세션 전체가 멈춤 (2026-08-03, 2시간 50분 정지 + 보고 누락). 백그라운드 + 타임아웃으로만 실행 |

---

## 7. 주요 파일·스크립트 위치

| 역할 | 경로 |
|---|---|
| CCC봇 자동 복구 스크립트 | `scripts/telegram_ops_collector.py` |
| 캡처봇 스크립트 | `scripts/telegram_collector.py` |
| ccc 실행 래퍼 (키체인 직접 로그인) | `~/run-ccc.sh` |
| ccc 부팅 기동 스크립트 | `~/ccc-startup.sh` |
| 매일 04:00 재시작 스크립트 | `~/ccc-daily-restart.sh` |
| ccc 기동·재시작 로그 | `/tmp/ccc-startup.log` |
| ~~Claude 토큰 유지 스크립트~~ | ~~`~/claude-auth-keepalive.sh`~~ — **폐지(2026-07-23)**. 파일은 남아 있으나 실행되지 않음 |
| OPS 감시자 로그 | `/tmp/telegram-ops-collector.log` |
| ~~keepalive 로그~~ | ~~`/tmp/claude-keepalive.log`~~ — **없는 게 정상** |
| 메모리 볼트 AI 작업 로그 | `memory-state/launchd-ai-jobs.log` |
| 메모리 볼트 일반 작업 로그 | `memory-state/launchd-jobs.log` |
| 메시지 백업 큐 | `scripts/.telegram-ops-queue.jsonl` |

---

## 8. 빠른 체크리스트 (문제가 생겼을 때 순서대로)

1. `tmux ls` → **`ccc` 세션 있나?** (`claude-keepalive`는 2026-07-23 폐지 — 없는 게 정상)
2. `pgrep -fl "bun server.ts"` → CCC봇 살아있나?
3. 없으면 → `tmux attach -t ccc` → `/reload-plugins`
4. 그래도 안 되면 → 세션 안에서 `Ctrl+C` → `claude` 다시 실행
5. 재부팅 후라면 → `tmux new-session -s ccc` → `claude` 실행
