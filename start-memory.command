#!/bin/bash
# Life Memory 시작 스크립트
# 바탕화면에 놓고 더블클릭하면 Admin 서버가 켜지고 브라우저가 열립니다.

ROOT="$(cd "$(dirname "$0")" && pwd)"
PORT=8765

echo "=============================="
echo "  Life Memory 시작 중..."
echo "=============================="

# 이미 실행 중인지 확인
if lsof -i :$PORT | grep LISTEN > /dev/null 2>&1; then
    echo "✅ Admin 서버 이미 실행 중 (포트 $PORT)"
else
    echo "🚀 Admin 서버 시작 중..."
    python3 "$ROOT/scripts/memory_admin.py" > "$ROOT/memory-state/admin-server.log" 2>&1 &
    sleep 2

    if lsof -i :$PORT | grep LISTEN > /dev/null 2>&1; then
        echo "✅ Admin 서버 시작됨"
    else
        echo "❌ 시작 실패 - 로그 확인: $ROOT/memory-state/admin-server.log"
        read -p "엔터를 누르면 창이 닫힙니다..."
        exit 1
    fi
fi

# 브라우저 열기
echo "🌐 브라우저 열는 중..."
open "http://127.0.0.1:$PORT"

echo ""
echo "Admin 서버: http://127.0.0.1:$PORT"
echo "종료하려면: 대시보드에서 수집기 끄기 후 이 창을 닫아주세요."
echo ""
echo "이 창을 닫아도 서버는 계속 실행됩니다."
echo "(완전히 끄려면: 터미널에서 'kill \$(lsof -ti :$PORT)')"
echo ""
read -p "엔터를 누르면 이 창이 닫힙니다..."
