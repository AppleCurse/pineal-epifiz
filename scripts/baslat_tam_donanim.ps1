# ============================================================================
# PINEAL-EPIFIZ -- TAM DONANIM TEK KOMUT BASLATICI (Windows)
# Zero hardcoded secrets: .pineal_vault.json okunur, loglara anahtar basilmaz.
# Kullanim: powershell -NoProfile -ExecutionPolicy Bypass -File scripts\baslat_tam_donanim.ps1 [-Restart] [-Port 8000] [-OpenBrowser]
# ============================================================================
[CmdletBinding()]
param(
    [switch]$Restart,
    [int]$Port = 8000,
    [switch]$OpenBrowser
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $RepoRoot

function Get-ListeningPids {
    param([int]$TargetPort)
    try {
        return @(
            Get-NetTCPConnection -LocalPort $TargetPort -State Listen -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty OwningProcess -Unique
        )
    } catch {
        return @()
    }
}

$existingPids = Get-ListeningPids -TargetPort $Port
if ($existingPids.Count -gt 0) {
    if (-not $Restart) {
        Write-Host "Pineal sunucusu zaten http://127.0.0.1:$Port uzerinde calisiyor (PID: $($existingPids -join ', '))." -ForegroundColor Green
        Write-Host "Yeniden baslatmak icin: powershell -NoProfile -ExecutionPolicy Bypass -File scripts\baslat_tam_donanim.ps1 -Restart" -ForegroundColor Gray
        if ($OpenBrowser) {
            Start-Process "http://127.0.0.1:$Port"
        }
        exit 0
    }
    foreach ($procId in $existingPids) {
        try {
            Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
        } catch {
        }
    }
    Start-Sleep -Milliseconds 900
}

# Python secimi (.venv varsa oncelikli, yoksa sistem python)
$PythonExe = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $PythonExe)) {
    $PythonExe = Join-Path $RepoRoot "venv\Scripts\python.exe"
}
if (-not (Test-Path $PythonExe)) {
    $cmdPy = Get-Command python -ErrorAction SilentlyContinue
    if ($cmdPy) { $PythonExe = $cmdPy.Source }
}
if (-not $PythonExe -or -not (Test-Path $PythonExe)) {
    throw "Python bulunamadi (.venv, venv veya PATH uzerinde)."
}

# Kasa dosyasini bellege yukle (loglara asla deger basma)
$VaultFile = Join-Path $RepoRoot ".pineal_vault.json"
if (Test-Path $VaultFile) {
    try {
        $vaultObj = Get-Content $VaultFile -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($vaultObj.api_key -and "$($vaultObj.api_key)".Trim()) {
            $env:NINEROUTER_API_KEY = "$($vaultObj.api_key)".Trim()
            $env:OPENROUTER_API_KEY = "$($vaultObj.api_key)".Trim()
        }
        if ($vaultObj.ig_sessionid -and "$($vaultObj.ig_sessionid)".Trim()) {
            $env:IG_SESSIONID = "$($vaultObj.ig_sessionid)".Trim()
        }
    } catch {
        Write-Host "Uyari: .pineal_vault.json okunamadi: $($_.Exception.Message)" -ForegroundColor Yellow
    }
}

# Cekirdek calisma ayarlari (9Router IPv4: localhost ::1 Windows zaman asimini onler)
$env:PINEAL_ENV = "development"
$env:NINEROUTER_BASE_URL = "http://127.0.0.1:20128/v1"
$env:LIVE_LLM_E2E = "1"
$env:PINEAL_ALLOW_UNPRICED_MODELS = "1"
$env:PINEAL_POST_DETAIL_ENABLED = "true"
$env:PINEAL_POST_DETAIL_LIMIT = "24"
$env:PINEAL_IG_MAX_POSTS = "48"
$env:PINEAL_IG_SCROLL_PAGES = "8"
$env:PINEAL_IG_PAGINATION_BUDGET_SEC = "120"
$env:PINEAL_HANDLE_PROBE_PLATFORMS_LIMIT = "20"

