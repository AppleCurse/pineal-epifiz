@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
echo ==============================================
echo PINEAL-HERETIC v2.0 - COMMAND CENTER INITIATION
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

REM --- 2) OSINT ve Retina paketleri (psutil uyumlulugu icin ayri adim) ---
set PYTHONUTF8=1
if exist requirements-osint.txt (
    echo [2/4] OSINT ve Retina paketleri kuruluyor...
    python -m pip install -q -r requirements-osint.txt -r requirements-retina.txt
    if errorlevel 1 echo UYARI: OSINT/Retina paketleri kurulamadi - panel acilir ama bazi moduller kapali kalir.
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
if not defined ENABLE_CROSS_PLATFORM set ENABLE_CROSS_PLATFORM=true
if not defined ENABLE_MAIGRET set ENABLE_MAIGRET=true
if not defined ENABLE_HOLEHE set ENABLE_HOLEHE=true
if not defined ENABLE_CRAWL4AI set ENABLE_CRAWL4AI=true
if not defined ENABLE_SCRAPLING set ENABLE_SCRAPLING=true
if not defined ENABLE_X_SENSOR set ENABLE_X_SENSOR=true
if not defined ENABLE_IG_SECONDARY set ENABLE_IG_SECONDARY=true
if not defined ENABLE_COMPANY_TARGETING set ENABLE_COMPANY_TARGETING=true
if not defined ENABLE_REPORT_FACTORY set ENABLE_REPORT_FACTORY=true
if not defined ENABLE_MEDIA_FORENSICS set ENABLE_MEDIA_FORENSICS=true
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
