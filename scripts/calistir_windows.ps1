# ============================================================================
# PINEAL-EPİFİZ — GÖLGE DENETİMİ (Windows çalıştırıcısı)
#
# Bu betik, senin Windows makinesindeki sanal ortamda denetimi çalıştırır.
# Linux'ta denendiği için "dependency_missing" çıkan paketler, senin
# Windows ortamında zaten kurulu olabilir — bu betik o farkı gösterir.
#
# Kullanım (PowerShell'de, depo kökünde):  .\scripts\calistir_windows.ps1
# ============================================================================

$ErrorActionPreference = "Stop"
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")

Write-Host "== Pineal-Epifizi Gölge Denetimi (Windows) ==" -ForegroundColor Cyan
Write-Host "Depo kökü: $repoRoot" -ForegroundColor Gray
Write-Host ""

# 1. Sanal ortamı etkinleştir (varsa)
$venvPy = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
    Write-Host "HATA: .venv\Scripts\python.exe bulunamadı. Önce sanal ortamı oluştur:" -ForegroundColor Red
    Write-Host "  python -m venv .venv" -ForegroundColor Gray
    Write-Host "  .venv\Scripts\pip install pydantic httpx ruff python-dotenv" -ForegroundColor Gray
    exit 1
}

Write-Host "[1/4] Sanal ortam python bulundu: $venvPy" -ForegroundColor Green

# 2. Gerekli paketlerin yüklü olduğunu kontrol et (sessiz, hata verse de devam et)
Write-Host "[2/4] Denetim betiği çalıştırılıyor..." -ForegroundColor Gray
& $venvPy scripts/golge_denetimi.py

$exitCode = $LASTEXITCODE
if ($exitCode -ne 0) {
    Write-Host "Denetim betiği hata kodu $exitCode ile döndü." -ForegroundColor Red
    exit $exitCode
}

# 3. Rapor dosyalarının yerini göster
$json = Join-Path $repoRoot "reports\golge_denetimi.json"
$md   = Join-Path $repoRoot "docs\reports\GOLGE_DENETIMI.md"
Write-Host ""
Write-Host "[3/4] Rapolar yazıldı:" -ForegroundColor Green
Write-Host "  JSON: $json" -ForegroundColor Gray
Write-Host "  MD:   $md" -ForegroundColor Gray

# 4. Özet: ne açıldı, ne kaldı
Write-Host ""
Write-Host "[4/4] ÖNEMLI: Bu rapor BU makinede ölçülüyor." -ForegroundColor Cyan
Write-Host "  Eğer 'dependency_missing' çıkan bir yeteneğin paketi senin Windows'ta" -ForegroundColor Cyan
Write-Host "  zaten kuruluysa (ör. instagrapi, maigret, scrapling, trafilatura), o" -ForegroundColor Cyan
Write-Host "  yetenek zaten kullanılabilir — şalter zaten açık (.env'de true)." -ForegroundColor Cyan
Write-Host ""
Write-Host "  Hala kapalı olanlar için:" -ForegroundColor Cyan
Write-Host "    * ffmpeg        -> https://ffmpeg.org/download.html (Windows binary'sini indir, PATH'e ekle)"
Write-Host "    * theHarvester  -> Python 3.14+ gerektirir; Docker veya WSL2 ile çalıştırılabilir"
Write-Host "    * agent-reach   -> npm i -g agent-reach (AMA: dikkat! benzer isimli farklı projeler var)"
Write-Host "    * twscrape      -> pip install twscrape"
Write-Host "    * searxng       -> ayrı servis; SEARXNG_BASE_URL env değişkeni gerekli"
Write-Host ""
Write-Host "Tamam." -ForegroundColor Green
