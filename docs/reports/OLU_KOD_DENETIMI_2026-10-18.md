# ÖLÜ KOD / "ÇALIŞIR GİBİ YAPAN" DENETİMİ — 2026-10-18

**Kapsam:** kullanıcı talebi — (a) "çalışmayan çalışır gibi yapan" kodun tespiti ve
düzeltilmesi, (b) kullanılmayan ajan dosyalarının tespiti ve düzeltilmesi,
(c) gece bekçisi ile kilitlenmesi. Fiyat/parametre işi kapsam dışı (ikincil).

**Yöntem:** varsayım yok. Her bulgu AST/import grafiği ile kanıtlandı; her düzeltme
çalıştırılarak doğrulandı. Ölü kod tespiti **kalıcı bir dedektöre** (`scripts/dead_code_audit.py`)
ve **CI adımına** dönüştürüldü.

---

## 1. KISA SONUÇ

| Ölçüm | Sonuç | Kanıt |
|---|---|---|
| `agent_core/agents/` içindeki ajan modülü | **13/13 CANLI** (ölü ajan dosyası YOK) | `agent_core/task_executor.py` 13 ajanı kaydediyor ve çağırıyor; `lilith_growth.py` CLI-only (`./run_lilith.py`) |
| Executor'da kayıtlı ama **çağrılmayan** ajan | **0** | `scripts/dead_code_audit.py` C3 → 0 |
| Kayıt defterindeki **düşürülemeyen** yetenek | **0** (26/26 düşürülebilir) | C4 → 0 (kaynak: `bootstrap()` kayıt defteri) |
| Hiç import edilmemiş Python modülü | **0** | C1 → 0 |
| Yalnız testlerden import edilen modül | **0** | C1b → 0 |
| Hiç çağrılmayan ≥12 satırlık fonksiyon | **1 → SİLİNDİ** | `agent_core/services/profile_deep_scan.py:266 summary_row` |
| Giriş noktalarından **ulaşılamayan** frontend dosyası | **12 → SİLİNDİ (4779 satır)** | C5 → 0 |
| Ölü kodu koruyan **test dosyası** | **6 → CANLI YÜZEYE BAĞLANDI** | aşağıdaki §4 |

**Kullanıcının "kullanılmayan ajan dosya" sezgisi AJAN KATMANINDA doğru değil** —
ölü olan şey ajan dosyaları değil, (1) bir ölü P0 kopyası, (2) 12 ölü frontend
bileşeni ve (3) o ölü bileşenleri koruyan 6 test dosyasıydı. Ajan katmanı 13/13
kayıtlı ve çağrılabilir; bu, AST + çağrı grafiğiyle ölçülmüş bir gerçektir
(rapor §3).

---

## 2. DÜZELTMELER (silinen / değişen)

### 2.1 `DeepScanResult.summary_row` — ölü P0 kopyası (26 satır) · SİLİNDİ

`agent_core/services/profile_deep_scan.py:266` — P0'da yazılmış, P1'de
`agent_core/services/deep_profile_resolver.py:166 _summary_row()` ile
**değiştirilmiş** ölü bir kopya. İki uygulama farklı: canlı olan kimlik
kaydını da hesaba katıyor.

Kanıt (ölü olduğu):

```
$ grep -rn "summary_row" --include="*.py" .
./agent_core/services/deep_profile_resolver.py:166:def _summary_row(      ← CANLI ( çağrılıyor, :257)
./agent_core/services/profile_deep_scan.py:266:    def summary_row(self)  ← ÖLÜ (hiç çağrılmıyor)
```

Neden tehlikeliydi: okuyan biri `summary_row()`'ın derin tarama satırını
ürettiğini sanır; üretmiyor. Bu, "çalışır gibi yapan" sınıfının ta kendisi.

### 2.2 12 ölü frontend bileşeni (4779 satır) · SİLİNDİ

PR #143 (merge `7212657`) frontend'i yeniden yazdı; eski bileşenler depoda
kaldı ama **hiçbir yerden import edilmiyordu** → ekranda ASLA görünmüyordu.

```
$ grep -rn "CockpitEntry\|OrganikIrisCanvas\|UnifiedCompactPanel" frontend/src/
frontend/src/store.ts:19:// UnifiedCompactPanel hata yolları); "ağ hatası" maskesi yok.   ← yalnız yorum
```

