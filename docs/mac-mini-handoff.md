# 맥미니 이전 핸드오프 — Claude Desktop 작업 지시서

이 문서는 맥미니의 Claude Desktop이 읽고 실행하기 위한 작업 지시서입니다.

**사용 방법:**
맥미니의 Claude Desktop을 열고 아래와 같이 입력하세요:
```
docs/mac-mini-handoff.md 파일을 읽고, 이 문서에 나온 순서대로 맥미니 설정을 완료해줘.
```

---

## 현재 상황

- **프로젝트**: Life Memory Vault — Telegram으로 기억을 던지면 Obsidian vault에 구조화 저장되는 개인 기억 시스템
- **맥북 작업**: 완료. GitHub에 업로드됨
- **GitHub 주소**: `https://github.com/iamsangmin/life-memory-vault`
- **맥북 수집기 상태**: 이미 종료됨 (맥미니와 동시 실행 방지)

---

## 맥미니 경로 정보

| 항목 | 경로 |
|---|---|
| 프로젝트 폴더 | `/Users/mini-song/Documents/AI-PlayGround/life-memory-vault` |
| Obsidian Vault | `/Users/mini-song/Library/CloudStorage/GoogleDrive-iamsangmin@gmail.com/내 드라이브/[ Cloud Notes ]/Obsidian Vault/my-memory-vault` |
| Telegram 봇 토큰 위치 | 프로젝트 폴더의 `.env` 파일 |

---

## Claude Desktop이 순서대로 실행할 작업

### STEP 0: 사전 확인 (자동으로 확인할 것)

아래 항목들이 준비되어 있는지 확인합니다. 없는 것이 있으면 사용자에게 알려주세요.

1. **Git 설치 확인**: `git --version`
2. **Python 3 설치 확인**: `python3 --version`
3. **Google Drive 동기화 확인**: Obsidian vault 경로가 실제로 존재하는지 확인
   ```bash
   ls "/Users/mini-song/Library/CloudStorage/GoogleDrive-iamsangmin@gmail.com/내 드라이브/[ Cloud Notes ]/Obsidian Vault/my-memory-vault"
   ```
   - 폴더가 있으면 계속 진행
   - 없으면 Google Drive 앱이 실행 중인지 확인하고, 동기화가 완료될 때까지 대기

---

### STEP 1: 프로젝트 다운로드

아래 경로에 프로젝트를 클론합니다.

```bash
# 프로젝트를 저장할 폴더가 있는지 확인
ls /Users/mini-song/Documents/AI-PlayGround/ 2>/dev/null || mkdir -p /Users/mini-song/Documents/AI-PlayGround/

# GitHub에서 프로젝트 다운로드
git clone https://github.com/iamsangmin/life-memory-vault.git \
  /Users/mini-song/Documents/AI-PlayGround/life-memory-vault

# 다운로드 확인
ls /Users/mini-song/Documents/AI-PlayGround/life-memory-vault/
```

다운로드 후 `README.md`, `scripts/`, `docs/` 폴더가 보이면 성공입니다.

---

### STEP 2: 초기 설정 (setup.sh 실행)

```bash
cd /Users/mini-song/Documents/AI-PlayGround/life-memory-vault
bash scripts/setup.sh
```

이 스크립트가 자동으로 처리하는 것:
- `memory-state/` 폴더 생성
- `memory-config.json` 파일 생성 (example에서 복사)
- `.env` 파일 생성 (example에서 복사)
- 필요한 도구 점검

---

### STEP 3: memory-config.json 설정

`setup.sh` 실행 후 `memory-config.json`의 vault 경로를 맥미니에 맞게 수정합니다.

**현재 상태**: example에서 복사되어서 아래처럼 되어 있음
```json
"vaultPath": "/path/to/your/memory/vault"
```

**바꿔야 할 값**:
```json
"vaultPath": "/Users/mini-song/Library/CloudStorage/GoogleDrive-iamsangmin@gmail.com/내 드라이브/[ Cloud Notes ]/Obsidian Vault/my-memory-vault"
```

파일 전체 경로: `/Users/mini-song/Documents/AI-PlayGround/life-memory-vault/memory-config.json`

수정 후 반드시 확인:
```bash
python3 -B /Users/mini-song/Documents/AI-PlayGround/life-memory-vault/scripts/mem.py digest
```
오류 없이 통계가 나오면 vault 경로가 올바르게 설정된 것입니다.

