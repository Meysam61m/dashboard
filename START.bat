@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
title سیستم ثبت و چاپ سند کارپردازی
cd /d "%~dp0"

echo ================================================================
echo    سیستم ثبت و چاپ سند کارپردازی  -  راه‌اندازی خودکار
echo    (نیازی به تایپ هیچ دستوری نیست)
echo ================================================================
echo.

REM ---------------- [1/4] پیدا کردن یا نصب Python ----------------
set "PY="
py -3 -c "import sys" >nul 2>&1 && set "PY=py -3"
if not defined PY (
    python -c "import sys" >nul 2>&1 && set "PY=python"
)
if not defined PY (
    for %%V in (313 312 311 310) do (
        if not defined PY (
            if exist "%LocalAppData%\Programs\Python\Python%%V\python.exe" (
                set "PY=%LocalAppData%\Programs\Python\Python%%V\python.exe"
            )
        )
    )
)

if not defined PY (
    echo [1/4] پایتون روی سیستم یافت نشد - در حال نصب خودکار Python ...
    winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
    if errorlevel 1 goto :no_python
    for %%V in (313 312 311 310) do (
        if not defined PY (
            if exist "%LocalAppData%\Programs\Python\Python%%V\python.exe" (
                set "PY=%LocalAppData%\Programs\Python\Python%%V\python.exe"
            )
        )
    )
    if not defined PY set "PY=python"
)
echo [1/4] Python آماده است: %PY%
echo.

REM ---------------- [2/4] ساخت محیط مجازی ----------------
if exist ".venv\Scripts\python.exe" goto :venv_ok
echo [2/4] در حال ساخت محیط مجازی ...
if exist ".venv" rmdir /s /q ".venv"
%PY% -m venv .venv
if not exist ".venv\Scripts\python.exe" goto :venv_fail
:venv_ok
echo [2/4] محیط مجازی آماده است.
echo.

REM ---------------- [3/4] نصب پیش‌نیازها ----------------
echo [3/4] در حال نصب/به‌روزرسانی پیش‌نیازها (فقط بار اول کمی طول می‌کشد) ...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q --upgrade pip
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt
if errorlevel 1 goto :pip_fail
echo [3/4] پیش‌نیازها نصب شدند.
echo.

REM ---------------- [4/4] اجرای برنامه ----------------
echo [4/4] در حال اجرای برنامه ...
echo.
echo    برنامه اجرا می‌شود و مرورگر به‌صورت خودکار باز خواهد شد.
echo    برای استفاده دیگران از شبکه داخلی:
echo          http://IP-این-کامپیوتر:8501
echo.
echo    برای بستن برنامه، این پنجره را ببندید یا Ctrl+C بزنید.
echo ================================================================
echo.
".venv\Scripts\python.exe" -m streamlit run app.py --server.address 0.0.0.0 --server.port 8501 --server.headless false --browser.gatherUsageStats false
echo.
echo برنامه بسته شد.
pause
exit /b 0

:no_python
echo.
echo ================================================================
echo   نصب خودکار Python ممکن نشد.
echo   لطفا Python را از لینک زیر نصب کنید (روی دکمه Download بزنید)
echo   و در صفحه نصب، حتما تیک  "Add python.exe to PATH"  را بزنید:
echo.
echo            https://www.python.org/downloads/
echo.
echo   سپس دوباره همین فایل (START.bat) را دوبار کلیک کنید.
echo ================================================================
pause
exit /b 1

:venv_fail
echo.
echo   ساخت محیط مجازی ناموفق بود. اگر مشکل ادامه داشت فایل START.bat
echo   را با Run as administrator اجرا کنید.
pause
exit /b 1

:pip_fail
echo.
echo ================================================================
echo   نصب پیش‌نیازها ناموفق بود.
echo   معمولا دلیل آن عدم اتصال به اینترنت است؛ اتصال را بررسی کنید
echo   و دوباره START.bat را اجرا کنید.
echo ================================================================
pause
exit /b 1