Silinen dosyalar (satır sayısı `wc -l` ile ölçüldü):

| Dosya | Satır | Durum |
|---|---|---|
| `frontend/src/components/UnifiedCompactPanel.svelte` | 1990 | hiç import edilmiyor |
| `frontend/src/components/CockpitEntry.svelte` | 685 | hiç import edilmiyor |
| `frontend/src/components/PinealEye.svelte` | 440 | yalnız ölü `CockpitEntry` import ediyordu |
| `frontend/src/components/diesel/LcdLogin.svelte` | 501 | yalnız ölü `UnifiedCompactPanel` import ediyordu |
| `frontend/src/lib/irisRenderer.ts` | 251 | yalnız ölü `PinealEye` import ediyordu |
| `frontend/src/components/diesel/AnalogGauge.svelte` | 162 | ölü panelden |
| `frontend/src/components/diesel/SplitFlap.svelte` | 141 | ölü panelden |
| `frontend/src/components/diesel/ToggleSwitch.svelte` | 126 | ölü panelden |
| `frontend/src/components/diesel/KeyLock.svelte` | 121 | ölü panelden |
| `frontend/src/components/diesel/EmergencyStop.svelte` | 109 | ölü panelden |
| `frontend/src/components/OrganikIrisCanvas.svelte` | 228 | hiç import edilmiyor |
| `frontend/src/components/PillarFeed.svelte` | 25 | ölü panelden |
| **TOPLAM** | **4779** | |

Kümeli etki: 3 büyük ölü bileşen, kendi içinde 9 dosyayı daha "canlı"
görünür kılıyordu; ulaşılabilirlik (fixpoint) hesabı bunları da ölü saydı.

**Doğrulama (çalıştırıldı):**

```
$ cd frontend && npm run check     →  svelte-check found 0 errors and 0 warnings
$ cd frontend && npm run build     →  ✓ built in 2.19s
$ grep -rl "UnifiedCompactPanel\|CockpitEntry\|OrganikIrisCanvas" dist/   →  (boş)
```

Derleme çıktısının hash'i silme öncesi/sonrası **aynı** (`index-BtTpn3JI.js`):
silinen kod paket zaten içinde değildi.

### 2.3 Ölü paneli koruyan 6 test dosyası → CANLI YÜZEYE BAĞLANDI

En kritik bulgu: **testler yeşildi, ama korudukları şey üretime girmiyordu.**

