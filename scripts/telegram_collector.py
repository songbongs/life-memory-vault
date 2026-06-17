#!/usr/bin/env python3
"""Telegram collector for the Life Memory Vault.

Telegram bot -> this collector -> scripts/mem.py save -> 00_Inbox/Raw

The collector uses only Python's standard library so the MacBook MVP can run
without installing python-telegram-bot. Store the bot token in
TELEGRAM_BOT_TOKEN or memory-config.json. Prefer the environment variable.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "memory-config.json"
MEM = ROOT / "scripts" / "mem.py"
JOBS = ROOT / "scripts" / "jobs.py"

# 텔레그램이 긴 텍스트를 자동 분할할 때 조각들을 합치는 대기 시간(초)
# 자동 분할은 ~0.1초 이내, 사람이 직접 보내는 연속 메시지는 보통 2초 이상 걸림
MERGE_WINDOW = 5.0


TELEGRAM_COMMANDS = {
    # English (original) + Korean aliases. Values are job types (unchanged).
    # parse_telegram_command lowercases the command; Korean is unaffected by .lower().
    "lint": "lint", "정리": "lint",
    "doctor": "doctor", "점검": "doctor",
    "repair": "repair", "수리": "repair",
    "seek": "seek", "검색": "seek", "찾기": "seek",
    "digest": "digest", "통계": "digest", "다이제스트": "digest",
    "status": "status", "상태": "status",
    "enrich": "enrich", "웹요약": "enrich",
    "help": "help", "도움": "help", "도움말": "help",
}

# /help reply (immediate). Plain text for Telegram (no markdown). Covers the
# two-bot topology and per-command timing so the user never has to memorize.
HELP_TEXT = (
    "📝 Life Memory 사용 안내\n"
    "\n"
    "[이 봇 = 캡처 봇] 메모·URL·파일을 보내면 그대로 저장합니다.\n"
    "\n"
    "⌨️ 명령 (한국어·영어 모두 가능)\n"
    "• 즉시 처리:  /검색(/seek) <검색어>,  /상태(/status),  /도움(/help)\n"
    "• 약 5분 내:  /통계(/digest),  /점검(/doctor)\n"
    "• 매일 23시 배치:  /정리(/lint),  /수리(/repair),  /웹요약(/enrich)\n"
    "\n"
    "💬 지금 바로, 자연어로 정리·검색하려면\n"
    "   운영 봇(@songbongs_CCC_bot)에 말하세요.\n"
    '   예: "안 정리된 메모 정리해줘", "어제 메모한 식당 찾아줘"\n'
    "\n"
    "ℹ️ 그냥 메시지를 보내면 메모로 저장됩니다."
)


def load_dotenv(path: Path = ROOT / ".env") -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def token_from(config: dict[str, Any]) -> str:
    return os.environ.get("TELEGRAM_BOT_TOKEN") or config.get("telegram", {}).get("botToken", "")


def api_json(token: str, method: str, params: dict[str, Any] | None = None, timeout: int = 90) -> dict[str, Any]:
    query = urllib.parse.urlencode(params or {})
    url = f"https://api.telegram.org/bot{token}/{method}"
    if query:
        url = f"{url}?{query}"
    with urllib.request.urlopen(url, timeout=timeout) as response:
        data = json.loads(response.read().decode("utf-8"))
    if not data.get("ok"):
        raise RuntimeError(f"Telegram API error for {method}: {data}")
    return data


def send_message(token: str, chat_id: int, text: str, reply_to_message_id: int | None = None) -> None:
    params: dict[str, Any] = {"chat_id": chat_id, "text": text}
    if reply_to_message_id:
        params["reply_to_message_id"] = reply_to_message_id
        params["allow_sending_without_reply"] = True
    api_json(token, "sendMessage", params, timeout=10)


def download_file(token: str, file_id: str, dest: Path) -> Path:
    info = api_json(token, "getFile", {"file_id": file_id})["result"]
    file_path = info["file_path"]
    url = f"https://api.telegram.org/file/bot{token}/{file_path}"
    suffix = Path(file_path).suffix
    final = dest.with_suffix(suffix) if suffix and not dest.suffix else dest
    with urllib.request.urlopen(url, timeout=180) as response:
        final.write_bytes(response.read())
    return final


def read_state(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        return int(json.loads(path.read_text(encoding="utf-8")).get("offset", 0))
    except Exception:
        return 0


def write_state(path: Path, offset: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"offset": offset}, indent=2), encoding="utf-8")


def message_text(message: dict[str, Any]) -> str:
    parts = []
    if message.get("text"):
        parts.append(message["text"])
    if message.get("caption"):
        parts.append(message["caption"])
    if message.get("location"):
        loc = message["location"]
        parts.append(f"Location: {loc.get('latitude')}, {loc.get('longitude')}")
    if not parts:
        parts.append("[Telegram non-text message]")
    return "\n\n".join(parts).strip()


def pick_file(message: dict[str, Any]) -> tuple[str, str, int] | None:
    if message.get("document"):
        doc = message["document"]
        return doc["file_id"], doc.get("file_name", "telegram-document"), int(doc.get("file_size", 0))
    if message.get("photo"):
        photo = sorted(message["photo"], key=lambda p: p.get("file_size", 0))[-1]
        return photo["file_id"], "telegram-photo.jpg", int(photo.get("file_size", 0))
    for key, name in [
        ("voice", "telegram-voice.ogg"),
        ("audio", "telegram-audio"),
        ("video", "telegram-video.mp4"),
        ("video_note", "telegram-video-note.mp4"),
        ("animation", "telegram-animation.mp4"),
    ]:
        if message.get(key):
            item = message[key]
            return item["file_id"], item.get("file_name", name), int(item.get("file_size", 0))
    return None


def run_mem_save(config_path: Path, text: str, file_path: Path | None = None) -> dict[str, Any]:
    cmd = [sys.executable, str(MEM), "--config", str(config_path), "save", text, "--source", "telegram"]
    if file_path:
        cmd.extend(["--file", str(file_path)])
    result = subprocess.run(cmd, cwd=str(ROOT), text=True, capture_output=True, check=True)
    return json.loads(result.stdout)


def run_seek_immediate(config_path: Path, query: str) -> str:
    """Keyword seek and format result for Telegram reply."""
    try:
        result = subprocess.run(
            [sys.executable, str(MEM), "--config", str(config_path), "seek", query, "--limit", "5"],
            cwd=str(ROOT), text=True, capture_output=True, check=True,
        )
        data = json.loads(result.stdout)
        hits = data.get("hits", [])
        if not hits:
            return f'🔍 "{query}" 검색 결과 없음\nAI 검색은 처리 후 별도 회신됩니다.'
        lines = [f'🔍 "{query}" 검색 결과 (상위 {len(hits)}건)']
        for hit in hits:
            snippet = hit.get("snippet", "")[:120].replace("\n", " ")
            lines.append(f"\n📄 {hit['path']}\n{snippet}...")
        lines.append("\nAI 검색 결과는 별도 회신됩니다.")
        return "\n".join(lines)
    except Exception as exc:
        return f'🔍 검색 오류: {short_error(exc)}'


def run_status_immediate(config_path: Path) -> str:
    """Return vault status summary for Telegram reply."""
    try:
        result = subprocess.run(
            [sys.executable, str(MEM), "--config", str(config_path), "digest"],
            cwd=str(ROOT), text=True, capture_output=True, check=True,
        )
        data = json.loads(result.stdout)
        raw = data.get("raw_notes", 0)
        processed = data.get("processed_markers", 0)
        pending = max(0, raw - processed)
        by_type = data.get("by_type", {})
        type_summary = ", ".join(f"{k} {v}건" for k, v in sorted(by_type.items(), key=lambda x: -x[1])[:5])
        return (
            f"📊 Life Memory 상태\n"
            f"Raw 노트: {raw}건\n"
            f"처리 완료: {processed}건\n"
            f"미처리: {pending}건\n"
            f"주요 분류: {type_summary or '없음'}"
        )
    except Exception as exc:
        return f"상태 조회 오류: {short_error(exc)}"


def get_pending_count(config_path: Path) -> int:
    try:
        result = subprocess.run(
            [sys.executable, str(MEM), "--config", str(config_path), "digest"],
            cwd=str(ROOT), text=True, capture_output=True, check=True,
        )
        data = json.loads(result.stdout)
        return max(0, data.get("raw_notes", 0) - data.get("processed_markers", 0))
    except Exception:
        return 0


def build_save_ack(save_result: dict[str, Any], pending: int) -> str:
    raw_type = save_result.get("raw_type", "")
    type_label = {
        "raw_text": "텍스트", "raw_url": "URL", "raw_youtube": "YouTube",
        "raw_pdf": "PDF", "raw_image": "이미지", "raw_audio": "음성",
        "raw_video": "영상", "raw_file": "파일",
    }.get(raw_type, raw_type)
    sensitivity = save_result.get("sensitivity", "normal")
    privacy = " 🔒" if sensitivity == "private" else ""
    hashtags = save_result.get("hashtags", [])
    tag_str = " ".join(f"#{t}" for t in hashtags) if hashtags else ""
    pending_str = f"\n미처리 누적: {pending}건 — /lint 로 정리 요청" if pending > 0 else ""
    return f"✓ 저장 완료 ({type_label}){privacy}{' ' + tag_str if tag_str else ''}{pending_str}"


def parse_telegram_command(text: str) -> tuple[str, str] | None:
    first_line = text.strip().splitlines()[0] if text.strip() else ""
    if not first_line.startswith("/"):
        return None
    head, _, rest = first_line.partition(" ")
    command = head[1:].split("@", 1)[0].strip().lower()
    job_type = TELEGRAM_COMMANDS.get(command)
    if not job_type:
        return None
    remainder = rest.strip()
    extra_lines = "\n".join(text.strip().splitlines()[1:]).strip()
    if extra_lines:
        remainder = f"{remainder}\n{extra_lines}".strip()
    return job_type, remainder


def run_job_add(
    job_type: str,
    text: str,
    message: dict[str, Any],
    requested_by: str,
    adapter: str = "codex",
) -> dict[str, Any]:
    cmd = [
        sys.executable,
        str(JOBS),
        "add",
        job_type,
        "--text",
        text,
        "--adapter",
        adapter,
        "--source",
        "telegram",
        "--requested-by",
        requested_by,
        "--chat-id",
        str(message.get("chat", {}).get("id", "")),
        "--message-id",
        str(message.get("message_id", "")),
    ]
    if job_type == "seek":
        cmd.extend(["--query", text])
    result = subprocess.run(cmd, cwd=str(ROOT), text=True, capture_output=True, check=True)
    return json.loads(result.stdout)


def user_allowed(config: dict[str, Any], message: dict[str, Any]) -> bool:
    # Sensitive-by-default: an empty allowlist means deny, not allow-all.
    # The first-time user gets their numeric ID back so they can register it.
    allowed = config.get("telegram", {}).get("allowedUserIds", [])
    if not allowed:
        return False
    user_id = message.get("from", {}).get("id")
    return user_id in allowed


def process_update(token: str, config_path: Path, config: dict[str, Any], update: dict[str, Any], dry_run: bool = False) -> dict[str, Any]:
    message = update.get("message") or update.get("edited_message")
    if not message:
        return {"skipped": "not_message"}
    user = message.get("from", {})
    if not user_allowed(config, message):
        if not dry_run:
            chat_id = message.get("chat", {}).get("id")
            if chat_id:
                notice = (
                    "🔒 등록되지 않은 사용자입니다.\n"
                    f"당신의 Telegram ID: {user.get('id')}\n"
                    "memory-config.json의 telegram.allowedUserIds에 이 ID를 추가하세요."
                )
                try:
                    send_message(token, int(chat_id), notice, message.get("message_id"))
                except Exception:
                    pass
        return {"skipped": "unauthorized", "from_id": user.get("id")}

    text = message_text(message)
    requested_by = str(user.get("id", ""))
    command = parse_telegram_command(text)
    if command:
        job_type, command_text = command
        if dry_run:
            return {"dry_run": True, "command": job_type, "text": command_text[:300], "from_id": user.get("id")}

        # /seek: 즉시 keyword 검색 결과를 Telegram으로 회신 (방향 A)
        # job queue에도 동시에 저장해서 AI seek(방향 B)로도 처리 가능하게 함
        if job_type == "seek" and command_text:
            chat_id = message.get("chat", {}).get("id")
            seek_reply = run_seek_immediate(config_path, command_text)
            if chat_id and seek_reply:
                try:
                    send_message(token, int(chat_id), seek_reply, message.get("message_id"))
                except Exception:
                    pass

        # /status: 즉시 digest 결과 회신
        if job_type == "status":
            chat_id = message.get("chat", {}).get("id")
            status_reply = run_status_immediate(config_path)
            if chat_id and status_reply:
                try:
                    send_message(token, int(chat_id), status_reply, message.get("message_id"))
                except Exception:
                    pass
            return {"status": "replied"}

        # /help: 즉시 사용 안내 회신 (잡 큐를 거치지 않음 — help는 잡 타입이 아님)
        if job_type == "help":
            chat_id = message.get("chat", {}).get("id")
            if chat_id:
                try:
                    send_message(token, int(chat_id), HELP_TEXT, message.get("message_id"))
                except Exception:
                    pass
            return {"help": "replied"}

        result = run_job_add(job_type, command_text, message, requested_by)
        telegram_config = config.get("telegram", {})
        if telegram_config.get("sendAck", True):
            chat_id = message.get("chat", {}).get("id")
            job_ack_labels = {
                "lint": "정리 작업 요청 등록",
                "doctor": "볼트 점검 요청 등록",
                "repair": "수리 작업 요청 등록",
                "digest": "요약 요청 등록",
                "seek": "AI 검색 요청 등록 (keyword 결과는 위에 표시)",
                "enrich": "웹 링크 요약 요청 등록 (23시 배치, 한국어)",
            }
            label = job_ack_labels.get(job_type, f"작업 요청 등록: {job_type}")
            ack = f"📋 {label}\nJob ID: {result.get('id')}\nAI 처리 후 결과를 알려드릴게요."
            if chat_id:
                try:
                    send_message(token, int(chat_id), ack, message.get("message_id"))
                    result["ack"] = "sent"
                except Exception as exc:
                    result["ack"] = "failed"
                    result["ack_error"] = short_error(exc)
        return {"job": result}

    file_info = pick_file(message)
    temp_file: Path | None = None
    if file_info and config.get("telegram", {}).get("downloadFiles", True):
        file_id, file_name, size = file_info
        max_bytes = int(config.get("telegram", {}).get("maxDownloadBytes", 20971520))
        if size and size > max_bytes:
            text += f"\n\n[Large Telegram file not downloaded]\nfile_name: {file_name}\nfile_size: {size}"
        else:
            temp_dir = Path(tempfile.mkdtemp(prefix="life-memory-telegram-"))
            try:
                temp_file = download_file(token, file_id, temp_dir / file_name)
            except Exception as exc:
                text += f"\n\n[Telegram file download failed]\nfile_name: {file_name}\nerror: {short_error(exc)}"

    if dry_run:
        return {"dry_run": True, "from_id": user.get("id"), "text": text[:300], "file": str(temp_file) if temp_file else ""}
    result = run_mem_save(config_path, text, temp_file)
    telegram_config = config.get("telegram", {})
    if telegram_config.get("sendAck", True):
        chat_id = message.get("chat", {}).get("id")
        pending = get_pending_count(config_path)
        ack = build_save_ack(result, pending)
        if chat_id and ack:
            try:
                send_message(token, int(chat_id), ack, message.get("message_id"))
                result["ack"] = "sent"
            except Exception as exc:
                result["ack"] = "failed"
                result["ack_error"] = short_error(exc)
    return result


def short_error(exc: BaseException) -> str:
    text = str(exc) or exc.__class__.__name__
    return " ".join(text.split())[:240]


def flush_pending(
    pending: dict[str, Any],
    token: str,
    config_path: Path,
    config: dict[str, Any],
    dry_run: bool = False,
    force: bool = False,
) -> list[dict[str, Any]]:
    """MERGE_WINDOW 초가 지난 버퍼 항목을 병합 저장."""
    now = time.time()
    results = []
    expired = [k for k, v in pending.items() if force or now - v["last_ts"] >= MERGE_WINDOW]
    for key in expired:
        entry = pending.pop(key)
        merged_text = "\n".join(entry["texts"])
        merged_count = len(entry["texts"])
        ref_message = entry["message"]
        if dry_run:
            results.append({"dry_run": True, "merged_parts": merged_count, "text": merged_text[:300]})
            continue
        try:
            result = run_mem_save(config_path, merged_text)
            if merged_count > 1:
                result["merged_parts"] = merged_count
            telegram_config = config.get("telegram", {})
            if telegram_config.get("sendAck", True):
                chat_id = ref_message.get("chat", {}).get("id")
                pending_count = get_pending_count(config_path)
                ack = build_save_ack(result, pending_count)
                if merged_count > 1:
                    ack = f"[{merged_count}개 분할 메시지 → 1개로 병합 저장]\n{ack}"
                if chat_id:
                    try:
                        send_message(token, int(chat_id), ack, ref_message.get("message_id"))
                        result["ack"] = "sent"
                    except Exception as exc:
                        result["ack_error"] = short_error(exc)
            results.append(result)
        except Exception as exc:
            results.append({"error": "flush_failed", "message": short_error(exc)})
    return results


def poll_once(args: argparse.Namespace, config_path: Path, config: dict[str, Any], token: str,
              pending: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    state_path = ROOT / config.get("telegram", {}).get("statePath", "memory-state/telegram-offset.json")
    offset = 0 if args.from_latest else read_state(state_path)
    params = {
        "timeout": int(config.get("telegram", {}).get("pollTimeoutSeconds", 30)),
        "allowed_updates": json.dumps(["message", "edited_message"]),
    }
    if offset:
        params["offset"] = offset
    updates = api_json(token, "getUpdates", params)["result"]
    results = []
    max_update = offset
    for update in updates:
        next_offset = int(update["update_id"]) + 1
        try:
            message = update.get("message") or update.get("edited_message")
            # 순수 텍스트 메시지(명령어·파일 제외)만 버퍼링 — 명령어·파일은 즉시 처리
            if (pending is not None and message and not args.dry_run
                    and message.get("text") and not message["text"].startswith("/")
                    and not pick_file(message)):
                key = (str(message.get("chat", {}).get("id", "")),
                       str(message.get("from", {}).get("id", "")))
                now = time.time()
                if key in pending:
                    pending[key]["texts"].append(message["text"])
                    pending[key]["last_ts"] = now
                else:
                    pending[key] = {
                        "texts": [message["text"]],
                        "last_ts": now,
                        "message": message,
                    }
                max_update = max(max_update, next_offset)
            else:
                results.append(process_update(token, config_path, config, update, args.dry_run))
                max_update = max(max_update, next_offset)
        except Exception as exc:
            results.append({"error": "update_failed", "update_id": update.get("update_id"), "message": short_error(exc)})
            break
    if max_update and not args.dry_run:
        write_state(state_path, max_update)
    return results


def print_me(token: str) -> None:
    me = api_json(token, "getMe")["result"]
    print(json.dumps(me, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect Telegram bot messages into the Life Memory Vault")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--once", action="store_true", help="Poll once and exit")
    parser.add_argument("--loop", action="store_true", help="Keep polling")
    parser.add_argument("--dry-run", action="store_true", help="Read messages but do not write notes")
    parser.add_argument("--from-latest", action="store_true", help="Ignore saved offset for this run")
    parser.add_argument("--me", action="store_true", help="Show bot identity and exit")
    args = parser.parse_args()

    load_dotenv()
    config_path = Path(args.config).expanduser()
    config = load_config(config_path)
    token = token_from(config)
    if not token:
        raise SystemExit("Missing Telegram bot token. Set TELEGRAM_BOT_TOKEN or telegram.botToken in memory-config.json.")

    if args.me:
        print_me(token)
        return

    if not args.once and not args.loop:
        args.once = True

    # 분할 메시지 병합 버퍼: key=(chat_id, user_id), value={texts, last_ts, message}
    pending: dict[str, Any] = {}

    while True:
        try:
            # 만료된 버퍼 항목 먼저 저장
            flushed = flush_pending(pending, token, config_path, config, args.dry_run)
            if flushed:
                print(json.dumps(flushed, ensure_ascii=False, indent=2), flush=True)

            results = poll_once(args, config_path, config, token, pending)
            if results:
                print(json.dumps(results, ensure_ascii=False, indent=2))
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            print(json.dumps({"warning": "telegram_network_retry", "message": short_error(exc)}, ensure_ascii=False), flush=True)
            if args.once:
                raise
            time.sleep(10)
            continue
        if args.once:
            # --once 모드에서도 버퍼에 남은 항목 강제 플러시
            flushed = flush_pending(pending, token, config_path, config, args.dry_run, force=True)
            if flushed:
                print(json.dumps(flushed, ensure_ascii=False, indent=2), flush=True)
            break
        time.sleep(1)


if __name__ == "__main__":
    main()
