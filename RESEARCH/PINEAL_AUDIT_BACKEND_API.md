---
title: "Pineal-Epifiz Derinlemesine Mimari ve Kod Denetim Raporu: Backend, Frontend, Edge Proxy, Dağıtım, Android ve Rust Core"
tags: [architecture, security, audit, backend]
status: active
created: 2026-11-09
---

# Pineal-Epifiz Çok Katmanlı Kod ve Mimari Denetim Raporu

Bu rapor, `C:\Projects\pineal-epifiz` deposundaki dört ana katmanın (**1. `backend/`**, **2. `frontend/`**, **3. `functions/` + `worker.ts` + Dağıtım Yapılandırmaları**, **4. `android/` + `rust_core/`**) **SALT OKUNUR** derinlemesine statik kod denetimi sonucunda hazırlanmıştır. Her bulgu; **Dosya Yolu**, **Satır Numarası**, **Kanıt**, **Önem Derecesi (`P0`–`P3`)** ve **Düzeltme Talimatı** formatında belgelenmiştir.

---

## Yönetici Özeti ve Katmanlar Arası Entegrasyon Durumu

| Katman | Gerçek Durum | Kritik Bulgular Özeti |
|---|---|---|
| **1. `backend/`** | Üretim omurgası (FastAPI, 5722 satırlık `api.py` + `routes/*`) | Windows'ta `fcntl` ve dizin üzerinde `os.open` nedeniyle `POST /api/override` ve `POST /api/commander/inject` uçlarının çökmesi (**P0**); `/api/tasks/{id}/changes` ve `/api/tasks/{id}/memory` uçlarında IDOR / sahip kontrolü eksikliği (**P1**); `/api/aspasia/command`, `/api/hook/generate` ve `/api/mobile/coach` uçlarında **Minor Gate (Reşit Olmayan Hedef Kilidi)** ve **Vault Interlock (Kasa Kilidi)** kontrollerinin atlanması (**P1**); `hook_studio.py` ve `mobile_coach.py`'nin kasa anahtarlarını (`POST /api/vault`) hiç almayan `aspasia_chief.llm` örneğini kullanması (**P1**); `hook_studio.py` içinde `final_conf == 0.0` olduğunda kelepçenin (clamp) devre dışı kalıp ham güven skorunun geri yüklenmesi (**P1**). |
| **2. `frontend/`** | Svelte 5 tabanlı 4 görünümlü arayüz (`spiderfoot`, `cockpit`, `warroom`, `control`) | `SpiderFootCockpit.svelte` içinde `📡 DERİN KİMLİK RADARI (4 SİLAH)` sekmesinin (`activeTab === 'osint_radar'`) şablon bloğunun tamamen eksik olması ve sekme seçildiğinde boş ekran çıkması (**P0**); `SupportPanel.svelte`, `store.ts` ve `TacticalWarRoom.svelte` içinde `/support`, `/resume` ve `/halt` çağrılarında `client_id` gönderilmemesi nedeniyle backend'in `'default'` odasına bakıp `404/403` dönmesi (**P1**); `LiveControlPanel.svelte` içinde `scanned_urls` nesne dizisinin `string[]` sanılarak `[object Object]` olarak çizilmesi (**P2**). |
| **3. `functions/`, `worker.ts` ve Dağıtım** | Cloudflare Pages/Workers + Docker + Railway + Vercel | `functions/ws/[[path]].ts` içinde `upstream` WebSocket henüz `CONNECTING (0)` durumundayken istemci bağlantısının kabul edilmesi ve istemcinin gönderdiği ilk `{type:"auth"}` çerçevesinin `if (to.readyState !== WebSocket.OPEN) return;` ile sessizce çöpe atılması (**P0**); `Dockerfile` içinde `VERSION` ve `skills/` dizinlerinin imaja kopyalanmaması (**P1**); `docker-compose.yml` ve `railway.toml` içinde `/app/vault-data` bağlanırken backend'in `/app/.pineal_vault.json` dosyasına yazması (**P1**); `wrangler.toml` içinde referans verilen `wrangler.pages.toml` dosyasının depoda bulunmaması (**P2**). |
| **4. `android/` ve `rust_core/`** | **İzole / Yarım Kalmış İskeletler** (Backend ile entegre değil) | **`rust_core/`**: Python `backend/` ile entegre değildir; `autonomous_verifier.rs` her sonucu `"UNVERIFIED"` olarak işaretleyip ardından `"DOĞRULANDI"` aradığı için **%100 oranında hata vererek durur** (**P0**); `aspasia.rs` sabit `/workspace/agent_core` yolunu ve kaçışsız (unescaped) `self.api_key` metnini `python3 -c` içine gömer (**P0**); `src-tauri/src/lib.rs` içindeki `query_aspasia` kullanıcının sorusunu LLM'e göndermek yerine statik sistem raporunun başına `[Mosyo sorusu: ...]` yazar (**P1**). **`android/`**: Yalnızca `AspasiaChatEngine` backend'i (`http://10.0.2.2:8000/api/mobile/coach`) dener, diğer tüm analiz motorları doğrudan Google Gemini API'sine (`gemini-3.1-pro-preview`) bağlanır; kimlik doğrulama başlığı (`X-API-Key`) göndermez (**P1**); görsel analizde `imageBitmap = null` sabitlendiği için fotoğraf gönderimi çalışmaz (**P1**). |

---

## BÖLÜM 1: `backend/` Katmanı Denetim Bulguları

### 1.1. Platform Uyumsuzluğu ve Çalışma Zamanı Çökmeleri (P0)

#### [B-01] Windows Üzerinde `fcntl` İçe Aktarımı ve Dizin `os.open`/`os.fsync` Çağrısı Nedeniyle Çökme
- **Dosya Yolu ve Satır Numarası:**
  - `backend/routes/commander.py` — Satır `57-66` (`locked_learnings`) ve Satır `72-102` (`_store_evidence`)
  - `backend/api.py` — Satır `3353-3372` (`POST /api/override`)
