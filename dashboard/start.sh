#!/usr/bin/env bash
echo "== داشبورد مدیریتی مجتمع خراسان =="
# پروکسی سیستم می‌تواند اتصال به Ollama روی localhost را قطع کند
unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy
if curl -s --max-time 4 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
  echo "[OK] Ollama در دسترس است."
else
  echo "[هشدار] Ollama پاسخ نمی‌دهد — تحلیل هوشمند غیرفعال."
  echo "        عیب‌یابی: python3 diagnose_ollama.py"
fi
echo "اجرا روی http://127.0.0.1:8000"
exec python3 run.py