# Dis arac yollari (%LOCALAPPDATA% altinda otomatik kesif)
$localApp = $env:LOCALAPPDATA
if ($localApp) {
    $pwRoot = Join-Path $localApp "ms-playwright"
    if (Test-Path $pwRoot) {
        $chromiumDirs = Get-ChildItem -Path $pwRoot -Directory -Filter "chromium*" -ErrorAction SilentlyContinue | Sort-Object Name -Descending
        foreach ($dir in $chromiumDirs) {
            foreach ($relBin in @("chrome-win64\chrome.exe", "chrome-win\chrome.exe")) {
                $cand = Join-Path $dir.FullName $relBin
                if (Test-Path $cand) {
                    $env:PINEAL_CHROMIUM_PATH = $cand
                    break
                }
            }
            if ($env:PINEAL_CHROMIUM_PATH) { break }
        }
    }

    $piperModel = Join-Path $localApp "pineal-tools\piper\tr_TR-dfki-medium.onnx"
    if (Test-Path $piperModel) { $env:PINEAL_PIPER_MODEL = $piperModel }

    $agentReachExe = Join-Path $localApp "pineal-tools\agent-reach-venv\Scripts\agent-reach.exe"
    if (Test-Path $agentReachExe) { $env:PINEAL_AGENT_REACH_CMD = $agentReachExe }

    $transCmd = Join-Path $localApp "pineal-tools\trans.cmd"
    if (Test-Path $transCmd) { $env:PINEAL_TRANSLATE_CMD = $transCmd }

    $toolsBin = Join-Path $localApp "pineal-tools\bin"
    if ((Test-Path $toolsBin) -and ($env:PATH -notlike "*$toolsBin*")) {
        $env:PATH = "$toolsBin;$env:PATH"
    }
}

# Anlamsal bellek (sentence-transformers kuruluysa hindsight aktif)
$hasSt = & $PythonExe -c "import importlib.util; print('1' if importlib.util.find_spec('sentence_transformers') else '0')" 2>$null
if ("$hasSt".Trim() -eq "1") {
    $env:PINEAL_MEMORY_ENGINE = "hindsight"
}

# Yerel juri (Ollama kurulu ve iki bagimsiz model mevcutsa acilir)
$ollamaExe = @(
    (Get-Command ollama -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source),
    (Join-Path $localApp "Programs\Ollama\ollama.exe"),
    (Join-Path $env:ProgramFiles "Ollama\ollama.exe")
) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1

if ($ollamaExe) {
    $tagsObj = $null
    try {
        $tagsObj = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 2 -ErrorAction Stop
    } catch {
        try {
            Start-Process -FilePath $ollamaExe -ArgumentList "serve" -WindowStyle Hidden | Out-Null
            for ($i = 0; $i -lt 8; $i++) {
                Start-Sleep -Milliseconds 500
                try {
                    $tagsObj = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 2 -ErrorAction Stop
                    break
                } catch {
                }
            }
        } catch {
        }
    }
    if ($tagsObj -and $tagsObj.models) {
        $installedModels = @($tagsObj.models | ForEach-Object { "$($_.name)" } | Where-Object { $_ })
        $preferredLocal = @("qwen2.5:1.5b", "llama3.2:1b") | Where-Object { $installedModels -contains $_ }
        if ($preferredLocal.Count -ge 2) {
            $juryModels = $preferredLocal
        } else {
            $juryModels = @($installedModels | Select-Object -First 3)
        }
        if ($juryModels.Count -ge 1) {
            $env:PINEAL_JURY_LOCAL_URL = "http://127.0.0.1:11434/v1"
            $env:PINEAL_JURY_LOCAL_MODELS = ($juryModels -join ",")
            $env:PINEAL_JURY_QUORUM = if ($juryModels.Count -ge 2) { "2" } else { "1" }
            $env:LOCAL_LLM_URL = "http://127.0.0.1:11434/v1"
            $env:LOCAL_LLM_MODEL = $juryModels[0]
        }
    }
}

# Tum saglikli yetenek kapilari
$enabledFlags = @(
    "ENABLE_AGENT_REACH", "ENABLE_COMPANY_TARGETING", "ENABLE_CRAWL4AI",
    "ENABLE_CROSS_PLATFORM", "ENABLE_HOLEHE", "ENABLE_IG_SECONDARY",
    "ENABLE_LOCAL_JURY", "ENABLE_LOCAL_STT", "ENABLE_LOCAL_TRANSLATE",
    "ENABLE_LOCAL_TTS", "ENABLE_MAIGRET", "ENABLE_MEDIA_FORENSICS",
    "ENABLE_REPORT_FACTORY", "ENABLE_SCRAPLING", "ENABLE_SEARXNG",
    "ENABLE_X_SENSOR", "ENABLE_BRAIN_HUB", "ENABLE_SOCID",
    "ENABLE_PHONE_OSINT", "ENABLE_COMPANY_OSINT", "ENABLE_MEDIA_OSINT",
    "ENABLE_SPEECH", "ENABLE_LANGUAGE", "ENABLE_SHADOW_ENGINE",
    "ENABLE_LILITH_ENGINE", "ENABLE_HOOK_STUDIO", "ENABLE_MOBILE_COACH",
    "ENABLE_BROWSER_CONTROL", "ENABLE_MCP"
)
foreach ($flag in $enabledFlags) {
    Set-Item -Path "env:$flag" -Value "true"
}
# Not: requirements-interpreter.txt [AUDIT 2026-09-11 P0] geregi open-interpreter>=0.4.0
# starlette<0.38.0 dayattigindan ana ortamda (starlette 1.10.0 + CVE-2026-48710) kapali tutulur.
$env:ENABLE_INTERPRETER = "false"

