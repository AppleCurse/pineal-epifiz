# B0 KABUL RAPORU — Kokpit Destek Sağlama ve Güvenli Devam Döngüsü

**Tarih:** 2026-10-14
**Kapsanan talep:** "Çekirdek kabul denetiminin sonuçlarını koru. Şimdi B0: kokpitten destek
sağlama ve güvenli devam döngüsünü tamamla." (§1-§6)
**Önceki denetim:** `reports/KABUL_DENETIMI_DESTEK_AKISI_2026-10-14.md` — **değiştirilmedi,
KABUL hükmü korunmuştur** (B0 bu rapordaki 3 eksik halkayı kapatır).

---

## 0. Karar

> **KABUL** — kapsamı bu raporda açıkça belirtilmiştir (§5.3-Kapsam).

B0'ın altı maddesi de dosya/kanıt + çalıştırılmış test ile kapatılmıştır:
U2E akışı, 6 negatif senaryo, kalıcılık/tekrar-güvenliği, E-GÖZ3-2 davranışsal testi,
state_bridge denetim izi/timeout, UI kablolaması. Tam paketler yeşildir (§4).

---

## 1. Destek durumu ≠ yürütme durumu (§1)

| Sözleşme | Uygulama | Kanıt |
|---|---|---|
| Resume **tüm `support_requests`'i otomatik resolved YAPMAZ** | `backend/routes/support.py:406` — resume öncesi yalnız `reopen()` çağrılır; destek kayıtlarına dokunulmaz. `agent_core/task_executor.py:1076-1122` — toplu kapatma YOK; talep bazında doğrulama + doğrulanmayan bloklayıcıda `ResumeBlockedError` |
| Yalnızca **ilgili talebin gerektirdiği destek sağlandığında VE engel giderildiğinde** kapat | `task_executor.py:1085-1116` — `kind=vault_open` → canlı kasa durumu, `kind=spend_cap` → canlı bütçe (`budget_status`), operatör → `approved && responses` (sağlanmamışsa KAPANMAZ). `checkpoint_store.py:261 record_support_response` + `:335 finalize_support` — HTTP yolunda yanıt `resolved` yapar, live-kontrol **önce** (`routes/support.py:220-260`: kilitli→423 **kayıt YOK**, bütçe→409 kayıt YOK) |
| Birden fazla açık talep **ayrı ayrı** takip | Talepler `status`/`resolved_at`/`resolution` alanlarıyla ayrı ayrı durumlanır (`checkpoint_store.py:261-355`); resume önkoşulu **açık bloklayanların listesini** döndürür (`routes/support.py:348-364` — yalnız ilgili şartı sağlamayanlar `missing`) |
| Destek ≠ yürütme durumu | `GET …/support` (`routes/support.py:128`) hem `task_status` hem `support_requests` hem `resume_running`'i **ayrı** döndürür; resume `reopen()` ile durum makinesinden geçer (`agent_core/services/task_lifecycle.py:176 reopen`, `routes/support.py:406`) |

**Test:** `tests/integration/test_support_cockpit.py` — `…missing_support_is_rejected:413`,
`…double_response…:347`, `tests/audit/test_support_flow_acceptance.py` (10/10, C hattı
`record` sonrası devam ediyor: C :166 + B0 eklentisi destek kaydı zorunlu).

## 2. Kokpit: AwaitingHumanEvent görünür + kalıcı geri yükleme (§2)

| İstenen | Kanıt |
|---|---|
| Görev, talep kimliği, ENGEL, ihtiyaç, sonraki adım görünür | `frontend/src/components/SupportPanel.svelte:87-124` — `support-card` içinde görev (`task_id`), `support_id`, `reason` (engel), `options` (ihtiyaç), `next_action`; `store.ts:151-166 supportRequests/supportTaskId/refreshSupport` |
| Hassas veri/anahtar YOK | Gösterim yalnız REST'in **proje edilmiş** cevabı (`routes/support.py:145-160 views`; `checkpoint_store.py:219 support_view` — `input_data`/anahtar/çerez bu nesneye GİRMEZ). Test: `test_support_cockpit.py:549` — `input_data`, `GIZLI_BIO…`, `policy`, `ingested_outputs` cevapta YOK |
| WS dalı genel event dalından ÖNCE | `frontend/src/App.svelte:156` — `data.event_type === 'AwaitingHuman'` (`:163` genel event dalı — ÖNCE) |
| Kop-yeniden bağlanınca açık talepler kalıcı kayıttan geri yüklenir | `App.svelte` `ws.onopen` → `refreshSupport(get(supportTaskId))` (kablolama testi `…ui_wiring…:570`); **kalıcı taraf** gerçek test: `test_support_cockpit.py:478 restart…` — oda belleği silinir, `GET …/support` dosyadan **açık talebi geri yükler**, destek sağlanır, resume biter |

