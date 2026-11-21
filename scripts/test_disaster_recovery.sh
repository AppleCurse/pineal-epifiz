#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# scripts/test_disaster_recovery.sh
#
# Disaster-recovery / volume-persistence smoke testi (docker-compose dağıtımı).
#
# KANITLAR:
#   - `pineal_memory` ve `pineal_vault` named volume'ları, konteynerin
#     hard-kill edilip silinmesi (`docker compose down`, bilinçli olarak -v
#     YOK) ve sıfırdan yeniden yaratılması sonrasında veriyi korur.
#
# KANITLAMAZ:
#   - Gerçek yedek alıp geri yüklemeyi (backup almaz — persistence testidir).
#   - Railway gibi platformların kendi volume mekanizmasını (repo dışı config).
#
# KULLANIM (Docker daemon çalışırken):
#   bash scripts/test_disaster_recovery.sh                  # Git Bash/WSL/Linux
#   DR_WAIT_TIMEOUT=600 bash scripts/test_disaster_recovery.sh   # yavaş makine
#
# NOTLAR:
#   - Docker imajı PINEAL_ENV=production ile açılır ve tokensuz başlamaz
#     (bkz. RUNBOOK). Script, .env'inize dokunmadan geçici bir compose
#     override dosyasıyla test amaçlı PINEAL_TOKEN enjekte eder.
#   - `--wait` healthcheck'i bekler; sabit sleep yok. İlk çalıştırmada imaj
#     yoksa otomatik build edilir (Playwright/Chromium nedeniyle dakikalar
#     sürebilir). Test sonunda stack `down` ile durdurulur (-v YOK).
# ---------------------------------------------------------------------------

set -euo pipefail

SERVICE="pineal"
MEMORY_FILE="//app/memory/dr_test.json"
# [2026-11-21 · P1-33] Uygulama artık /app/vault-data birimini gerçekten
# okur (PINEAL_VAULT_FILE > /app/vault-data > CWD — agent_core/utils/vault_path.py);
# bu script hacmin kendisini değil, uygulamanın gördüğü yolu sınar.
VAULT_FILE="/app/vault-data/.pineal_vault.json"
MARKER="persisted_test_data"
WAIT_TIMEOUT="${DR_WAIT_TIMEOUT:-300}"

if [ -t 1 ]; then
    BOLD=$'\033[1m'; GREEN=$'\033[32m'; RED=$'\033[31m'; RESET=$'\033[0m'
else
    BOLD=""; GREEN=""; RED=""; RESET=""
fi
step() { printf '\n%s==> %s%s\n' "$BOLD" "$*" "$RESET"; }
ok()   { printf '  %s[OK] %s%s\n' "$GREEN" "$*" "$RESET"; }
bad()  { printf '  %s[XX] %s%s\n' "$RED" "$*" "$RESET"; }

# Compose dosyaları repo kökünde.
cd "$(dirname "$0")/.."

# Test amaçlı token override'ı: production tokensuz açılmaz (RUNBOOK: Token kipi).
# Git Bash uyumu: mktemp'in /tmp'i Windows docker.exe'e C:\tmp olarak görünür
# ("The system cannot find the file specified" — docker compose -f açamaz).
# Bu yüzden override dosyası repo kökünde, $(pwd) tabanlı mutlak yol ile
# oluşturulur: /c/... yolları MSYS→Windows dönüşümünde doğru eşlenir.
# (Script bu noktada zaten repo köküne cd yapmış durumda.)
OVERRIDE_FILE="$(mktemp "$(pwd)/.dr_override.XXXXXX")"
cat >"$OVERRIDE_FILE" <<'YAML'
services:
  pineal:
    environment:
      - PINEAL_TOKEN=dr-test-token
YAML
dcomp() { docker compose -f docker-compose.yml -f "$OVERRIDE_FILE" "$@"; }
cleanup() {
    docker compose down >/dev/null 2>&1 || true   # -v YOK: volume'lara dokunma
    rm -f "$OVERRIDE_FILE"
}
trap cleanup EXIT

echo ">>> DISASTER RECOVERY TEST (volume persistence) <<<"

step "0/6 Ön kontroller"
command -v docker >/dev/null 2>&1 || { bad "docker bulunamadı"; exit 1; }
docker info >/dev/null 2>&1 || { bad "Docker daemon çalışmıyor (Docker Desktop açık mı?)"; exit 1; }
docker compose version >/dev/null 2>&1 || { bad "docker compose v2 gerekli ('docker compose version' hata verdi)"; exit 1; }
if ! VOLUMES="$(docker compose -f docker-compose.yml config --volumes 2>/dev/null)"; then
    bad "docker compose config başarısız — compose sürümü çok eski olabilir (env_file required:false icin v2.24+ gerekir)"
    exit 1