| Test dosyası | Ne koruyordu | Yeni hedef |
|---|---|---|
| `tests/unit/test_ui_honesty_contract.py` | ölü panelin uydurma başarı metinleri, ölü `depth_forensics` anahtarı, kurgu ASPASIA sohbeti | CANLI frontend ağacının tamamı + canlı kokpit |
| `tests/unit/test_frontend_agent_model_contract.py` | ölü panelin statik `primaryModel/backupModel` tablosu | canlı arayüzde statik tablo **yok** (model canlı `run.model`'den gelir) + RUNBOOK'un üretilen gölge bloğu SoT ile birebir |
| `tests/unit/test_wiring_frontend.py` | ölü panelin okuduğu alanlar | canlı frontend ağacı (sahte alanlar **hiçbir yerde** geçemez) |
| `tests/unit/test_routing_shadows.py` | ölü paneldeki routing gölge marker'ları | RUNBOOK gölgesi + "Svelte hedefi yokken üretici çökmez" testi |
| `tests/unit/test_aspasia_chief_layer.py` | ölü panelin ASPASIA komut→chat akışı | canlı kokpit `/api/aspasia/chat` + backend'de `/api/aspasia/command` ucunun yaşadığının kanıtı |
| `tests/unit/test_p1_profile_routing.py` | iki dosyadaki "profil bağlandı" dili | canlı frontend ağacının **tamamı** (daha güçlü kilit) |
| `tests/e2e/test_cross_stack_runtime.py` | ölü paneldeki `_provenance` bağlayıcısı | canlı War Room'un `run.call_ids` bağlayıcısı |

### 2.4 `scripts/generate_routing_shadows.py` — Svelte hedefi OPSİYONEL

Silinen panel, routing gölge üreticisinin **tek Svelte hedefi**ydi → üretici
`FileNotFoundError` ile çöküyordu (CI adımı kırılırdı). Canlı arayüzde statik
ajan-model tablosu **yoktur** (model/via koşunun provenance'ından gelir), bu
yüzden Svelte gölgesi üretilmez; **RUNBOOK gölgesi canlıdır** ve üretilmeye
devam eder. Üretici artık hedef yoksa çökmez, açıkça atlar.

### 2.5 `scripts/dead_code_audit.py` — YENİ kalıcı dedektör (gece bekçisi)

Beş denetim, hepsi AST tabanlı:

| Kod | Ne ölçer | Sonuç |
|---|---|---|
| C1 | hiç import edilmemiş Python modülü | 0 |
| C1b | yalnız testlerden import edilen modül (üretimde kullanılmayan) | 0 |
| C2 | kendi gövdesi dışında hiç referans edilmemiş ≥12 satırlık fonksiyon | 0 |
| C3 | executor'da kayıtlı ama çağrılmayan ajan | 0 |
| C4 | kayıt defterinde olup **düşürülemeyen** yetenek (26) | 0 |
| C5 | giriş noktalarından (main.ts → App.svelte) **ulaşılamayan** frontend dosyası | 0 |

Gürültüyü sıfırlayan kurallar: giriş noktaları izin listesi · FastAPI rota
handler'ları (`app.get(...)(fn)`) ve dekoratörlü fonksiyonlar "çağrılmamış"
sayılmaz · `from x import y as z` takma adları çözülür · özyineleme
(öz-referans) dış referans sayılmaz · MCP sunucusu jenerik yüzey olarak
notlanır · dinamik yerel import varsa C5 ölçülmez (yanlış suçlama olmaz).

CLI: `python scripts/dead_code_audit.py` · `--json` (CI için, bulgu varsa exit 1).

### 2.6 CI adımı (`.github/workflows/ci.yml`)

```yaml
- name: Dead code guard (ölü modül/ajan/yetenek/frontend bileşeni)
  run: |
    python scripts/dead_code_audit.py | tee /tmp/dead-code-guard.log
    # bulgu varsa exit 1 → ölü kod depoya giremez
```

---

## 3. AJAN KATMANI ÖLÇÜMÜ (kullanıcının asıl sorusu)

**Kayıtlı ajanlar (`agent_core/task_executor.py`) — 13, hepsi çağrılabilir:**

```
passion_mapper · friction_detector · cognitive_profiler · resonance_synthesizer
human_behavior · mirror_truth · resonance_calc · pattern_interrupt
autonomous_verifier · authenticity_auditor · osint_investigator
shadow_executor · depth_analyst
```

- 10'u router (`cognitive_router.GOAL_FOCUS`) üzerinden **dinamik** seçilir
  (`task_executor.py:1719` → `self.agents[agent_name]`),
- 3'ü doğrudan: `osint_investigator` (`:1284`), `shadow_executor` (`:2602`),
  `depth_analyst` (`:2524`).
- `lilith_growth.py` CLI-only'dir (`./run_lilith.py`, P3 kararı) — bu bir ölü
  dosya DEĞİL, belgelenmiş bir giriş noktasıdır.
- `target_psyche_profiler.py` üç ajanın ortak taban sınıfıdır (canlı).

**Kanıt (ölü ajan yok):**

```
$ python scripts/dead_code_audit.py
C3 KAYITLI AMA ÇAĞRILMAYAN AJAN (0)
```

**Beyan ↔ gerçek ayrımı (config/gateway vs kayıt):** `config/agent_tiers.json`
21 rol, `config/task_routing.json` 4 ajan, gateway zincirleri 21 ajan
listeler; bunların 9'u executor'da *ajan* değil, *servis/kanal* adıdır
(`aspasia`, `dialogue_manager`, `lilith_growth`, `interpreter`, jüri
koltukları, `vision_analyzer`) ve bu ayrım zaten P1/P3 raporlarında yazılıdır.
Bu turda **yeni bir ayrım uydurulmadı**; ölçülen durum rapora işlendi.

---

## 4. EKLENEN / DEĞİŞTİRİLEN TESTLER

- **YENİ** `tests/unit/test_dead_code_audit.py` — **11 test**:
  ölü modül yok · test-only modül yok · ölü fonksiyon yok · 13 ajanın hepsi
  çağrılabilir · 26 yeteneğin hepsi düşürülebilir · ölü frontend bileşeni yok ·
  **revert-doğrulama**: geçici ölü modül yazılır → dedektör görür; geçici ölü
  frontend bileşeni geri konur → dedektör görür; silinen 12 bileşen geri
  gelirse test kırmızıya döner.
- Yeniden yazıldı: `test_ui_honesty_contract.py` (17 test),
  `test_frontend_agent_model_contract.py` (5), `test_wiring_frontend.py` (6),
  `test_routing_shadows.py` (9, +1 yeni: "Svelte hedefi yokken üretici çökmez").
- Değişti: `test_aspasia_chief_layer.py`, `test_p1_profile_routing.py`,
  `tests/e2e/test_cross_stack_runtime.py`.

---

## 5. ÖLÇÜM SONUÇLARI

```
$ .venv/bin/python -m pytest tests -q -p no:cacheprovider
2800 passed, 6 skipped (188.84s)                       ← tam koşu (bkz. §7)

$ .venv/bin/ruff check .
All checks passed!

$ .venv/bin/python scripts/audit_regression.py
✓ BEKÇİ GEÇTİ — regresyon yok, taban çizgisi gerçekle birebir.

$ .venv/bin/python scripts/dead_code_audit.py
TOPLAM: modül=0 test-only=0 fonksiyon=0 ajan=0 yetenek=0 frontend=0

$ cd frontend && npm run check   →  svelte-check found 0 errors and 0 warnings
$ cd frontend && npm run build   →  ✓ built in 2.19s
$ .venv/bin/python scripts/generate_inventory_page.py --check  →  GÜNCEL
$ .venv/bin/python scripts/export_skills.py --check               →  Skills paketi taze: 26 dosya
$ .venv/bin/python scripts/generate_routing_shadows.py           →  taze ✅
```

Envanter: 742 → **732 dosya** (−12 frontend, +1 dedektör, +1 test).

---

## 6. DOĞRULANMADI (sebebiyle)

| Konu | Sebep |
|---|---|
| Canlı 9Router LLM zinciri | sandbox'ta `127.0.0.1:20128` erişilemiyor (HTTP 000) |
| Canlı X/IG kazıma, socid, holehe | egress kapalı |
| Frontend'in **görsel** doğrulaması (ekran görüntüsü) | `svelte-check` + `build` + import grafiği ile ölçüldü; tarayıcı koşusu yapılmadı |
| `UnifiedCompactPanel` silinince **kayıp olan ürün davranışı** | canlı arayüzde zaten yoktu; aşağıdaki §7'de kayda geçti |
| Android/Tauri tarafı | bu turda ölü dosya taraması yapılmadı (yalnız frontend) |

---

## 7. KAYDA GEÇEN ÜRÜN BOŞLUĞU (kullanıcı kararı gerekir)

PR #143'teki arayüz yenilenmesiyle **ölü panelde kalan iki davranış canlı
arayüze taşınmadı**:

1. **ASPASIA "komut önce, chat fallback" akışı**: canlı kokpit doğrudan
   `/api/aspasia/chat` çağırıyor. `/api/aspasia/command` ucu backend'de
   **ayakta** ve README:114'te dokümante; yalnız UI onu çağırmıyor. Bu
   **ölü kod değil, ürün boşluğudur** (sunucu tarafı yaşıyor).
2. **Çağrı kimliği (call id) bağlayıcısı**: ölü panel `_provenance.call_id`
   okuyordu; canlı War Room backend'in `call_ids` alanını bağlıyor
   (`backend/api.py:1987`) — yani sözleşme yaşıyor, alan adı değişti.

Bunlar "ölü kod" düzeltmesi değil, ürün kararı gerektiren iki nokta; bilerek
dokunulmadı ve burada kayda geçti.

---

## 8. ÇALIŞTIRILAN KOMUTLAR (özet)

```bash
python scripts/dead_code_audit.py            # 5 denetim (C1..C5)
python scripts/dead_code_audit.py --json     # makine-okunur
pytest tests/unit/test_dead_code_audit.py -q # 11 passed
pytest tests -q -p no:cacheprovider          # tam koşu
ruff check .
python scripts/audit_regression.py
cd frontend && npm run check && npm run build
python scripts/generate_inventory_page.py && python scripts/generate_inventory_page.py --check
python scripts/generate_routing_shadows.py
python scripts/export_skills.py --check
grep -rn "<ölü dosya adı>" --include="*.py" --include="*.svelte" .   # referans yokluğu
```