# Canli dogrulanmis, model_substitution_allowed=True ve sifir bozuk yedekli 9Router zincirleri
$env:OPENROUTER_CHAIN_DEPTH = "ag/claude-opus-5-5,ag/claude-sonnet-5-5,cx/gpt-6-luna,ag/gemini-3.8-flash"
$env:OPENROUTER_CHAIN_DIALOGUE = "ag/claude-sonnet-5-5,cx/gpt-6-luna,ag/gemini-3.8-flash"
$env:OPENROUTER_CHAIN_FAST = "groq/openai/gpt-oss-120b,ag/gpt-oss-120b-medium,cx/gpt-5.6-luna"
$env:OPENROUTER_CHAIN_VISION = "cx/gpt-6-luna,ag/gemini-3.8-flash,ag/gemini-4-carbon"

foreach ($deepAgent in @("MIRROR_TRUTH", "DEPTH_ANALYST", "RESONANCE_SYNTHESIZER", "SHADOW_EXECUTOR")) {
    Set-Item -Path "env:OPENROUTER_AGENT_CHAIN_$deepAgent" -Value "ag/claude-opus-5-5,ag/claude-sonnet-5-5,cx/gpt-6-luna,ag/gemini-3.8-flash"
}
foreach ($stratAgent in @("ASPASIA", "DIALOGUE_MANAGER", "HUMAN_BEHAVIOR", "FRICTION_DETECTOR", "COGNITIVE_PROFILER", "OSINT_INVESTIGATOR")) {
    Set-Item -Path "env:OPENROUTER_AGENT_CHAIN_$stratAgent" -Value "ag/claude-sonnet-5-5,cx/gpt-6-luna,ag/gemini-3.8-flash"
}
foreach ($visionAgent in @("VISION_ANALYZER", "AUTHENTICITY_AUDITOR")) {
    Set-Item -Path "env:OPENROUTER_AGENT_CHAIN_$visionAgent" -Value "cx/gpt-6-luna,ag/gemini-3.8-flash,ag/gemini-4-carbon"
}
# Dogrulayici yalniz OpenAI ailesini kullanir -> 3 capraz juri koltugunun tamami korunur
$env:OPENROUTER_AGENT_CHAIN_AUTONOMOUS_VERIFIER = "cx/gpt-6-luna,cx/gpt-5.6-luna"

foreach ($fastAgent in @("PASSION_MAPPER", "PATTERN_INTERRUPT", "AUTONOMOUS_VERIFIER_EXTRACT", "LILITH_GROWTH", "INTERPRETER")) {
    Set-Item -Path "env:OPENROUTER_AGENT_CHAIN_$fastAgent" -Value "groq/openai/gpt-oss-120b,ag/gpt-oss-120b-medium,cx/gpt-5.6-luna"
}

$env:OPENROUTER_AGENT_CHAIN_PINEAL_JUROR_GOOGLE = "ag/gemini-3.8-flash,ag/gemini-4-carbon-medium"
$env:OPENROUTER_AGENT_CHAIN_PINEAL_JUROR_CLAUDE = "ag/claude-sonnet-5-5,ag/claude-sonnet-4-6"
$env:OPENROUTER_AGENT_CHAIN_PINEAL_JUROR_OPEN = "groq/openai/gpt-oss-120b,ag/gpt-oss-120b-medium"

# Frontend derleme paketi hazir degilse uret
$distIndex = Join-Path $RepoRoot "frontend\dist\index.html"
if (-not (Test-Path $distIndex)) {
    Write-Host "frontend/dist eksik; npm run build calistiriliyor..." -ForegroundColor Yellow
    Push-Location (Join-Path $RepoRoot "frontend")
    try {
        if (-not (Test-Path "node_modules")) { & npm ci }
        & npm run build
    } finally {
        Pop-Location
    }
}

Write-Host "Pineal-Epifiz tam donanim sunucusu baslatiliyor: http://127.0.0.1:$Port" -ForegroundColor Cyan
if ($OpenBrowser) {
    Start-Process "http://127.0.0.1:$Port"
}

& $PythonExe -X utf8 -m uvicorn backend.api:app --host 127.0.0.1 --port $Port
exit $LASTEXITCODE
