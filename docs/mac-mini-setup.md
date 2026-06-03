# 맥미니 설치 가이드

## 이 가이드는 누구를 위한 것인가요?

맥미니를 24시간 켜두고 Life Memory Vault를 홈서버로 운영하고 싶은 분을 위한 가이드입니다.
터미널을 처음 써보는 분도 따라할 수 있도록 하나하나 설명합니다.

---

## 설치 전 필요한 것들

맥미니에서 설치를 시작하기 전에 아래 항목들을 먼저 준비하세요.

### 필수 확인 항목

| 항목 | 확인 방법 |
|---|---|
| Google Drive for Desktop | 상단 메뉴바에 구름 아이콘이 있고, 동기화가 완료된 상태 |
| Obsidian 앱 | 앱이 설치되어 있고, vault가 Google Drive에서 열리는 상태 |
| Telegram 봇 토큰 | @BotFather에게 이미 받아 둔 토큰 문자열 |

> **Google Drive가 동기화되지 않으면?**
> 상단 메뉴바의 구름 아이콘을 클릭해서 동기화 상태를 확인하세요.
> "동기화 중" 상태라면 완료될 때까지 기다린 후 진행하세요.

---

## 터미널 여는 방법

> 이미 터미널을 알고 있다면 이 섹션은 넘어가도 됩니다.

1. 키보드에서 `Command(⌘) + Space`를 눌러 Spotlight를 엽니다
2. `terminal`을 입력하고 Enter를 누릅니다
3. 검은 창(터미널)이 열립니다
4. 이제 아래 명령어들을 터미널에 하나씩 복사해서 붙여넣고 Enter를 누르세요

---

## STEP 1: Homebrew 설치 (패키지 관리자)

Homebrew는 맥에서 소프트웨어를 쉽게 설치해주는 도구입니다.
이미 설치되어 있다면 STEP 2로 넘어가세요.

터미널에서 확인:
```bash
brew --version
```

`Homebrew X.X.X` 같은 버전이 보이면 이미 설치된 것입니다.

설치되지 않았다면 아래 명령어를 실행하세요:
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

> 설치 중 맥 비밀번호를 물어볼 수 있습니다. 입력 시 화면에 글자가 보이지 않는 것이 정상입니다.

---

## STEP 2: Python 3 설치 확인

```bash
python3 --version
```

`Python 3.X.X` 같은 버전이 보이면 이미 설치된 것입니다.

없다면:
```bash
brew install python3
```

---

## STEP 3: Git 설치 확인

```bash
git --version
```

`git version X.X.X`가 보이면 이미 설치된 것입니다.

없다면:
```bash
brew install git
```

---

## STEP 4: 프로젝트 폴더 만들기 및 다운로드

프로젝트를 저장할 폴더를 만들고 다운로드합니다.

```bash
# 폴더 만들기
mkdir -p /Users/mini-song/Documents/AI-PlayGround

# GitHub에서 프로젝트 다운로드
git clone https://github.com/songbongs/life-memory-vault.git \
  /Users/mini-song/Documents/AI-PlayGround/life-memory-vault

# 다운로드된 파일 확인
ls /Users/mini-song/Documents/AI-PlayGround/life-memory-vault/
```

`README.md`, `scripts/`, `docs/` 등의 폴더와 파일이 보이면 성공입니다.

---

## STEP 5: 초기 설정 (setup.sh 실행)

```bash
cd /Users/mini-song/Documents/AI-PlayGround/life-memory-vault
bash scripts/setup.sh
```

이 스크립트가 자동으로 해주는 일:
- 필요한 폴더(`memory-state/`) 생성
- 설정 파일(`memory-config.json`) 준비
- 봇 토큰 파일(`.env`) 준비

실행 후 화면에 나오는 안내를 잘 읽어보세요.

---

## STEP 6: Obsidian vault 경로 설정

`memory-config.json` 파일을 열어서 vault 경로를 맥미니에 맞게 수정합니다.

### 파일 찾기

Finder에서 `Command(⌘) + Shift + G`를 누르고 아래 경로를 입력하세요:
```
/Users/mini-song/Documents/AI-PlayGround/life-memory-vault
```

### 수정할 내용

`memory-config.json` 파일을 텍스트 편집기(TextEdit)로 열고 아래 줄을 찾으세요:
```json
"vaultPath": "/path/to/your/memory/vault"
```

이것을 아래처럼 바꾸세요:
```json
"vaultPath": "/Users/mini-song/Library/CloudStorage/GoogleDrive-iamsangmin@gmail.com/내 드라이브/[ Cloud Notes ]/Obsidian Vault/my-memory-vault"
```

> **경로가 맞는지 확인하는 방법:**
> Finder에서 Obsidian vault 폴더를 찾아 선택한 후,
> 하단 상태바에 경로가 표시됩니다.
> 또는 터미널에서: `ls "/Users/mini-song/Library/CloudStorage/GoogleDrive-iamsangmin@gmail.com/내 드라이브/[ Cloud Notes ]/Obsidian Vault/"`
> 명령어 결과에 `my-memory-vault`가 보이면 경로가 맞는 것입니다.

### 저장 후 검증

```bash
python3 -B /Users/mini-song/Documents/AI-PlayGround/life-memory-vault/scripts/mem.py digest
```

오류 없이 숫자가 나오면 경로 설정이 올바른 것입니다.

