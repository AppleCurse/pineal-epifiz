# UTF-8 Encoding
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host "===================================================================" -ForegroundColor Cyan
Write-Host "[GOOSE-SKILLS] Growth, GTM, Ads, Social ve Scraping Yetenekleri" -ForegroundColor Cyan
Write-Host "https://github.com/gooseworks-ai/goose-skills" -ForegroundColor Gray
Write-Host "===================================================================" -ForegroundColor Cyan

$cloneDir = "$env:APPDATA\Block\goose\skills\goose-skills-repo"
$gooseGlobalSkills = "$env:APPDATA\Block\goose\skills"
$userAgentsSkills = "$env:USERPROFILE\.agents\skills"
$userGooseSkills = "$env:USERPROFILE\.config\goose\skills"
$pinealGooseSkills = "C:\Projects\pineal-epifiz\.goose\skills"

Write-Host "`n[1/4] GitHub deposu klonlanıyor..." -ForegroundColor Yellow
if (Test-Path $cloneDir) {
    Write-Host "Depo mevcut, güncelleniyor (git pull)..." -ForegroundColor Gray
    Push-Location $cloneDir
    git pull
    Pop-Location
} else {
    git clone --depth 1 https://github.com/gooseworks-ai/goose-skills.git $cloneDir
}

if ($LASTEXITCODE -ne 0 -and !(Test-Path "$cloneDir\skills")) {
    Write-Host "[HATA] Git klonlama başarısız oldu!" -ForegroundColor Red
    exit 1
}

Write-Host "[2/4] Dizinler hazırlanıyor..." -ForegroundColor Yellow
$targets = @($gooseGlobalSkills, $userAgentsSkills, $userGooseSkills, $pinealGooseSkills)
foreach ($target in $targets) {
    if (!(Test-Path $target)) {
        New-Item -ItemType Directory -Path $target -Force | Out-Null
    }
}

Write-Host "[3/4] Skiller Goose dizinlerine kopyalanıyor..." -ForegroundColor Yellow
$sourceSkills = "$cloneDir\skills"
if (Test-Path $sourceSkills) {
    foreach ($target in $targets) {
        Copy-Item -Path "$sourceSkills\*" -Destination $target -Recurse -Force
        Write-Host " -> $target hedefine kopyalandı." -ForegroundColor Green
    }
}

Write-Host "`n===================================================================" -ForegroundColor Cyan
Write-Host "[BAŞARILI] gooseworks-ai/goose-skills tüm hedeflere kuruldu!" -ForegroundColor Green
Write-Host "Goose artık Growth, Marketing, Video, SEO ve Scraping yeteneklerine tam erişebilir." -ForegroundColor Green
Write-Host "===================================================================" -ForegroundColor Cyan