- **Önem Derecesi:** **P0 (Kritik — Windows'ta %100 Çökme / HTTP 500)**
- **Kanıt:**
  ```python
  # backend/routes/commander.py:57-65
  @contextmanager
  def locked_learnings(path: str):
      """Advisory cross-process lock; all writers must use the same shared path."""
      import fcntl
      os.makedirs(os.path.dirname(path), exist_ok=True)
      with open(os.path.join(os.path.dirname(path), ".learnings.lock"), "a") as lock:
          fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
  ```
  ```python
  # backend/routes/commander.py:92-95
          directory_fd = os.open(os.path.dirname(mem_path), os.O_RDONLY)
          try:
              os.fsync(directory_fd)
          finally:
              os.close(directory_fd)
  ```
  1. `fcntl` yalnızca Unix/POSIX sistemlerde mevcuttur. Windows üzerinde `POST /api/override` çağrıldığında (`backend/api.py:3361`), `locked_learnings(lp)` yakalanmayan bir `ModuleNotFoundError: No module named 'fcntl'` fırlatarak sunucunun HTTP 500 dönmesine yol açar.
  2. `POST /api/commander/inject` çağrıldığında (`backend/routes/commander.py:165`), `_store_evidence` hem `import fcntl` hem de Windows'ta `PermissionError (EACCES)` fırlatan dizin üzerinde `os.open(..., os.O_RDONLY)` çağrısı yüzünden her zaman `500 EVIDENCE_STORE_FAILED` döner.
  3. Üstelik `_store_evidence` veriyi sabit `.pineal_memory/learnings.json` yoluna yazarken (`commander.py:73`), `api_override` veriyi `os.path.join(executor.memory.storage_path, "learnings.json")` (`memory/learnings.json`) yoluna yazar (`api.py:3360`). İki uç farklı dosyaları kilitler ve günceller.
- **Düzeltme Talimatı:**
  1. `locked_learnings` içinde platform kontrolü yapın: POSIX'te `fcntl.flock`, Windows'ta (`os.name == "nt"`) `msvcrt.locking` veya süreç içi `threading.RLock` + atomik `os.replace` kullanın (`backend/checkpoint_store.py:86-99` içindeki atomik yazım deseni gibi).
  2. `_store_evidence` içindeki dizin `os.open`/`os.fsync` bloğunu yalnızca `os.name != "nt"` koşulunda çalıştırın veya `try/except OSError:` ile sarın.
  3. `_store_evidence` fonksiyonunun sabit `.pineal_memory` yerine ilgili odanın `executor.memory.storage_path` dizinini kullanmasını sağlayın.

---

### 1.2. Yetkilendirme, Oda Sahipliği (IDOR) ve Güvenlik Kapısı (Gate) İhlalleri (P1)

#### [B-02] Görev Değişiklikleri (`/changes`) ve Hafıza (`/memory`) Uçlarında Görev Sahipliği (IDOR) Kontrolü Eksikliği
- **Dosya Yolu ve Satır Numarası:**
  - `backend/api.py` — Satır `4955-5006` (`GET /api/tasks/{task_id}/changes`)
  - `backend/api.py` — Satır `5191-5257` (`GET /api/tasks/{task_id}/memory`)
- **Önem Derecesi:** **P1 (Yüksek — Yetkisiz Veri Erişimi / IDOR)**
- **Kanıt:**
  `GET /api/tasks/{task_id}` (`routes/tasks.py:72`) ve `GET /api/tasks/{task_id}/graph` (`api.py:5050`) uçları `_task_access(task_id, request)` çağırarak `guard_task` üzerinden operatör/oda sahipliğini doğrularken, `GET /api/tasks/{task_id}/changes` ve `GET /api/tasks/{task_id}/memory` uçları **hiçbir `_task_access` veya `guard_task` kontrolü yapmadan** doğrudan diskteki `memory/` dizinini ve tüm `execution_rooms` sözlüğünü tarar:
  ```python
  # backend/api.py:4955-4972
  @app.get("/api/tasks/{task_id}/changes")
  async def get_task_changes(task_id: str, client_id: str = "default"):
      room = get_room(client_id, create=False)
      entry = None
      if room:
          entry = _find_history_entry_in_room(room, task_id)
      if not entry:
          for r in list(execution_rooms.values()):
              entry = _find_history_entry_in_room(r, task_id)
  ```
  Benzer şekilde `get_task_memory` (`api.py:5191`) doğrudan `executor = get_room("default")["executor"]` üzerinden hedef hafıza kristalini (`executor.memory.load_crystal(target_id)`) herhangi bir istemciye döndürür.
- **Düzeltme Talimatı:**
  Her iki uca `request: Request` parametresi ekleyin ve işleme başlamadan önce `err = _task_access(task_id, request)` kontrolünü çalıştırıp `if err is not None: return err` ile yetkisiz erişimleri HTTP 403 ile reddedin.

#### [B-03] `POST /api/aspasia/command` Ucunda Reşit Olmayan Hedef Kilidi (`_require_minor_clearance`) ve Kasa Kilidi (`_require_vault_open`) Eksikliği
- **Dosya Yolu ve Satır Numarası:**
  - `backend/api.py` — Satır `4399-4445` (`_aspasia_command_dispatch`) ve Satır `4448-4471` (`POST /api/aspasia/command`)
- **Önem Derecesi:** **P1 (Yüksek — Güvenlik ve Hukuki Kapı Bypass'ı)**
- **Kanıt:**
  `POST /api/initiate` (`api.py:3284-3292`) ve `POST /api/commander/dispatch` (`routes/commander.py:131-136`) görev başlatmadan önce hem `_require_minor_clearance(req.url, room=room)` (HTTP 451) hem de `_require_vault_open(room)` (HTTP 423) kontrollerini zorunlu tutar. Ancak `POST /api/aspasia/command` üzerinden gelen komutta bir URL veya `@kullanici` bulunduğunda (`_extract_target_from_command`), `_aspasia_command_dispatch` doğrudan `asyncio.create_task(run_mission(cid, target, ...))` başlatır (`api.py:4425-4435`) ve **ne `_require_minor_clearance` ne de `_require_vault_open` kontrolü yapar**:
  ```python
  # backend/api.py:4425-4435
      mission_coro = run_mission(
          cid,
          target,
          "",
          "",
          "",
          task_id=task_id,
          initial_lifecycle=lifecycle,
      )
      task_handle = asyncio.create_task(mission_coro)
  ```
- **Düzeltme Talimatı:**
  `_aspasia_command_dispatch` içinde `target` tespit edildiğinde, `lifecycle` oluşturulmadan hemen önce `minor_err = _require_minor_clearance(target, room=room, extra_texts=[text])` ve `vault_err = _require_vault_open(room)` kontrollerini çalıştırın; hata varsa ilgili HTTP 451 / 423 yanıtını döndürün.

#### [B-04] `POST /api/hook/generate` ve `POST /api/mobile/coach` Uçlarında Güvenlik Kapısı Eksikliği ve Yanlış LLM Nesnesi Kullanımı
- **Dosya Yolu ve Satır Numarası:**
  - `backend/api.py` — Satır `3617-3618`
  - `backend/routes/hook_studio.py` — Satır `133-250` ve `304-316`
  - `backend/routes/mobile_coach.py` — Satır `57-116` ve `150-162`
- **Önem Derecesi:** **P1 (Yüksek — Kasa Anahtarlarının Çalışmaması ve Güvenlik Kapısı Bypass'ı)**
- **Kanıt:**
  1. `backend/api.py:3617-3618` satırlarında:
     ```python
     register_mobile_coach_routes(app, llm_getter=lambda: aspasia_chief.llm)
     register_hook_studio_routes(app, llm_getter=lambda: aspasia_chief.llm, room_getter=get_room)
     ```
     Operatör `POST /api/vault` (`api.py:4329-4356`) ile API anahtarı kaydettiğinde, anahtarlar yalnızca ilgili odanın `room["executor"].llm` nesnesine (`llm.set_api_key(...)`) ve `os.environ["OPENROUTER_API_KEY"]` değişkenine yazılır; küresel `aspasia_chief.llm.api_key` alanı **hiçbir zaman güncellenmez**. Sunucu `.env` içinde anahtar olmadan başlatıldıysa, kasa kilidi açılsa bile `/api/hook/generate` ve `/api/mobile/coach` her zaman `LLM_NOT_CONFIGURED` nedeniyle sessizce şablon yedeklerine (fallback) düşer.
  2. Her iki uç da dış LLM çağrısı yapmasına rağmen `_require_vault_open(room)` ve `_require_minor_clearance(...)` kontrollerini **hiç çağırmaz**; ayrıca `rate_limit(...)` koruması da yoktur.
- **Düzeltme Talimatı:**
  1. `llm_getter` fonksiyonunu istemcinin `client_id` odasındaki `get_room(client_id)["executor"].llm` nesnesini döndürecek şekilde değiştirin (veya `POST /api/vault` içinde `aspasia_chief.llm` nesnesini de senkronize edin).
  2. `generate_hook` ve `mobile_coach` uçlarına `rate_limit`, `_require_vault_open(room)` ve `_require_minor_clearance` kontrollerini ekleyin.

#### [B-05] `hook_studio.py` İçinde `final_conf == 0.0` Olduğunda Epistemik Kelepçenin (Clamp) Devre Dışı Kalması
- **Dosya Yolu ve Satır Numarası:**
  - `backend/routes/hook_studio.py` — Satır `374-393`
- **Önem Derecesi:** **P1 (Yüksek — Epistemik Güvenlik İhlali)**
- **Kanıt:**
  ```python
  # backend/routes/hook_studio.py:374-388
      conf, valid = normalize_confidence(getattr(res, "confidence", None))
      clamped_conf = clamp(conf if valid else 0.85, epistemic_state)
      final_conf = clamped_conf if valid else clamp(0.85, epistemic_state)
      ...
      return res.model_copy(update={
          "confidence": final_conf if final_conf > 0.0 else (conf if valid else 0.85),
  ```
  `epistemic_state` tavanı `0.0` olduğunda (örneğin `UNVERIFIED` veya sıfır kanıt durumunda), `clamp(..., epistemic_state)` fonksiyonu güven skorunu bilinçli olarak `0.0` değerine indirir. Ancak `386.` satırdaki `final_conf if final_conf > 0.0 else (conf if valid else 0.85)` ifadesi, `final_conf == 0.0` olduğu anda kelepçelenmiş değeri çöpe atıp LLM'in ürettiği ham `conf` değerini veya `0.85` sabitini geri yükler!
- **Düzeltme Talimatı:**
  `backend/routes/hook_studio.py:386` satırını doğrudan `"confidence": final_conf,` olarak değiştirin.

#### [B-06] `DELETE /api/tasks/{task_id}` Ucunun Checkpoint Dosyasını ve Sahiplik Kaydını Silmemesi
- **Dosya Yolu ve Satır Numarası:**
  - `backend/routes/tasks.py` — Satır `131-180` (`delete_task`)
- **Önem Derecesi:** **P1 (Yüksek — Silinen Görevin Dirilmesi ve Disk Sızıntısı)**
- **Kanıt:**
  `delete_task` yalnızca `room["task_history"]` listesinden görevi çıkarır ve `memory/{task_id}.json` dosyasını siler (`routes/tasks.py:165-171`). Ancak:
  1. `checkpoint_store.delete(task_id)` çağrılmaz (`memory/checkpoints/{task_id}.json` diskte kalır). Bu nedenle silinmiş bir görev `POST /api/tasks/{task_id}/resume` (`routes/support.py:345`) ile diskteki checkpoint'ten tekrar diriltilebilir!
  2. `room["tasks_by_id"]` ve `room["support_by_task"]` içindeki referanslar temizlenmez.
  3. `task_owners.db` (`security/ownership.py`) içindeki sahiplik kaydı silinmez.
- **Düzeltme Talimatı:**
  `delete_task` içinde `checkpoint_store.delete(safe_id)` çağrısını ekleyin; `room["tasks_by_id"].pop(safe_id, None)` ve `room["support_by_task"].pop(safe_id, None)` ile bellek içi referansları temizleyin.

#### [B-07] `GET /api/speech/tts` Ucunda Bulut TTS (`edge_tts`) Kullanımı, Rate Limit ve Kasa Kilidi Eksikliği
- **Dosya Yolu ve Satır Numarası:**
  - `backend/routes/speech.py` — Satır `236-267` (`legacy_speech_tts`)
- **Önem Derecesi:** **P1 (Yüksek — Gizlilik / Kasa Kilidi İhlali ve DoS Açığı)**
- **Kanıt:**
  `POST /api/speech/synthesize` (`routes/speech.py:114-149`) yerel öncelikli (local-first) politikasını uygularken ve `rate_limit` kontrolü yaparken, `GET /api/speech/tts` ucu (`routes/speech.py:236`) **hiçbir `rate_limit` veya `_require_vault_open` kontrolü yapmadan** doğrudan Microsoft bulut servisine (`edge_tts.Communicate`) metin gönderir. Kasa kilitli (`VAULT_LOCKED`) olsa dahi hedefe dair hassas analiz metinleri Microsoft sunucularına sızar.
- **Düzeltme Talimatı:**
  `legacy_speech_tts` ucuna `_rate_identity(request)` tabanlı `rate_limit` ve kasa kilidi (`_require_vault_open`) kontrolü ekleyin; kasa kilitliyken yalnızca yerel TTS sağlayıcılarına izin verin.

#### [B-08] Çoklu Uçlarda Rate Limit Eksikliği veya İstemci Tarafından Sahtelenebilir `req.client_id` Anahtarı Kullanımı
- **Dosya Yolu ve Satır Numarası:**
  - `backend/routes/commander.py` — Satır `117-227` (`/dispatch`, `/inject`, `/phone-probe` — hiç rate limit yok)
  - `backend/routes/speech.py` — Satır `123` (`rate_limit("speech_synthesize", req.client_id or "default", ...)`)
  - `backend/routes/company.py` — Satır `62` (`rate_limit("company_ switching", req.client_id, ...)`)
  - `backend/routes/language.py` — Satır `67` (`rate_limit("language_set", req.client_id, ...)`)
  - `backend/api.py` — Satır `4551, 4668, 4700, 4800` (`req.client_id` üzerinden rate limit)
- **Önem Derecesi:** **P2 (Orta — Rate Limit Bypass)**
- **Kanıt:**
  `backend/api.py:854` içindeki `_rate_identity(request)` fonksiyonu, istemcinin her istekte rastgele `client_id` göndererek hız sınırını aşmasını engellemek için IP + doğrulanmış operatör kimliği üretir (`f"ip:{host}|p:{principal}"`). Ancak yukarıdaki uçlar `_rate_identity(request)` yerine doğrudan istemcinin JSON gövdesinde gönderdiği `req.client_id` değerini anahtar olarak kullanmaktadır; saldırgan her istekte farklı bir `client_id` göndererek hız sınırını tamamen atlatabilir.
- **Düzeltme Talimatı:**
  Tüm `rate_limit(...)` çağrılarında ikinci parametre olarak `req.client_id` yerine `_rate_identity(request)` kullanın ve `commander.py` uçlarına da `rate_limit` ekleyin.

#### [B-09] `POST /api/agents/status/{agent_id}` Ucunda Rastgele `agent_id` Enjeksiyonu ve Tüm Odalara Yayın
- **Dosya Yolu ve Satır Numarası:**
  - `backend/api.py` — Satır `3425-3454` (`update_agent_status`)
- **Önem Derecesi:** **P2 (Orta — Oda İzolasyonu İhlali ve Bellek Şişmesi)**
- **Kanıt:**
  `update_agent_status(agent_id: str, status: str)` ucu:
  1. `agent_id` değerinin `AGENT_RACK_SLOTS` içinde olup olmadığını veya `status` değerinin geçerli bir durum olup olmadığını doğrulamaz (`room["agent_statuses"][agent_id]` sözlüğüne sınırsız anahtar eklenebilir).
  2. İstemciye özel oda yerine `for cid, room in list(execution_rooms.items()):` döngüsüyle **sistemdeki tüm operatörlerin odalarını** değiştirir ve tüm WebSocket istemcilerine yayınlar.
- **Düzeltme Talimatı:**
  `agent_id` değerini `AGENT_RACK_SLOTS` kümesiyle, `status` değerini izin verilen durumlarla (`IDLE`, `WORKING`, `COMPLETED`, `ERROR`, `HALTED` vb.) sınırlandırın ve güncellemeyi yalnızca ilgili `client_id` odasına uygulayın.

#### [B-10] `checkpoint_store.py` İçinde Zaman Aşımı (`TIMED_OUT_CHECKPOINT_S`) Sonrası Yarım Kalan İndeks Temizliği
- **Dosya Yolu ve Satır Numarası:**
  - `backend/checkpoint_store.py` — Satır `198-211` (`mark_timed_out_all`)
- **Önem Derecesi:** **P2 (Orta — Tutarsız Bellek İndeksi)**
- **Kanıt:**
  `mark_timed_out_all` fonksiyonu, süresi dolan (`> 1800s`) `PAUSED_AWAITING_SUPPORT` görevlerinin diskteki JSON dosyasını `TIMED_OUT` olarak günceller; ancak `self._index` ve `self._support_to_task` bellek içi indekslerinden bu destek kimliklerini temizlemez. Sonuç olarak `resolve_support_id(support_id)` süresi dolmuş görevleri döndürmeye devam eder.
- **Düzeltme Talimatı:**
  `mark_timed_out_all` içinde `self._write_atomic(task_id, doc)` çağrısından sonra ilgili `support_id` kayıtlarını `self._support_to_task` indeksinden silin veya `self._index[task_id]` kaydını güncelleyin.

---

## BÖLÜM 2: `frontend/` Katmanı Denetim Bulguları

### 2.1. Eksik Şablonlar ve Kırık Kullanıcı Akışları (P0 – P1)

#### [F-01] `SpiderFootCockpit.svelte` İçinde `📡 DERİN KİMLİK RADARI (4 SİLAH)` (`osint_radar`) Sekmesinin Şablonunun Tamamen Eksik Olması
- **Dosya Yolu ve Satır Numarası:**
  - `frontend/src/components/SpiderFootCockpit.svelte` — Satır `118`, `276-298`, `1214-1326`, `1720-1724` ve `1758-2563`
- **Önem Derecesi:** **P0 (Kritik — Tıklanan Sekmenin Tamamen Boş Ekran Çizmesi / Ölü Kod)**
- **Kanıt:**
  `SpiderFootCockpit.svelte` içinde `1720-1724` satırlarında üst sekme çubuğunda `📡 DERİN KİMLİK RADARI (4 SİLAH)` düğmesi yer alır ve tıklandığında `activeTab = 'osint_radar'` ataması yapar:
  ```svelte
  <!-- frontend/src/components/SpiderFootCockpit.svelte:1720-1724 -->
  <button
    class="tab-btn osint-tab-btn"
    class:active={activeTab === 'osint_radar'}
    on:click={() => activeTab = 'osint_radar'}
  >📡 DERİN KİMLİK RADARI (4 SİLAH)</button>
  ```
  `<script>` bloğunda `runMaigretScan()`, `runHoleheScan()`, `runSocidScan()`, `runCrawlFetch()` fonksiyonları (`1214-1326`) ve durum değişkenleri (`276-298`) tanımlanmış olmasına rağmen, `1758-2563` satırları arasındaki `{#if activeTab === ...}` zincirinde **`{:else if activeTab === 'osint_radar'}` bloğu hiç yazılmamıştır!** (`graph`, `opening_hook`, `psychology_shadow`, `matrix`, `evidence`, `agents`, `control`, `logs` vardır; `osint_radar` ve `correlations` yoktur). Kullanıcı bu sekmeye tıkladığında çalışma alanı tamamen boş (siyah) kalır ve 4 OSINT aracının hiçbirine arayüzden erişilemez.
- **Düzeltme Talimatı:**
  `SpiderFootCockpit.svelte` içinde `{:else if activeTab === 'opening_hook'}` bloğundan sonra `{:else if activeTab === 'osint_radar'}` şablon bloğunu ekleyerek `osintSubTool` (`maigret`, `holehe`, `socid`, `crawl`) seçicilerini ve `runMaigretScan`, `runHoleheScan`, `runSocidScan`, `runCrawlFetch` tetikleyici formlarını/sonuç tablolarını bağlayın.

#### [F-02] `SupportPanel.svelte` ve `store.ts` İçinde Destek Yanıtlama ve Görev Sürdürme (`/resume`) Çağrılarında `client_id` Gönderilmemesi
- **Dosya Yolu ve Satır Numarası:**
  - `frontend/src/components/SupportPanel.svelte` — Satır `31-36` (`submit`) ve Satır `53-58` (`resumeTask`)
  - `frontend/src/store.ts` — Satır `72-74` (`getOrCreateClientId`) ve Satır `166-175` (`refreshSupport`)
  - Karşı taraf: `backend/routes/support.py` — Satır `189`, `293`, `341`
- **Önem Derecesi:** **P1 (Yüksek — Görev Kurtarma / Destek Akışının Çalışmaması)**
- **Kanıt:**
  `store.ts:73` her tarayıcı oturumuna `client_xxxxxxx` biçiminde rastgele bir `clientId` atar ve görevler bu odaya kaydedilir. Ancak:
  1. `SupportPanel.svelte:32-36`:
     ```ts
     const res = await apiFetch(`/api/tasks/${encodeURIComponent($supportTaskId || '')}/support/${encodeURIComponent(sid)}`, {
       method: 'POST',
       headers: { 'Content-Type': 'application/json' },
       body: JSON.stringify({ action: 'provide', note: 'kokpit' }),
     });
     ```
  2. `SupportPanel.svelte:54-58`:
     ```ts
     const res = await apiFetch(`/api/tasks/${encodeURIComponent($supportTaskId)}/resume`, {
       method: 'POST',
       headers: { 'Content-Type': 'application/json' },
       body: JSON.stringify({}),
     });
     ```
  3. `store.ts:169`: `await apiFetch(`/api/tasks/${encodeURIComponent(tid)}/support`)`
  Bu üç çağrının hiçbirinde `client_id` gönderilmez! Backend (`routes/support.py:189, 293, 341`) `client_id` gelmediğinde varsayılan olarak `"default"` odasına bakar (`room = get_room(client_id)`). Görev `client_xxxxxxx` odasında olduğu için `"default"` odasında bulunamaz veya yanlış odada aranır!
- **Düzeltme Talimatı:**
  `SupportPanel.svelte` içindeki her iki `POST` gövdesine `client_id: get(clientId) || 'default'` alanını ekleyin; `store.ts:169` içindeki `GET` çağrısına `?client_id=${encodeURIComponent(get(clientId) || 'default')}` sorgu parametresini ekleyin.

#### [F-03] `TacticalWarRoom.svelte` İçinde Görev Durdurma (`/halt`) Çağrısında `client_id` Eksikliği ve Hatanın Yutulması
- **Dosya Yolu ve Satır Numarası:**
  - `frontend/src/components/TacticalWarRoom.svelte` — Satır `257-266` (`haltTask`)
  - Karşı taraf: `backend/api.py` — Satır `4861-4895` (`POST /api/tasks/{task_id}/halt`)
- **Önem Derecesi:** **P1 (Yüksek — Savaş Odasından Görevin Durdurulamaması)**
- **Kanıt:**
  ```ts
  // frontend/src/components/TacticalWarRoom.svelte:257-266
  async function haltTask() {
    playHalt();
    const taskId = $taskStatus?.task_id;
    if (taskId) {
      try {
        await apiFetch(`/api/tasks/${taskId}/halt`, { method: 'POST' });
      } catch (_e) {}
    }
    isProcessing.set(false);
  }
  ```
  `POST /api/tasks/{task_id}/halt` ucu (`backend/api.py:4862`) `client_id: str = "default"` bekler ve `room = get_room(client_id, create=False)` içinde görevi arar. `TacticalWarRoom.svelte` `?client_id=...` göndermediği için backend `"default"` odasına bakar, `client_xxxxxxx` odasındaki görevi bulamaz (`404 TASK_NOT_FOUND`), `haltTask` ise yanıtı hiç kontrol etmeden `isProcessing.set(false)` yaparak arayüzde görev durmuş gibi gösterir; oysa arka planda görev çalışmaya devam eder!
- **Düzeltme Talimatı:**
  `SpiderFootCockpit.svelte:900-905` içinde yapıldığı gibi `TacticalWarRoom.svelte:262` satırında da `?client_id=${encodeURIComponent(get(clientId) || 'default')}` parametresini gönderin ve yalnızca `res.ok || res.status === 409` olduğunda `isProcessing.set(false)` yapın.

---

### 2.2. Veri Sözleşmesi Uyumsuzlukları ve Yanıltıcı UI Durumları (P2 – P3)

#### [F-04] `LiveControlPanel.svelte` İçinde `scanned_urls` Nesne Dizisinin `string[]` Sanılarak `[object Object]` Olarak Çizilmesi
- **Dosya Yolu ve Satır Numarası:**
  - `frontend/src/components/LiveControlPanel.svelte` — Satır `101-104` ve `477-481`
- **Önem Derecesi:** **P2 (Orta — Bozuk UI Görünümü)**
- **Kanıt:**
  Backend'de `TargetProfile.scanned_urls` (`agent_core/models.py`) `{ url, platform, handle, status, http_status, ... }` alanlarına sahip `ScannedUrl` nesnelerinden oluşur (`TacticalWarRoom.svelte:246` bunu `ScannedUrl[]` olarak doğru tipler). Ancak `LiveControlPanel.svelte:101-104`:
  ```ts
  $: targetUrls = [
    ...(($taskStatus?.target_profile?.detected_urls || []) as string[]),
    ...(($taskStatus?.target_profile?.scanned_urls || []) as string[]),
  ];
  ```
  ve `478-480` satırlarında `{#each targetUrls.slice(0, 6) as u}<span class="url-chip" title={u}>{u}</span>{/each}` olarak doğrudan metin gibi basar. Sonuç olarak ekranda URL yerine `[object Object]` rozetleri görünür.
- **Düzeltme Talimatı:**
  `LiveControlPanel.svelte:103` satırını `...(($taskStatus?.target_profile?.scanned_urls || []).map((s: any) => typeof s === 'string' ? s : s?.url).filter(Boolean))` olarak düzeltin.

#### [F-05] `SpiderFootCockpit.svelte` İçinde `selectedMode` (`TAM ADLİ TARAMA` vs `HIZLI RADAR`) Seçiminin Görev Başlatırken Hiç Kullanılmaması
- **Dosya Yolu ve Satır Numarası:**
  - `frontend/src/components/SpiderFootCockpit.svelte` — Satır `116`, `789-842` ve `1540-1553`
- **Önem Derecesi:** **P2 (Orta — İşlevsiz UI Kontrolü)**
- **Kanıt:**
  Üst barda kullanıcıya `TAM ADLİ TARAMA` (`selectedMode = 'full'`) ve `HIZLI RADAR` (`selectedMode = 'probe'`) seçenekleri sunulur (`1540-1553`). Ancak `startMission()` (`789-842`) içinde `selectedMode` değişkeni hiç okunmaz ve her iki modda da birebir aynı `/api/initiate` isteği gönderilir.
- **Düzeltme Talimatı:**
  `selectedMode === 'probe'` seçildiğinde hızlı yoklama ucunu çağırın veya `/api/initiate` yüküne `mode: selectedMode` alanını ekleyip backend'de ilgili tarama derinliğini uygulayın.

#### [F-06] `SpiderFootCockpit.svelte` İçinde Ölçüm Yokken Sabit `%82` Zaafiyet Skoru ve Kurgusal Psikodinamik Metin Gösterilmesi
- **Dosya Yolu ve Satır Numarası:**
  - `frontend/src/components/SpiderFootCockpit.svelte` — Satır `2085, 2097, 2109, 2118-2121` ve `2163, 2168`
- **Önem Derecesi:** **P2 (Orta — Kanıtsız / Sabit Kodlu Gösterge İhlali)**
- **Kanıt:**
  `activeDarkTriad` henüz boşken (hiçbir analiz çalışmamışken):
  - Satır `2118`: `<span class="metric-val">{activeDarkTriad?.exploitability ? \`%${Math.round(activeDarkTriad.exploitability * 100)}\` : '%82'}</span>` — analiz yokken bile ekranda `%82` yazar!
  - Satır `2085, 2097, 2109, 2121`: Çubuk genişlikleri sabit `0.15`, `0.25`, `0.08`, `0.82` değerleriyle doldurulur.
  - Satır `2163, 2168`: Analiz verisi yokken kurgusal cümleler (`'Hedef yüzeysel ilgiden kaçınırken, derin anlaşılma ve takdir edilme arayışında.'`) gerçek analiz sonucuymuş gibi gösterilir.
- **Düzeltme Talimatı:**
  Kanıt/analiz yokken `'Ölçümlenmedi (Veri Yok)'`, çubuk genişliği olarak `0%` ve açıklama olarak `'Henüz psikodinamik analiz çalıştırılmadı.'` gösterin.

#### [F-07] `App.svelte` İçinde `telemetryVisible` Değişkeninin Yorumla Çelişecek Şekilde `onMount` İçinde Kapatılması
- **Dosya Yolu ve Satır Numarası:**
  - `frontend/src/App.svelte` — Satır `122-126` ve Satır `363`
- **Önem Derecesi:** **P3 (Düşük — Mantık Çelişkisi)**
- **Kanıt:**
  Satır `122-126` üzerindeki açıklama *"Başlangıçta telemetri şeridi AÇIK: denetçi ilk bakışta ... görsün"* diyerek `let telemetryVisible = true;` tanımlar; ancak `onMount` içindeki `363.` satırda doğrudan `telemetryVisible = false;` yapılarak panel açılışta gizlenir.
- **Düzeltme Talimatı:**
  `App.svelte:363` satırındaki `telemetryVisible = false;` atamasını kaldırın veya varsayılan davranışı netleştirin.

#### [F-08] `AtlasPinealCockpit.svelte` ve `SpiderFootCockpit.svelte` İçinde Sabit/Tekrarlanan Şablon Hataları
- **Dosya Yolu ve Satır Numarası:**
  - `frontend/src/components/AtlasPinealCockpit.svelte` — Satır `960-976`
  - `frontend/src/components/SpiderFootCockpit.svelte` — Satır `2699-2715`
- **Önem Derecesi:** **P3 (Düşük — Yanıltıcı Telemetri Etiketi ve Çift Başlık)**
- **Kanıt:**
  1. `AtlasPinealCockpit.svelte:960-976` içinde kasa kilitli veya WebSocket kopuk olsa bile sabit yeşil `'Sensör Motoru: Twscrape & Playwright'`, `'LLM Gateway: Aktif / Router OK'` ve `'Protokol: WSS Çift Yönlü'` yazıları gösterilir.
  2. `SpiderFootCockpit.svelte:2699-2715` içinde `<div class="chat-header"><span>ASPASIA CANLI ANALİZ DANIŞMANI</span></div>` başlığı alt alta **iki kez** yazılmıştır (`2699` ve `2712`).
- **Düzeltme Talimatı:**
  `AtlasPinealCockpit.svelte` içindeki durum etiketlerini gerçek `$vaultLocked` ve `$uplinkStatus` mağazalarına bağlayın; `SpiderFootCockpit.svelte:2712-2715` arasındaki mükerrer `chat-header` bloğunu silin.

---

## BÖLÜM 3: `functions/`, `worker.ts` ve Dağıtım Yapılandırmaları Denetim Bulguları

#### [D-01] Cloudflare Edge WebSocket Proxy (`functions/ws/[[path]].ts`) İçinde İlk Mesaj Kimlik Doğrulama (`auth`) Çerçevesinin Kaybolması
- **Dosya Yolu ve Satır Numarası:**
  - `functions/ws/[[path]].ts` — Satır `61-66` ve `109-128`
  - Karşı taraf: `backend/routes/websocket.py` — Satır `133-163` (`WS_AUTH_TIMEOUT_S = 5.0`) ve `frontend/src/App.svelte` — Satır `192-199`
- **Önem Derecesi:** **P0 (Kritik — Cloudflare Pages Üzerinde WebSocket Kimlik Doğrulamasının Çökmesi)**
- **Kanıt:**
  ```ts
  // functions/ws/[[path]].ts:61-66
  const upstream: WebSocket = new WebSocket(wsTarget);
  const [pipeEnd, clientEnd] = Object.values(new WebSocketPair()) as [WebSocket, WebSocket];
  pipeEnd.accept();
  ```
  ```ts
  // functions/ws/[[path]].ts:109-128
  const pump = (from: WebSocket, to: WebSocket, label: string) => {
    from.addEventListener("message", (ev: any) => {
      if (to.readyState !== WebSocket.OPEN) return;
      ...
      to.send(ev.data);
    });
  };
  pump(pipeEnd, upstream, "client->upstream");
  pump(upstream, pipeEnd, "upstream->client");
  return new Response(null, { status: 101, webSocket: clientEnd });
  ```
  1. `new WebSocket(wsTarget)` çağrısı asenkrondur; `upstream` bağlantısı henüz Railway/Render backend'ine el sıkışmasını tamamlamadan (`upstream.readyState === WebSocket.CONNECTING (0)` iken) `pipeEnd.accept()` çağrılır ve istemciye `101 Switching Protocols` dönülür.
  2. İstemci (`App.svelte:192-199`) bağlantı açılır açılmaz (`ws.onopen`) ilk mesaj olarak `{ type: "auth", token: tok }` çerçevesini gönderir.
  3. Bu sırada `upstream.readyState` hâlâ `CONNECTING` olduğu için `111.` satırdaki `if (to.readyState !== WebSocket.OPEN) return;` kontrolü **istemcinin gönderdiği `auth` mesajını sessizce çöpe atar!**
  4. Backend (`backend/routes/websocket.py:149`) `5.0` saniye boyunca ilk mesajı bekler, alamadığı için `1008 First-message auth timeout` ile bağlantıyı kapatır.
- **Düzeltme Talimatı:**
  `functions/ws/[[path]].ts` içinde `upstream` bağlantısını `await fetch(httpTarget, { headers: { Upgrade: "websocket", ... } })` ile kurup `upstream.accept()` sonrasında çift yönlü pompalamayı başlatın **veya** `upstream.readyState === WebSocket.CONNECTING` iken `pipeEnd` üzerinden gelen mesajları bir `pendingQueue: any[] = []` dizisinde tamponlayıp `upstream.addEventListener("open", ...)` tetiklendiğinde sırayla `upstream.send(...)` ile iletin.

#### [D-02] `Dockerfile` İçinde `VERSION` Dosyasının ve `skills/` Dizinlerinin İmaja Kopyalanmaması
- **Dosya Yolu ve Satır Numarası:**
  - `Dockerfile` — Satır `53-58`
  - Karşı taraf: `agent_core/version.py` — Satır `26-44`
- **Önem Derecesi:** **P1 (Yüksek — Docker/Railway Ortamında Sürüm Bilgisinin `'unknown'` Dönmesi)**
- **Kanıt:**
  ```dockerfile
  # Dockerfile:54-57
  COPY backend/ ./backend/
  COPY agent_core/ ./agent_core/
  COPY config/ ./config/
  COPY --from=frontend /app/frontend/dist ./frontend/dist
  ```
  `agent_core/version.py:26` sürüm bilgisini kök dizindeki `/app/VERSION` dosyasından okur (`_VERSION_FILE = _REPO_ROOT / "VERSION"`). `Dockerfile` içinde `COPY VERSION ./VERSION` satırı olmadığı için Docker ve Railway dağıtımlarında `get_version()` her zaman `"unknown"` döner (`/api/health` ve `/api/version` uçları bozulur). Ayrıca kök dizindeki `skills/` klasörü de kopyalanmamaktadır.
- **Düzeltme Talimatı:**
  `Dockerfile:56` satırından sonra `COPY VERSION ./VERSION` ve `COPY skills/ ./skills/` satırlarını ekleyin.

#### [D-03] `docker-compose.yml` ve `railway.toml` İçindeki Kasa Hacmi (`/app/vault-data`) ile `backend/api.py` (`VAULT_FILE`) Arasındaki Yol Uyumsuzluğu
- **Dosya Yolu ve Satır Numarası:**
  - `docker-compose.yml` — Satır `31-33`
  - `railway.toml` — Satır `19-21`
  - `backend/api.py` — Satır `784`
- **Önem Derecesi:** **P1 (Yüksek — Konteyner Yeniden Başlatıldığında Kasa Anahtarlarının Sıfırlanması)**
- **Kanıt:**
  `docker-compose.yml:32` (`- pineal-vault:/app/vault-data`) ve `railway.toml:21` (`vault = "/app/vault-data"`) kalıcı disk hacmini `/app/vault-data` dizinine bağlar. Oysa `backend/api.py:784`:
  ```python
  VAULT_FILE = ".pineal_vault.json"
  ```
  diyerek kasa dosyasını çalışma dizinine (`/app/.pineal_vault.json`) yazar ve okur! `/app/vault-data` dizini kodda hiçbir yerde kullanılmaz; bu yüzden konteyner her yeniden başladığında mühürlenen kasa anahtarları silinir.
- **Düzeltme Talimatı:**
  `backend/api.py:784` satırını `VAULT_FILE = os.environ.get("PINEAL_VAULT_FILE", "/app/vault-data/.pineal_vault.json" if os.path.isdir("/app/vault-data") else ".pineal_vault.json")` olarak güncelleyin.

#### [D-04] `wrangler.toml` İçinde Referans Verilen `wrangler.pages.toml` Dosyasının Depoda Bulunmaması ve Gelecek Tarihli `compatibility_date`
- **Dosya Yolu ve Satır Numarası:**
  - `wrangler.toml` — Satır `18-23`
- **Önem Derecesi:** **P2 (Orta — Eksik Dağıtım Yapılandırma Dosyası)**
- **Kanıt:**
  ```toml
  # wrangler.toml:18-23
  # Bu yüzden Pages yolu AYRI dosyaya taşındı: `wrangler.pages.toml`
  # (kullanımı: npx wrangler pages deploy -c wrangler.pages.toml frontend/dist).
  name = "pineal-frontend"
  compatibility_date = "2026-09-01"
  main = "worker.ts"
  ```
  1. Yorumda belirtilen `wrangler.pages.toml` dosyası depoda **mevcut değildir** (`functions/` altındaki Pages Functions dosyalarını dağıtmak için gereken yapılandırma kayıptır).
  2. `worker.ts` (`1-118`) yalnızca HTTP `fetch` kancasına sahiptir; WebSocket yükseltmelerini (`Upgrade: websocket`) doğrudan `fetch(upstreamReq)` ile iletir ancak `PINEAL_BACKEND_ORIGIN` ortam değişkeni `wrangler.toml` içinde `[vars]` altında tanımlanmamıştır (tanımlanmadığında `worker.ts:45` uyarı vermeden tüm `/api/*` ve `/ws/*` isteklerine SPA `index.html` döndürerek JSON ayrıştırma hatalarına yol açar).
- **Düzeltme Talimatı:**
  Depoya `wrangler.pages.toml` dosyasını ekleyin; `worker.ts` içinde `/api/` veya `/ws/` ile başlayan bir istek geldiğinde `PINEAL_BACKEND_ORIGIN` tanımlı değilse `index.html` döndürmek yerine açık bir `502 Bad Gateway (PINEAL_BACKEND_ORIGIN not configured)` JSON hatası döndürün.

#### [D-05] `vercel.json` İçinde `/api/*` ve `/ws/*` Yönlendirme (Rewrite) Kurallarının Bulunmaması
- **Dosya Yolu ve Satır Numarası:**
  - `vercel.json` — Satır `1-6`
- **Önem Derecesi:** **P2 (Orta — Vercel Dağıtımında Backend Bağlantısının Çalışmaması)**
- **Kanıt:**
  `vercel.json` yalnızca statik Vite derlemesi yapar (`"rootDirectory": "frontend", "outputDirectory": "dist"`). Hiçbir `rewrites` kuralı tanımlanmadığı için `VITE_API_BASE` derleme zamanında ayarlanmamışsa Vercel üzerindeki tüm `/api/*` çağrıları `404 Not Found` döner.
- **Düzeltme Talimatı:**
  `vercel.json` içine backend sunucusuna yönlendiren `rewrites` kurallarını ekleyin veya `README` / dağıtım belgelerinde `VITE_API_BASE` ve `VITE_WS_BASE` zorunluluğunu doğrulayın.

---

## BÖLÜM 4: `android/` ve `rust_core/` Katmanları Denetim Bulguları

### 4.1. `rust_core/` Katmanı: Mimari Durum ve Hatalar

> **Mimari Gerçeklik Tespiti:** `rust_core/` (`pineal_heretic_core` kütüphanesi + `rust_core/src-tauri/` masaüstü kabuğu), Python `backend/` (`backend/api.py`) ile **entegre değildir**. Tauri uygulaması Python FastAPI sunucusuna bağlanmaz; kendi içinde ayrı bir Rust ajan boru hattı çalıştırmaya çalışır ve yalnızca `scripts/run_task.py` betiğini alt süreç (`subprocess`) olarak çağırır. Üstelik aşağıdaki kritik hatalar nedeniyle Rust ajan boru hattı çalışma zamanında işlevsizdir:

#### [R-01] `autonomous_verifier.rs` İçinde `"UNVERIFIED"` vs `"DOĞRULANDI"` Dil/Etiket Uyumsuzluğu Nedeniyle %100 Oranında Hata (`HaltReason::InsufficientEvidence`)
- **Dosya Yolu ve Satır Numarası:**
  - `rust_core/src/agents/autonomous_verifier.rs` — Satır `138-145` ve `168-190`
- **Önem Derecesi:** **P0 (Kritik — Rust Ajanının Hiçbir Koşulda Başarılı Olamaması)**
- **Kanıt:**
  `AutonomousVerifierAgent` Tavily aramasından dönen her bir sonucu `verifications` векtörüne eklerken `truth_status` alanına sabit `"UNVERIFIED"` yazar (`140.` satır):
  ```rust
  // rust_core/src/agents/autonomous_verifier.rs:138-143
  verifications.push(VerificationResult {
      claim_text: title,
      truth_status: "UNVERIFIED".to_string(),
      evidence_source: url,
      confidence_adjustment: 0.0,
  });
  ```
  Ancak hemen altında (`170.` satırda) doğrulanan kayıtları sayarken Türkçe `"DOĞRULANDI"` değerini arar:
  ```rust
  // rust_core/src/agents/autonomous_verifier.rs:169-190
  let confirmed = verifications
      .iter()
      .filter(|v| v.truth_status == "DOĞRULANDI")
      .count();
  ...
  if confirmed == 0 {
      return Err(HaltReason::InsufficientEvidence(reason));
  }
  ```
  Hiçbir yerde `truth_status = "DOĞRULANDI"` atanmadığı için `confirmed` **her zaman `0`** olur ve ajan %100 oranında `Err(HaltReason::InsufficientEvidence)` döndürerek durur!
- **Düzeltme Talimatı:**
  Tavily sonuçlarını hedef kimliği ve kanıt kriterleriyle karşılaştırarak eşleşen sonuçlara `"DOĞRULANDI"` (veya tutarlı bir enum değeri) atayın ya da doğrulama mantığını gerçek içerik eşleşmesine bağlayın.

#### [R-02] `aspasia.rs` İçinde Sabit `/workspace/agent_core` Yolu, Kod Enjeksiyonu (`self.api_key`) ve Boş API Anahtarı
- **Dosya Yolu ve Satır Numarası:**
  - `rust_core/src/aspasia.rs` — Satır `70-105`
  - `rust_core/src-tauri/src/lib.rs` — Satır `286`
- **Önem Derecesi:** **P0 (Kritik — Kod Enjeksiyonu ve Çalışma Zamanı Hatası)**
- **Kanıt:**
  ```rust
  // rust_core/src/aspasia.rs:70-101
  let python_script = format!(
      r#"
  import sys
  sys.path.insert(0, '/workspace/agent_core')
  ...
      os.environ['OPENROUTER_API_KEY'] = '{}'
  ..."#,
      self.api_key, summary.system_health, summary.status_message
  );
  let output = Command::new("python3").arg("-c").arg(python_script).output().await
  ```
  1. **Kod Enjeksiyonu:** `self.api_key` ve `summary.status_message` doğrudan Python kodu metnine (`'{}'`) kaçışsız (unescaped) yerleştirilir; tek tırnak içeren bir girdi doğrudan rastgele Python kodu çalıştırır.
  2. **Sabit Yol ve İkili Adı:** `/workspace/agent_core` yolu yalnızca özel bir konteynerde var olabilir; Windows/macOS/Linux masaüstünde mevcut değildir. Ayrıca Windows'ta `python3` komutu genellikle bulunmaz (`python` kullanılır).
  3. **Boş Anahtar:** `rust_core/src-tauri/src/lib.rs:286` satırında `AspasiaEngine::new(chief, String::new())` ile boş API anahtarı verilir ve Tauri kasası (`open_vault`) açıldığında bile `aspasia.api_key` hiç güncellenmez!
- **Düzeltme Talimatı:**
  Parametreleri Python kodunun içine `format!` ile gömmek yerine `Command::new(...).env("OPENROUTER_API_KEY", &self.api_key)` ve `stdin` / komut satırı argümanları (`sys.argv`) ile güvenli biçimde aktarın; `/workspace/agent_core` yerine çalışma dizinine göreli yol kullanın ve `open_vault` içinde `aspasia` anahtarını güncelleyin.

#### [R-03] `rust_core/src-tauri/src/lib.rs` İçinde `query_aspasia` Komutunun Kullanıcı Sorusunu LLM'e Göndermemesi
- **Dosya Yolu ve Satır Numarası:**
  - `rust_core/src-tauri/src/lib.rs` — Satır `212-222`
- **Önem Derecesi:** **P1 (Yüksek — Sahte / Yarım Kalmış Sohbet İşlevi)**
- **Kanıt:**
  ```rust
  // rust_core/src-tauri/src/lib.rs:212-222
  #[tauri::command]
  async fn query_aspasia(user_message: Option<String>, state: tauri::State<'_, CoreState>) -> Result<String, String> {
      let mut aspasia = state.aspasia.lock().await;
      let report = aspasia.report_system_overview().await;
      if let Some(msg) = user_message {
          if !msg.is_empty() {
              return Ok(format!("[Mosyo sorusu: {}]\n\n{}", msg, report));
          }
      }
      Ok(report)
  }
  ```
  Kullanıcı Tauri masaüstü uygulamasında Aspasia'ya bir soru sorduğunda, soru hiçbir zaman `aspasia` motoruna iletilmez; yalnızca genel sistem özetinin başına `[Mosyo sorusu: ...]` eklenip geri döndürülür.
- **Düzeltme Talimatı:**
  `AspasiaEngine` içine kullanıcı mesajını ve mevcut görev bağlamını alan gerçek bir `chat(user_message)` metodu ekleyin ve `query_aspasia` komutundan bu metodu çağırın.

#### [R-04] `mirror_truth.rs` İçinde Sürekli Hata Dönen `call_llm` İskeleti ve Yanlış `duration_ms` Ölçümü
- **Dosya Yolu ve Satır Numarası:**
  - `rust_core/src/agents/mirror_truth.rs` — Satır `37-43` ve `140-150`
- **Önem Derecesi:** **P1 (Yüksek — Çalışmayan Ajan İskeleti ve Hatalı Telemetri)**
- **Kanıt:**
  1. `call_llm` (`37-43`) her zaman sabit `Err("LLM_UNAVAILABLE: Rust ajanında yapılandırılmış gerçek LLM istemcisi yok...")` döndürür; bu nedenle `MirrorTruthAgent` hiçbir zaman başarılı olamaz.
  2. `140.` satırda `let started = std::time::Instant::now();` tüm işlemler bittikten hemen sonra tanımlanıp `150.` satırda `started.elapsed().as_millis()` okunur (her zaman `0ms` ölçer).
- **Düzeltme Talimatı:**
  `started` zamanlayıcısını `execute` fonksiyonunun en başına (`51.` satır) taşıyın ve `call_llm` metodunu gerçek HTTP LLM istemcisine bağlayın.

#### [R-05] `rust_core/src/` Altında Derlenmeyen Ölü Modüller (`aspasia_bridge.rs`, `llm_client.rs`, `scrapers/`)
- **Dosya Yolu ve Satır Numarası:**
  - `rust_core/src/lib.rs` — Satır `1-14`
  - `rust_core/src/aspasia_bridge.rs` — Satır `70-120`
  - `rust_core/src/llm_client.rs` — Satır `1-120`
  - `rust_core/src/scrapers/mod.rs`, `twitter.rs`, `instagram.rs`, `osint.rs`
- **Önem Derecesi:** **P2 (Orta — Derlenmeyen / Kopuk Ölü Kod)**
- **Kanıt:**
  `rust_core/src/lib.rs` yalnızca `agents`, `aspasia`, `chief`, `memory`, `models`, `orchestrator`, `python_Handover`, `resonance`, `security`, `stealth` modüllerini bildirir. `aspasia_bridge.rs`, `llm_client.rs` ve `scrapers/` klasörü `lib.rs` içinde **hiç bildirilmemiştir** (derlenmez). Üstelik `aspasia_bridge.rs:78` içinde `data = json.loads('{}')` ile Python kod enjeksiyonu ve `115.` satırda var olmayan `state.aspasia_bridge` alanına erişim bulunmaktadır.
- **Düzeltme Talimatı:**
  Kullanılmayan `aspasia_bridge.rs`, `llm_client.rs` ve `scrapers/` dosyalarını temizleyin veya derleme ağacına dahil edip kırık referanslarını düzeltin.

---

### 4.2. `android/` Katmanı: Mimari Durum ve Hatalar

> **Mimari Gerçeklik Tespiti:** `android/` uygulaması Python `backend/` ile **büyük ölçüde entegre değildir; izole bir yerel Gemini istemcisi** olarak çalışır. `PinealAnalyzerEngine.kt` ve `ForensicReconEngine.kt`, Python sunucusundaki 12 ajanlı boru hattını veya OSINT araçlarını çağırmak yerine doğrudan cihaz üzerinden Google'ın `generativelanguage.googleapis.com/v1beta/models/gemini-3.1-pro-preview:generateContent` ucuna (`GeminiClient.kt:19`) bağlanır. Yalnızca `AspasiaChatEngine.kt` sohbet sırasında önce `POST /api/mobile/coach` ucunu dener, hata alırsa yine yerel Gemini çağrısına düşer.

#### [A-01] `PinealBackendClient.kt` İçinde Sabit Emülatör IP'si (`10.0.2.2:8000`) ve Kimlik Doğrulama Başlığı (`X-API-Key`) Eksikliği
- **Dosya Yolu ve Satır Numarası:**
  - `android/app/src/main/java/com/example/pineal/engine/backend/PinealBackendClient.kt` — Satır `26-30` ve `86-93`
- **Önem Derecesi:** **P1 (Yüksek — Gerçek Cihazlarda ve Korumalı Backend'de Bağlantının %100 Başarısız Olması)**
- **Kanıt:**
  ```kotlin
  // android/app/src/main/java/com/example/pineal/engine/backend/PinealBackendClient.kt:86-88
  class PinealBackendClient(
      val baseUrl: String = "http://10.0.2.2:8000/"
  )
  ```
  1. `10.0.2.2` yalnızca Android Emülatör içinden ana bilgisayarın `localhost` adresine erişmek için geçerlidir; gerçek bir Android telefonda bu adres hiçbir yere ulaşamaz ve uygulama ayarlarında Backend URL'sini değiştirecek bir alan yoktur.
  2. `PinealBackendApi.getCoachReply` (`26-30`) hiçbir `X-API-Key` veya `Authorization: Bearer` başlığı göndermez; backend'de `PINEAL_API_TOKEN` aktif olduğunda tüm mobil istekler `401 Unauthorized` ile reddedilir.
  3. `network_security_config.xml` yalnızca `10.0.2.2` ve `localhost` için şifresiz HTTP (`cleartextTrafficPermitted="true"`) izni verir.
- **Düzeltme Talimatı:**
  Android ayar ekranına yapılandırılabilir `backendBaseUrl` ve `backendApiToken` alanları ekleyin; `PinealBackendApi` arayüzüne `@Header("X-API-Key") apiToken: String?` parametresini dahil edin.

#### [A-02] `PinealViewModel.kt` İçinde Aspasia Sohbetinde Görsel (`imageBitmap = null`) Gönderiminin Devre Dışı Bırakılmış Olması
- **Dosya Yolu ve Satır Numarası:**
  - `android/app/src/main/java/com/example/pineal/ui/PinealViewModel.kt` — Satır `353-361`
- **Önem Derecesi:** **P1 (Yüksek — Arayüzde Seçilen Görselin Hiçbir Zaman İşlenmemesi)**
- **Kanıt:**
  Kullanıcı Aspasia sohbetinde galeriden bir görsel seçebilmesine (`selectedChatImageUri`) rağmen, `sendMessage()` fonksiyonu `aspasiaEngine.generateResponse(...)` çağrısında `imageBitmap = null` sabit değerini gönderir:
  ```kotlin
  // android/app/src/main/java/com/example/pineal/ui/PinealViewModel.kt:353-361
  val reply = aspasiaEngine.generateResponse(
      userMessage = text,
      currentProfile = state.holisticProfile,
      liveHypotheses = reconEngine.liveReconState.value,
      hasImage = image != null,
      imageBitmap = null, // simplified for now due to context issues
      language = state.language,
      apiKey = state.apiKey
  )
  ```
  Sonuç olarak `AspasiaChatEngine.kt:129` içindeki `if (hasImage && imageBitmap != null)` koşulu hiçbir zaman sağlanmaz ve görsel ne backend'e ne de Gemini API'sine gönderilir.
- **Düzeltme Talimatı:**
  `PinealViewModel` (`AndroidViewModel` veya içerik çözücü kullanarak) ya da `ChatScreen` içinde `selectedChatImageUri` değerini `Bitmap` nesnesine dönüştürüp `imageBitmap` parametresine gerçek `Bitmap` olarak iletin.

#### [A-03] `TargetInputCard.kt` ve `PinealUiState` İçindeki OSINT ve Model Ayarlarının Analiz Motorunda Hiç Kullanılmaması (Ölü Kontroller)
- **Dosya Yolu ve Satır Numarası:**
  - `android/app/src/main/java/com/example/pineal/ui/components/TargetInputCard.kt` — Satır `31` ve `104-123` (`useDeepExtraction` / `"DEEP_OSINT_EXTRACTION"`)
  - `android/app/src/main/java/com/example/pineal/ui/PinealViewModel.kt` — Satır `44-49` ve `282-304` (`osintApiKey`, `cookie`, `selectedModel`, `useCloudApi`)
- **Önem Derecesi:** **P2 (Orta — İşlevsiz Ayar ve Arayüz Kontrolleri)**
- **Kanıt:**
  1. `TargetInputCard.kt:104-123` içindeki `"DEEP_OSINT_EXTRACTION"` anahtarı yalnızca yerel `var useDeepExtraction by remember { mutableStateOf(false) }` değişkenini değiştirir; ne `ViewModel`'e ne de analiz motoruna aktarılır.
  2. `SettingsDialog.kt` içinde kullanıcıdan alınan `osintApiKey`, `cookie`, `selectedModel` ve `useCloudApi` değerleri `PinealUiState` içinde saklanır ancak `PinealAnalyzerEngine.executeAnalysisPipeline` veya `ForensicReconEngine` tarafından **hiçbir yerde okunmaz**.
  3. `PinealAnalyzerEngine.kt:155` içindeki `evolveProfile()` metodu ve `ui/components/ReconRadarCard.kt` bileşeni uygulama genelinde hiçbir yerden çağrılmayan ölü kodlardır.
- **Düzeltme Talimatı:**
  Ayarlar ekranındaki `selectedModel`, `osintApiKey`, `cookie` ve `useDeepExtraction` parametrelerini `executeAnalysisPipeline` çağrısına bağlayın veya kullanılmayan sahte kontrolleri arayüzden kaldırın.
