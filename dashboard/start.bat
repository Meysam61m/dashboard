@echo off
chcp 65001 >nul
title داشبورد مدیریتی مجتمع خراسان
echo ============================================
echo   داشبورد مدیریتی مجتمع خراسان
echo ============================================
echo.

REM پروکسی سیستم می‌تواند اتصال به Ollama روی localhost را قطع کند
set HTTP_PROXY=
set HTTPS_PROXY=
set ALL_PROXY=
set http_proxy=
set https_proxy=
set all_proxy=

echo بررسی Ollama...
curl -s --max-time 4 http://127.0.0.1:11434/api/tags >nul 2>&1
if errorlevel 1 (
  echo [هشدار] Ollama پاسخ نمی‌دهد.
  echo          داشبورد کار می‌کند ولی تحلیل هوشمند غیرفعال است.
  echo          برای عیب‌یابی اجرا کنید:  python diagnose_ollama.py
) else (
  echo [OK] Ollama در دسترس است.
)
echo.
echo اجرا روی http://127.0.0.1:8000
echo برای توقف: Ctrl+C
echo.
start "" http://127.0.0.1:8000
python run.py
pause