---

## STEP 7: Telegram 봇 토큰 입력

`.env` 파일을 열어서 봇 토큰을 입력합니다.

터미널에서:
```bash
open /Users/mini-song/Documents/AI-PlayGround/life-memory-vault/.env
```

파일이 텍스트 편집기로 열립니다.
아래 부분을 찾아서 봇 토큰을 입력하세요:

```
TELEGRAM_BOT_TOKEN=여기에_봇_토큰_입력
```

예를 들어 봇 토큰이 `1234567890:ABCdefGHI...` 라면:
```
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHI...
```

저장하고 닫으세요.

---

## STEP 8: 수집기 테스트

서비스 설치 전에 수집기가 제대로 작동하는지 확인합니다.

```bash
cd /Users/mini-song/Documents/AI-PlayGround/life-memory-vault
python3 -B scripts/telegram_collector.py --once
```

실행 후 폰의 Telegram에서 봇에게 아무 메시지를 보내세요.

예시:
```
안녕하세요! 테스트 메시지입니다
```

봇에게서 아래와 비슷한 응답이 오면 성공입니다:
```
✓ 저장 완료 (텍스트) | 미처리 1건 누적
/lint 로 정리 요청
```

응답이 오지 않는다면:
1. `.env` 파일의 봇 토큰이 올바른지 확인하세요
2. Telegram에서 봇을 시작(`/start`)했는지 확인하세요
3. `memory-config.json`의 `allowedUserIds`에 자신의 Telegram ID가 있는지 확인하세요

---

## STEP 9: 24/7 서비스 설치

테스트가 성공했으면 이제 맥미니가 항상 자동으로 수집기를 실행하도록 설치합니다.

```bash
cd /Users/mini-song/Documents/AI-PlayGround/life-memory-vault
bash scripts/install-mac-mini.sh
```

설치 완료 후 확인:
```bash
launchctl list | grep life-memory
```

아래와 비슷한 줄이 2개 보이면 성공입니다:
```
-	0	com.sangmin.life-memory-collector
-	0	com.sangmin.life-memory-lint
```

---

## STEP 10: 최종 확인

맥미니를 **재시작**해서 서비스가 자동으로 켜지는지 확인합니다.

재시작 후:
```bash
# 서비스 실행 중인지 확인
launchctl list | grep life-memory

# 수집기 로그 확인
tail -20 /Users/mini-song/Documents/AI-PlayGround/life-memory-vault/memory-state/collector-service.log
```

로그에 에러 없이 Telegram 연결 시도가 보이면 완료입니다.

---

## 설치 완료!

이제 맥미니에서 Life Memory Vault가 24시간 운영됩니다.

### 이제 할 수 있는 것들

**Telegram에서:**
- 아무 텍스트 전송 → 자동 저장
- 사진, 파일 전송 → 자동 저장
- `/status` → 볼트 현황 즉시 확인
- `/seek 검색어` → 저장된 기억 검색
- `/lint` → AI 정리 요청

**Admin 대시보드 (맥미니 브라우저에서):**
```bash
python3 /Users/mini-song/Documents/AI-PlayGround/life-memory-vault/scripts/memory_admin.py
```
브라우저: `http://127.0.0.1:8765`

---

## 문제 해결 FAQ

### Q: Telegram에서 응답이 안 와요

1. `.env` 파일의 봇 토큰 확인
2. Telegram에서 봇에게 `/start` 전송
3. 수집기 서비스 실행 확인:
   ```bash
   launchctl list | grep life-memory-collector
   ```
4. 로그 확인:
   ```bash
   tail -50 /Users/mini-song/Documents/AI-PlayGround/life-memory-vault/memory-state/collector-service.log
   ```

### Q: "memory-config.json을 찾을 수 없다"는 오류가 나요

`setup.sh`를 먼저 실행했는지 확인하세요:
```bash
bash /Users/mini-song/Documents/AI-PlayGround/life-memory-vault/scripts/setup.sh
```

### Q: vault 경로가 존재하지 않는다는 오류가 나요

1. Google Drive가 실행 중인지 확인 (메뉴바의 구름 아이콘)
2. 동기화가 완료됐는지 확인
3. vault 경로가 올바른지 확인:
   ```bash
   ls "/Users/mini-song/Library/CloudStorage/GoogleDrive-iamsangmin@gmail.com/내 드라이브/[ Cloud Notes ]/Obsidian Vault/"
   ```

### Q: 서비스를 제거하고 싶어요

```bash
bash /Users/mini-song/Documents/AI-PlayGround/life-memory-vault/scripts/install-mac-mini.sh --uninstall
```

### Q: 프로젝트를 최신 버전으로 업데이트하려면?

```bash
cd /Users/mini-song/Documents/AI-PlayGround/life-memory-vault
git pull
```

업데이트 후 서비스 재시작:
```bash
launchctl unload ~/Library/LaunchAgents/com.sangmin.life-memory-collector.plist
launchctl load ~/Library/LaunchAgents/com.sangmin.life-memory-collector.plist
```

### Q: 맥미니가 꺼져 있는 동안 온 Telegram 메시지는 어떻게 되나요?

Telegram은 메시지를 서버에 보관합니다. 맥미니가 다시 켜지면 수집기가 자동으로 시작되고, 그동안 쌓인 메시지를 모두 처리합니다. 메시지가 유실되지 않습니다.
