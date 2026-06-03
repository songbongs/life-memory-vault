# Local Admin Dashboard

The admin dashboard is a small local web page for the MacBook MVP.

It lets you:

- Turn the Telegram collector on.
- Turn the Telegram collector off.
- See whether it is running.
- Run `mem-lint` manually.
- Read recent collector logs.

## Start

프로젝트 폴더로 이동한 뒤 실행하세요:

```bash
# 맥북이라면:
cd /Users/sangmin/Documents/AI_Playground/my-life-memory

# 맥미니라면:
cd /Users/mini-song/Documents/AI-PlayGround/life-memory-vault

python3 scripts/memory_admin.py
```

Then open:

```text
http://127.0.0.1:8765
```

## Important

If you already started the collector manually with:

```bash
python3 scripts/telegram_collector.py --loop
```

stop it with `Ctrl+C` before using the dashboard. Only one collector should run at a time.

## Token

The dashboard starts the collector using `TELEGRAM_BOT_TOKEN` from either:

1. the current terminal environment, or
2. a local `.env` file in this project.

Example `.env`:

```text
TELEGRAM_BOT_TOKEN=PASTE_TOKEN_HERE
```

Never commit `.env`.
