@echo off
REM ============================================================================
REM PINEAL-EPİFİZ — GÖLGE DENETİMİ (Windows çalıştırıcısı)
REM ============================================================================

echo == Pineal-Epifizi Gölge Denetimi (Windows) ==
echo.

REM Sanal ortamı etkinleştir
if not exist ".venv\Scripts\python.exe" (
    echo HATA: .venv\Scripts\python.exe bulunamadi.
    echo once sanal ortamı oluşturun:
    echo   python -m venv .venv
    echo   .venv\Scripts\pip install pydantic httpx ruff python-dotenv
    pause
    exit /b 1
)

echo [1/1] Denetim calistiriliyor...
".venv\Scripts\python.exe" scripts\golge_denetimi.py

if %errorlevel% neq 0 (
    echo Denetim betigi hata kodu %errorlevel% ile dondi.
    exit /b %errorlevel%
)

echo.
echo Rapolar yazildi:
echo   JSON: reports\golge_denetimi.json
echo   MD:   docs\reports\GOLGE_DENETIMI.md
echo.
echo NOT: Bu rapor BU makinede olculuyor. Windows'ta kurulu paketler
echo (instagrapi, maigret, holehe, socid_extractor, scrapling, trafilatura,
echo reportlab, Pillow) zaten kullanilabilir olabilir.
echo.
echo Tamam.
pause