---

### STEP 4: .env 파일 확인 (Telegram 봇 토큰)

`.env` 파일에 실제 봇 토큰이 입력되어 있어야 합니다.

파일 위치: `/Users/mini-song/Documents/AI-PlayGround/life-memory-vault/.env`

현재 상태 확인:
```bash
cat /Users/mini-song/Documents/AI-PlayGround/life-memory-vault/.env
```

만약 `여기에_봇_토큰_입력` 이라고 나오면, 사용자에게 봇 토큰을 알려달라고 요청하세요.
(봇 토큰은 보안 정보이므로 파일에 직접 입력하면 됩니다)

올바른 형태:
```
TELEGRAM_BOT_TOKEN=8960131930:AAE6KBBY...
```

---

### STEP 5: 수집기 즉시 실행 테스트

서비스 설치 전에 수집기가 정상 작동하는지 확인합니다.

```bash
cd /Users/mini-song/Documents/AI-PlayGround/life-memory-vault

# 한 번만 실행해서 Telegram에서 받아보기
python3 -B scripts/telegram_collector.py --once
```

이 명령을 실행하면 Telegram 봇에게 메시지가 올 때 한 번 처리하고 종료합니다.
Telegram에서 아무 텍스트를 보내고 `✓ 저장 완료` 응답이 오면 성공입니다.

---

### STEP 6: 맥미니 서비스 영구 설치

테스트가 성공했으면 24/7 서비스로 등록합니다.

```bash
cd /Users/mini-song/Documents/AI-PlayGround/life-memory-vault
bash scripts/install-mac-mini.sh
```

이 스크립트가 설치하는 것:
1. **수집기 서비스**: 맥미니 켤 때 자동 시작 + 오류 시 자동 재시작
2. **정리 스케줄러**: 2시간마다 미처리 메모 자동 정리

---

### STEP 7: 최종 검증

모든 설치가 완료되면 아래를 확인합니다.

```bash
# 1. 서비스 실행 상태 확인
launchctl list | grep life-memory
# → com.sangmin.life-memory-collector 줄이 있으면 수집기 서비스 실행 중
# → com.sangmin.life-memory-lint 줄이 있으면 스케줄러 실행 중

# 2. 수집기 로그 확인 (처음 몇 줄)
head -20 /Users/mini-song/Documents/AI-PlayGround/life-memory-vault/memory-state/collector-service.log

# 3. 기본 동작 테스트
python3 -B /Users/mini-song/Documents/AI-PlayGround/life-memory-vault/scripts/mem.py \
  save "맥미니 설치 완료 테스트" --source manual

python3 -B /Users/mini-song/Documents/AI-PlayGround/life-memory-vault/scripts/mem.py \
  seek "테스트"
# → 방금 저장한 기록이 나오면 성공

# 4. digest로 전체 현황 확인
python3 -B /Users/mini-song/Documents/AI-PlayGround/life-memory-vault/scripts/mem.py digest
```

---

### STEP 8: Telegram 최종 테스트

폰에서 Telegram 봇에게 메시지를 보내세요:
```
맥미니 연결 테스트입니다 🎉
```

`✓ 저장 완료` 응답이 오면 모든 설치가 완료된 것입니다.

---

## 문제가 생겼을 때

상세한 설치 가이드: `docs/mac-mini-setup.md` 파일을 참고하세요.

수집기 로그 확인:
```bash
tail -50 /Users/mini-song/Documents/AI-PlayGround/life-memory-vault/memory-state/collector-service.log
```

서비스 재시작:
```bash
launchctl unload ~/Library/LaunchAgents/com.sangmin.life-memory-collector.plist
launchctl load ~/Library/LaunchAgents/com.sangmin.life-memory-collector.plist
```

---

## 완료 체크리스트

- [ ] STEP 0: Google Drive 동기화 확인됨
- [ ] STEP 1: 프로젝트 다운로드 완료
- [ ] STEP 2: setup.sh 실행 완료
- [ ] STEP 3: memory-config.json vault 경로 설정 완료
- [ ] STEP 4: .env 봇 토큰 확인됨
- [ ] STEP 5: 수집기 테스트 성공 (Telegram ack 수신)
- [ ] STEP 6: 서비스 영구 설치 완료
- [ ] STEP 7: 모든 검증 통과
- [ ] STEP 8: Telegram 최종 테스트 성공 🎉
