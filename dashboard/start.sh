#!/usr/bin/env bash
echo "== داشبورد مدیریتی مجتمع خراسان =="
if curl -s --max-time 3 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
  echo "[OK] Ollama در دسترس است."
else
  echo "[هشدار] Ollama در حال اجرا نیست — داشبورد کار می‌کند، تحلیل هوشمند غیرفعال."
fi
echo "اجرا روی http://127.0.0.1:8000"
python3 run.py
