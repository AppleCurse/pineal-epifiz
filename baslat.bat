@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
set "PINEAL_VERSION=unknown"
if exist VERSION set /p PINEAL_VERSION=<VERSION
echo ==============================================
echo PINEAL-HERETIC v%PINEAL_VERSION% - COMMAND CENTER INITIATION
echo ==============================================
echo.

REM --- 0) Port kontrolu: ikinci sunucu baslatma ---
curl.exe -fsS http://127.0.0.1:8000/ >nul 2>&1
if not errorlevel 1 (
    echo Sunucu zaten calisiyor: http://localhost:8000
    start "" http://localhost:8000
    goto :done
)

netstat -ano | findstr /R /C:":8000 .*LISTENING" >nul 2>&1
if not errorlevel 1 (
    echo HATA: 8000 portu baska bir uygulama tarafindan kullaniliyor.
    echo Portu bosaltin veya mevcut uygulamayi kapatin.
    goto :fail
)

REM --- 1) Python ortami + temel paketler ---
if not exist venv (
    echo [1/4] venv olusturuluyor...
    python -m venv venv
    if errorlevel 1 goto :fail
)
call venv\Scripts\activate.bat
python -m pip install -q -r requirements.txt
if errorlevel 1 goto :fail

REM --- 2) OSINT paketleri (psutil uyumlulugu icin ayri adim) ---
if exist requirements-osint.txt (
    echo [2/4] OSINT paketleri kuruluyor...
    python -m pip install -q -r requirements-osint.txt
    if errorlevel 1 echo UYARI: OSINT paketleri kurulamadi - panel acilir ama OSINT modulleri kapali kalir.
)

REM --- 3) Playwright tarayici motoru ---
 echo [3/4] Playwright Chromium kontrol ediliyor...
python -m playwright install chromium
if errorlevel 1 goto :fail

REM --- 4) Frontend derlemesi (dist yoksa) ---
if not exist frontend\dist (
    echo [4/4] Frontend derleniyor...
    pushd frontend
    if not exist node_modules call npm ci
    if errorlevel 1 (popd & goto :fail)
    call npm run build
    if errorlevel 1 (popd & goto :fail)
    popd
)

REM --- Sunucu: http://localhost:8000 ---
REM [AUDIT P2-10] PINEAL_ENV artik fail-closed: set edilmemis/bozuk bir deger
REM URETIM sayilir ve PINEAL_TOKEN ister. Yerel baslatici acikca gelistirme der.
if not defined PINEAL_ENV set PINEAL_ENV=development
echo Sunucu baslatiliyor: http://localhost:8000
echo.
python -m uvicorn backend.api:app --host 0.0.0.0 --port 8000
if errorlevel 1 goto :fail

goto :done

:fail
echo.
echo Baslatma basarisiz oldu.
exit /b 1

:done
endlocal
pause
