#!/usr/bin/env bash
set -euo pipefail

echo "This installs optional local-first memory tools."
echo "Review before running on a new Mac mini."

if command -v brew >/dev/null 2>&1; then
  brew install ffmpeg poppler tesseract yt-dlp
else
  echo "Homebrew not found; skipping brew tools." >&2
fi

python3 -m pip install --upgrade \
  pdfplumber pdftext marker-pdf surya-ocr youtube-transcript-api \
  markitdown python-telegram-bot fastapi uvicorn mcp

echo "Optional Korean/public-document tools to evaluate manually:"
echo "  - OpenDataLoader PDF: https://github.com/opendataloader-project/opendataloader-pdf"
echo "  - kordoc MCP: https://github.com/chrisryugj/kordoc"
echo "  - PaddleOCR MCP may already be installed via uv tool."
