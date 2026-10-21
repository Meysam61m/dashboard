@echo off
chcp 65001 >nul
title داشبورد مدیریتی مجتمع خراسان
echo ============================================
echo   داشبورد مدیریتی مجتمع خراسان
echo ============================================
echo.
echo بررسی Ollama...
curl -s --max-time 3 http://127.0.0.1:11434/api/tags >nul 2>&1
if errorlevel 1 (
  echo [هشدار] Ollama در حال اجرا نیست. داشبورد کار می‌کند ولی تحلیل هوشمند غیرفعال است.
  echo          برای فعال شدن، برنامه Ollama را اجرا کنید.
) else (
  echo [OK] Ollama در دسترس است.
)
echo.
echo در حال اجرای داشبورد روی http://127.0.0.1:8000
echo برای توقف: کلیدهای Ctrl+C
echo.
start "" http://127.0.0.1:8000
python run.py
pause