**Test komutu/sonuç:** `pytest tests/integration/test_support_cockpit.py -q` → **10 passed**.

## 3. Güvenli resume (§3)

`POST /api/tasks/{task_id}/resume` → `backend/routes/support.py:274 api_resume_task`
(kayıt `backend/api.py:4682 register_support_routes(...)` — route düzeni korunmuş,
`api.py:611` tek-satır import; **monolit 6000/6000 ratchet'i korunur, yeni mantık dosyada**).

Sıra (her adımda istemciden gelen veri KABUL EDİLMEZ):
1. Kimlik: `auth_middleware` + (üretimde) token; rate `rate_limit` (:275).
2. Minor/devre temizliği `require_minor_clearance` (:288).
3. **Kalıcı kayıt yükle** (`ckpt.load`, :294-305) — `CheckpointCorrupted` → 409; mühürsüz/task_id uyuşmaz `CheckpointCorrupted` (`checkpoint_store.py:96-108 load` — "mührü tutmuyor") → **başka görevin verisi yüklenemez**.
4. **Sahip mührü** (:308-311): `owner != principal` → `TaskForbiddenError` → 403. (Adopt yan etkisi mühürden ÖNCE çalışmadığı için saldırgan sahiplenemez.)
5. Oda-görev mührü `guard_task` (:312) → 403.
6. Eşzamanlılık: `ckpt.claim_resume` (:317) — süreç belleği `_RESUME_CLAIMS` → ikinci istek **409 RESUME_ALREADY_RUNNING**; `finally` ile bırakılır.
7. Kasa 423 (`require_vault_open`, :327) ve bütçe 409 (:332 + def `:67 _budget_blocked` — `budget_status()` fail-closed).
8. Eksik destek 409 `RESUME_SUPPORT_MISSING` + `missing[]` (:348-364).
9. `run_mission` girdisi `ckpt_input` (sunucu) + **snapshot yalnız dosyadan**: `data["status"]` → `TaskStatus.model_validate` (`routes/support.py:392`). İstemciden gelen `resume` gövdesi **boş** (`{}`; UI: `SupportPanel.svelte:57 JSON.stringify({})`); `TaskStatus`/tamamlanmış ajan listesi istemciden ASLA okunmaz.
10. `reopen()` (:406) → `executor.execute_task(..., resume_from=stored_status)` (:410) — terminal bayraklar temizlenir, sekans parmak izleri korunur.

**Negatif testler (hepsi gerçek HTTP):**
- Başka operatörün görevi → **403** (`test_support_cockpit.py:297`, prod duruşu + iki token)
- Aynı talebe çift yanıt → **409 ALREADY_RESOLVED** (`:347`)
- Eşzamanlı iki resume → **409 RESUME_ALREADY_RUNNING** (`:373`)
- Eksik destekle resume → **409 RESUME_SUPPORT_MISSING** + `missing` (`:413`)
- Kasa yeniden kilitlendi → destek **423 + talep AÇIK KALIR**, resume **423** (`:433`)
- Süreç yeniden başlatıldıktan sonra destek sağlama → **çalışır ve biter** (`:478`)

## 4. Kalıcılık / tekrar-güvenliği (§4)

- **Kalıcılık (testli):** her destek kaydı/snapshot anında atomik dosyaya (`checkpoint_store.py:124 _atomic_write` = tmp+`os.replace`+fsync, mühür `:96-108`); `test_support_cockpit.py:478` (oda belleği sıfırlanır → açık talep dosyadan gelir → destek+resume tamamlanır), `:524` (mühürsüz kayıt `CheckpointCorrupted` → API 409). API kökleri: `PINEAL_CHECKPOINT_PATH`/`PINEAL_MEMORY_PATH`.
- **Başka görevin çıktısı yüklenemez:** dosya içi `task_id` mührü `load`'te zorunlu (`checkpoint_store.py:96-108`); test `:524`.
- **Kesinti → yan etki tekrarı garantisi (yöntem, sınır):**
  1. *Yöntem:* resume tohumlaması yan etkileri **tek tek** yürütür: (a) tamamlanan ajan **skip** (yan etki tekrarı YOK — kanıt: E2E `counts["cognitive_profiler"]==1`, I hattı kabul testi); (b) bloklayıcı destek **önce canlı doğrulanır**, doğrulanamazsa `ResumeBlockedError` → görev hiç devam etmez (`task_executor.py:1122`); (c) dosya yazımı **atomik** (yarım kayıt okunamaz, eski sürüm kalır); (d) resume kilidi süreç belleğinde (çift koşu imkânsız) + `reopen` sonrası tek mission.
  2. *Garanti alanı:* "destek doğrulanmadan devam YOK", "tamamlanan ajan tekrar çalışmaz", "yarım checkpoint'ten ilerleme YOK", "yan etki sonrası checkpoint yazımı sırası: kayıt → durum → fsync (persist hook'ları `api.py:2186/:2673`)"; kesinti bu sınırlarda **aynı etkiyi tekrarlamaz** — doğrulanmış E2E + restart testi.
  3. *Sınır (dürüst):* bir ajan **içinde**, o anlık snapshot persist'inden ÖNCE kesilirse o ajan yeniden çalıştırılır; idempotent olmayan dış çağrılar (ör. farklılaştırılmış POST) için ek idempotency-key katmanı YOKTUR — bu sınır bu B0'da kapsam dışıdır ve operatörün bilmesi gerekir.

## 5. Kabul boşlukları (§5)

1. **E-GÖZ3-2 davranışsal** — `tests/unit/test_task_lifecycle.py::test_production_redis_import_failure_is_hard_refusal` (üretim + Redis import düşerse `RuntimeError PRODUCTION_REQUIRES_REDIS`, kapıda) + `::test_dev_redis_import_failure_degrades_visibly` (dev → süreç yaşar, `DEGRADED_MODE` izi ERROR'da) — **2/2 geçti**.
2. **state_bridge yerel urllib** — hedef sınırı: `agent_core/mcp/state_bridge.py:76-83` (yalnız `LOCAL_API_HOSTS`), denetim izi: `:79/:82/:113-118` (`logger.warning`, **hedef adres loga sızar mı: hayır**), timeout: `:102 _opener.open(url, timeout=…)`. Testler: `tests/unit/test_mcp_state_bridge.py::TestAuditTrailAndTimeout` (timeout→fail-closed+iz; red→iz, adres-sızıntısı yok) — **25/25 geçti**.
3. **Kalan skipped (ana ortam, 8 adet) — hiçbiri B0 senaryosu değil:**
   - `tests/integration/test_speech_api_faz_c.py:212/223/240/247` — `multipart` modülü bu ortamda yok (4 test)
   - `tests/unit/test_consolidation_faz1_5.py:153` — crawl4ai ikinci adım `requirements-osint.txt`'te
   - `tests/unit/test_gorev2_artiklar.py:158` — PIL kurulu; None-dalı bu ortamda çalışmaz
   - `tests/unit/test_no_mock_in_production.py:130` — open-interpreter opsiyonel (`requirements-interpreter.txt`)
   - `tests/unit/test_no_mock_in_production.py:138` — crawl4ai opsiyonel
   **Lock ortamı 2 skipped:** `test_gorev2_artiklar.py:158` (aynı gerekçe) ve
   `test_no_mock_in_production.py:130` (open-interpreter). Bunlar **"geçti" sayılmamıştır**.

## 6. Uçtan uca (§6) — tek testte tam halka

`test_support_cockpit.py::test_e2e_block_visible_support_authorized_response_resume_verified` (:225):
engel (düşük güven + graceful kapalı → `halted_critical/halted_evidence` + `blocks_resume` talep)
→ **canlı WS'te `AwaitingHuman` çerçevesi** → REST'te görünür talep (görev/talep/engel/ihtiyaç/sonraki adım; gizli alan yok)
→ yetkili `POST provide` → **yalnız doğru talep** `resolved` → `POST resume` (boş gövde!)
→ `reopen` + dosya-snapshot'tan devam → **doğrulanmış sonuç** (tamamlanan ajan tekrar çalışmadı, kalan ajan 0.93 güvenle bitti, `resume_running=false`, tüm kayıtlar resolved).

---

## 7. Çalıştırılan test komutları ve sonuçları (gerçek çıktı özeti)

```
$ /home/user/.venv-pineal/bin/ruff check . --select E9,F
All checks passed!
$ /home/user/.venv-pineal/bin/python -m pytest tests/unit/test_api_monolith_ratchet.py -q
6 passed        # api.py = 6000/6000 (başlıkta: 0 satır baş boşluk)
$ /home/user/.venv-pineal/bin/python -m pytest tests/audit/test_support_flow_acceptance.py -q
10 passed       # KABUL denetimi (C hattı B0 sözleşmesine göre destek-kayıt adımıyla)
$ /home/user/.venv-pineal/bin/python -m pytest tests/integration/test_support_cockpit.py -q
10 passed       # E2E + 6 negatif + restart + izolasyon + gizli-alan + UI kablolama
$ /home/user/.venv-pineal/bin/python -m pytest tests/unit/test_task_lifecycle.py tests/unit/test_mcp_state_bridge.py -q
35 passed       # 10 yaşam döngüsü (+2 E-GÖZ3-2 davranışsal) + 25 state_bridge (+2 denetim/timeout)
$ /home/user/.venv-pineal/bin/python -m pytest tests -q -p no:cacheprovider
2445 passed, 8 skipped — EXIT 0        # 2 dk 10 sn
$ /home/user/.venv-lock/bin/python -m pytest tests -q -p no:cacheprovider
2451 passed, 2 skipped — EXIT 0        # 2 dk 15 sn
$ python3 scripts/audit_regression.py
✓ BEKÇİ GEÇTİ — regresyon yok, taban çizgisi gerçekle birebir.
$ Uygulama dumanı: backend.api import + GET route listesi (3 destek/resume rota) + checkpoint round-trip — EXIT 0
```

## 8. Kalan sınırlamalar / çalıştırılmayanlar (dürüstlük listesi)

1. **Tarayıcı DOM'u bu ortamda çalıştırılmadı:** `frontend/node_modules` yok ve sayfa
   gerçek tarayıcıda açılmadı. UI sözleşmesi **statik kablolama testleriyle** kilitli
   (`test_support_cockpit.py:570`: AwaitingHuman dalı, onopen geri yükleme, panel
   testid/alanları, resume boş gövde, gizli alan yok) + gerçek WS çerçevesi backend
   tarafından **sunucu tarafında doğrulandı**. Tarayıcı-içi görsel doğrulama **kullanıcıya** aittir.
2. **`npm run build` çalıştırılmadı** (node_modules kurulu değil) — olası Svelte derleme
   hatası bu ortamda yakalanmaz; sözdizimi gözden geçirildi ama derleyici değil.
3. **Süreç yeniden başlatma testi** oda belleğini silip dosyayı koruyarak **in-process**
   simüle edilir (OS-seviyesi tam yeniden başlatma değil). Sınır-çizgisi: oda/payload
   belleği (süreç-geneli `_RESUME_CLAIMS` dâhil) + dosya-dışı kalıcı her şey. Üretimde
   tam yeniden başlatma AYNI mekanizmaya güvenir (dosya deposu) — ek doğrulama önerilir.
4. **8/2 skipped** yukarıda ad+gerekçeyle listelendi; **çalıştırılmayan = "geçti" sayılmadı**.
5. `python-dotenv` ana venv'de yok (`.env` yüklenmez); bu, B0'dan önceki bilinen ortam
   farkıdır — testler ortamı `monkeypatch` ile kurar, üründe `.env` gerekliliği etkilenmez.

## 9. Kapsamı belirtilen kabul kararı

**KABUL.** Kapsam: (a) backend destek/resume halkası — gerçek HTTP+WS+executor ile
doğrulanmış; (b) kalıcılık/tekrar-güvenliği — dosya deposu + in-process yeniden başlatma
testiyle doğrulanmış; (c) UI — **kablolama ve veri-sözleşmesi** testlenmiş, **görsel/tarayıcı
çalıştırımı hariç**; (d) E-GÖZ3-2/state_bridge denetim boşlukları kapatılmış.
Bu kapsam dışında kalan maddeler §8'de açıkça "çalıştırılmadı" olarak işaretlenmiştir.
Önceki `reports/KABUL_DENETIMI_DESTEK_AKISI_2026-10-14.md` hükmü **korunmuştur**.
