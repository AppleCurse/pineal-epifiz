@echo off
chcp 65001 >nul
echo ===================================================================
echo [GOOSE-SKILLS] Growth, GTM, Ads, Social ve Scraping Yetenekleri
echo https://github.com/gooseworks-ai/goose-skills
echo ===================================================================

set CLONE_DIR=%APPDATA%\Block\goose\skills\goose-skills-repo
set GOOSE_GLOBAL_SKILLS=%APPDATA%\Block\goose\skills
set USER_AGENTS_SKILLS=%USERPROFILE%\.agents\skills
set USER_GOOSE_SKILLS=%USERPROFILE%\.config\goose\skills
set PINEAL_GOOSE_SKILLS=C:\Projects\pineal-epifiz\.goose\skills

echo [1/4] GitHub deposu klonlaniyor...
if exist "%CLONE_DIR%" (
    echo Depo mevcut, guncelleniyor (git pull)...
    cd /d "%CLONE_DIR%"
    git pull
) else (
    git clone --depth 1 https://github.com/gooseworks-ai/goose-skills.git "%CLONE_DIR%"
)

if %ERRORLEVEL% NEQ 0 (
    echo [HATA] Git klonlama basarisiz oldu! Lutfen internet baglantinizi ve git kurulumunu kontrol edin.
    pause
    exit /b 1
)

echo [2/4] Dizinler hazirlaniyor...
if not exist "%GOOSE_GLOBAL_SKILLS%" mkdir "%GOOSE_GLOBAL_SKILLS%"
if not exist "%USER_AGENTS_SKILLS%" mkdir "%USER_AGENTS_SKILLS%"
if not exist "%USER_GOOSE_SKILLS%" mkdir "%USER_GOOSE_SKILLS%"
if not exist "%PINEAL_GOOSE_SKILLS%" mkdir "%PINEAL_GOOSE_SKILLS%"

echo [3/4] Skiller Goose global ve proje dizinlerine kopyalaniyor...
if exist "%CLONE_DIR%\skills" (
    xcopy /E /I /Y /Q "%CLONE_DIR%\skills\*" "%GOOSE_GLOBAL_SKILLS%\"
    xcopy /E /I /Y /Q "%CLONE_DIR%\skills\*" "%USER_AGENTS_SKILLS%\"
    xcopy /E /I /Y /Q "%CLONE_DIR%\skills\*" "%USER_GOOSE_SKILLS%\"
    xcopy /E /I /Y /Q "%CLONE_DIR%\skills\*" "%PINEAL_GOOSE_SKILLS%\"
)

echo [4/4] Goose Skills konfigürasyonu kontrol ediliyor...
echo.
echo ===================================================================
echo [BASARILI] gooseworks-ai/goose-skills basariyla yuklendi!
echo Yuklenen yetenekler:
echo  - Marketing & GTM Playbooks (Ads, Content, Outreach, SEO)
echo  - Video & Creative Ad Production
echo  - Data Scraping & Enrichment
echo Goose bir sonraki baslatmada veya oturumda tum skilleri otomatik gorecektir.
echo ===================================================================
pause