fi
for v in pineal_memory pineal_vault; do
    grep -qx "$v" <<<"$VOLUMES" || { bad "docker-compose.yml'de '$v' volume tanimi yok"; exit 1; }
done
ok "docker + compose v2 hazir; tanimli volume'lar: $(echo "$VOLUMES" | tr '\n' ' ')"

# Eski compose surumlerinde --wait-timeout yoktur; yoksa sadece --wait kullan.
WAIT_ARGS=(--wait)
if docker compose up --help 2>/dev/null | grep -q -- '--wait-timeout'; then
    WAIT_ARGS=(--wait --wait-timeout "$WAIT_TIMEOUT")
fi

RESULT=0

step "1/6 Konteyneri ayağa kaldır (healthcheck beklenir, t/o ${WAIT_TIMEOUT}s)"
dcomp up -d "${WAIT_ARGS[@]}"
ok "konteyner çalışıyor ve /health hazır"

step "2/6 Kalıcı volume'lara test verisi yaz"
dcomp exec -T "$SERVICE" sh -c \
    "mkdir -p /app/memory /app/vault-data \
     && printf '{\"status\": \"%s\"}' '$MARKER' > '$MEMORY_FILE' \
     && printf '{\"status\": \"%s\"}' '$MARKER' > '$VAULT_FILE'"
ok "yazıldı: $MEMORY_FILE ve $VAULT_FILE (uygulama yolundan)"

step "2b/6 Uygulama kasa dosyasını görebiliyor mu? (uygulamanın çözdüğü yol)"
# Eskiden "volume var mı" diye dosya yazılıp okunuyordu — hacme dosya
# düşmesi, UYGULAMANIN o dosyayı okuyacağı anlamına gelmez (P1-33: hacim
# bağlıydı ama VAULT_FILE /app/.pineal_vault.json idi). Şimdi asıl kanıt:
# konteyner İÇİNDE uygulamanın çözdüğü kasa yolu /app/vault-data mı?
RESOLVED=$(dcomp exec -T "$SERVICE" python -c \
    "from agent_core.utils.vault_path import default_vault_file; print(default_vault_file())" | tr -d '\r')
echo "  uygulama kasa yolu: $RESOLVED"
if [ "$RESOLVED" != "/app/vault-data/.pineal_vault.json" ]; then
    bad "uygulama /app/vault-data yerine '$RESOLVED' kullanıyor (P1-33 regresyonu)"
    RESULT=1
else
    ok "uygulama /app/vault-data birim yolunu çözüyor"
fi

step "3/6 FELAKET: hard-kill + konteyneri sil (down — bilinçli olarak -v YOK)"
dcomp kill "$SERVICE" || true
dcomp down
ok "konteyner öldü ve silindi; named volume'lar yerinde"

step "4/6 Sıfırdan taze konteyner yarat (crash sonrası redeploy simülasyonu)"
dcomp up -d "${WAIT_ARGS[@]}"
ok "konteyner yeniden oluşturuldu ve sağlıklı"

step "5/6 Veri hayatta mı?"
# RESULT 2b adımında belirlenmiş olabilir; sıfırlamayız, üzerine ekleriz.
if dcomp exec -T "$SERVICE" cat "$MEMORY_FILE" 2>/dev/null | grep -q "$MARKER"; then
    ok "pineal_memory -> veri HAYATTA"
else
    bad "pineal_memory -> veri KAYIP"; RESULT=1
fi
if dcomp exec -T "$SERVICE" cat "$VAULT_FILE" 2>/dev/null | grep -q "$MARKER"; then
    ok "pineal_vault  -> veri HAYATTA"
else
    bad "pineal_vault  -> veri KAYIP"; RESULT=1
fi

step "6/6 Temizlik"
if [ "$RESULT" -eq 0 ]; then
    dcomp exec -T "$SERVICE" sh -c "rm -f '$MEMORY_FILE' '$VAULT_FILE'" || true
    ok "test verisi volume'lardan silindi (stack 'down' ile durduruldu)"
else
    echo "  Hata ayıklama için dr_test.json dosyaları volume'larda bırakıldı."
fi

echo
if [ "$RESULT" -eq 0 ]; then
    echo "DISASTER RECOVERY PASSED ✅  memory + vault verisi konteyner ölümünü atlattı."
else
    echo "DISASTER RECOVERY FAILED ❌  volume persistence bozuk — docker-compose.yml"
    echo "volume/mount tanımlarını ve volume'ların anonim değil NAMED olduğunu kontrol et."
    exit 1
fi
