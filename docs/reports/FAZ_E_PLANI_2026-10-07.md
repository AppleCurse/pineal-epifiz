# PINEAL EPİFİZ — FAZ E PLANI (ÖNERİ)
## "MÜHÜR & KAPI" — Sertleştirme Fazı

**Tarih:** 2026-10-07
**Dayanak:** `main` @ `162d7ec` (FAZ D tamam · PR #112 birleşti)
**Durum:** **ÖNERİ** — onay bekliyor. Bu belge bir hüküm değil, kanıta dayalı bir tekliftir.
**Güncelleme:** 2026-10-07 akşam — **E1 kapandı** (PR #113 ile, `main`'e birleşmedi). Ayrıntı: aşağıdaki "Durum Güncellemesi" bölümü.

---

## ⟳ DURUM GÜNCELLEMESİ — 2026-10-07 akşam

Bu bölüm **CI kanıtı + bağımsız kaynak denetimi** ile yazıldı. Aşağıdaki plan metni tarihsel kayıt olarak korundu; ölçüm anı `main` @ `162d7ec` idi ve hâlâ öyle.

### E1 — KAPANDI ✅ (PR #113 ile)

Planın açılış sorusu — *"E1 Rust onarımı bu fazda mı, ayrı bir vault PR'ı olarak mı yürüsün?"* — **fiilen cevaplandı: ayrı bir PR olarak yürüdü** ve onarıldı.

- **Künye:** PR **#113** · dal `arena/51add43a-pineal-epifiz` · head `1518017d` (4 commit) · 16 dosya · durum **AÇIK**, `main`'e göre `BEHIND`, **7/7 kontrol yeşil**.
- **rust-core adım kanıtı** (run `37562185866` · job `112601776418`): adım 5 "Cargo check (core, no tauri feature)" → **success** · adım 6 "Cargo test" → **success** — yani yalnız derlenmiyor, `#[ignore]`'lı test **gerçekten koşuyor**.
- **Bağımsız kaynak denetimi** (`rust_core/src/vault.rs` @ `1518017d`): `#[ignore]` özniteliği **yok** (yalnız yorumlarda, satır 10 ve 586); `cfg!(test)` / erken `return` / `should_panic` gibi kaçış yolu **yok**; `writer.finish()` üç yerde (345, 400, 550). Roundtrip testinin gövdesi hile değil: oluştur → `store` → kapsamdan çık → diskten `load` → `retrieve` → `assert_eq!`.
- **Süreç kanıtı (dürüstlük notu):** ilk CI denemesi kırmızı yandı — `E0277`: `StealthVault` `Debug` türetmiyor, çünkü `unwrap_err()` `T: Debug` ister ve `age::x25519::Identity` `Debug` türetmez. Onarım: elle yazılmış, sır **sızdırmayan** `Debug` impl'i (`master_key` · `identity` · `password_hash` → `[REDACTED]`). Yalnız `--all-targets` ile görünen bir trait-bound hatasıydı; "sandbox'ta derleme yok" riskinin gerçek olduğunu ve CI'ın yakaladığını gösterir.

### Kasa egress kapısı — plana girmeyen, ölçülmemiş bir yara kapandı

Bu plan hazırlanırken ölçülmemişti; #113 ile kapandı: **kasa kilitliyken dış-çıkış**.

- 15 dış-çıkış ucu `_require_vault_open` → **423 `VAULT_LOCKED`** ile sert reddediliyor; 5 muafiyet (örn. `/api/browser/close` — açık kanalı *kapatır*, zombi Chromium bırakmasın) gerekçesiyle adıyla yazılı.
- `SearchEngine` kilitliyken **hiç `httpx` istemcisi kurmuyor** (`status="VAULT_LOCKED"`, `available=False`) — DuckDuckGo dâhil. Öncesinde yalnız SearXNG omurga yolu kapılıydı, ücretsiz yollar açıktı.
- Kapı, route tablosuna karşı koşan **yapısal testle** makine denetiminde: yeni bir dış-çıkış ucu eklenip listeye yazılmamak mümkün değil.

### FAZ E tablosunun bugünkü hâli

| Kalem | Durum | Kim çalışıyor |
|---|---|---|
| **E0** regresyon paketi (şemsiye) | Açık | — |
| **E1** vault truncate + `#[ignore]` kaldırma | **Kapandı** (#113, birleşme bekliyor) | paralel oturum |
| **E2** MinorGate API sınırı | **Açık** 🔴 | — |
| **E3** omurga tek yol (8 `httpx` dosyası) | Açık 🟡 | — |
| **E4** fail-closed worker | **Çalışılıyor** | paralel oturum (talep 3) |
| **E5** motor yoksa `400` | Açık 🟡 | — |
| **E6** UI "Yetersiz Kanıt" | Açık 🟡 | — |
| **E7** `gather` koruması | Açık 🟡 | — |
| **E8** Pydantic (169 → 10-15) | Açık 🟢 | — |

**Sıra notu (çakışma uyarısı):** E4 şu an paralel oturumun elinde ve E3/E7 ile **aynı dosyalara** dokunuyor. #113 `backend/api.py`'yi ağır biçimde değiştirdiği için **E2 de aynı dosyada** yaşar → E2 · E3 · E7'yi #113 birleşmeden başlatmak çakışma üretir.

### DOĞRULANAMAYANLAR (güncel)

Yerel `cargo`/`rustc` bu ortamda **yok**; tüm Rust aynaları ağdan erişilemez (`static.rust-lang.org` · `crates.io` · `rsproxy` → bağlantı yok). **Actions logları da erişilemez** — Azure blob TLS-engelli, açık olan tek uç `api.github.com`. Bu yüzden Rust doğrulaması (a) pinli crate kaynaklarına karşı satır satır okuma (age `v0.10.1` · secrecy `v0.8.0`), (b) CI adım sonuçları ve (c) `api.github.com`'dan okunabilen workflow annotation'ları ile yapıldı. **Annotation ile okunabilirlik bu sayede kalıcılaştırıldı:** #113'te `cargo check`/`cargo test` çıktısı artık annotation olarak da yayınlanıyor; düşen bir Rust koşusunun hatası log indirmeden okunabiliyor.

---

## 0 · Önce soru: "FAZ E nedir?"

**Kısa cevap: repoda tanımlı değil.** Bu boşluk ölçülerek doğrulandı:

- Harf programı **A → B → C → D** olarak `docs/reports/TEKLIF_TAM_GUC_2026-10-05.md` §7'de tanımlandı ve **D ile bitti** (PR #112, `main` @ `162d7ec`).
- `'FAZ E'` için tüm repoda arama: **0 sonuç** (`grep -rniE 'faz[ _-]?e\b'`).
- Yıldız Depo karar ağacının **sayısal** yol haritası (Faz 0–9) farklı bir eksendir — ve FAZ D, o listeden kalemleri **öne aldı**: D1 MCP = sayısal Faz 7 · D2 yerel jüri = Faz 8 · D3 medya adli = Faz 3 · D5 rapor fabrikası = Faz 9 (`YILDIZ_DEPO_KARAR_AGACI_2026-10-05.md:347, 389, 407, 424, 435, 479`).

Yani E'yi hazır bulamayız; **tanımlanması** gerekir. Bu belge, kodun bugünkü durumundan çıkarılmış bir tanım öneriyor.

---

## 1 · Neden "sertleştirme" fazı? (kanıtlı gerekçe)

K0 felsefe kapısı 4 dokunulmaz ilkeye dayanır: **(1)** LLM falcı değildir · **(2)** Kanıt mührü fail-closed · **(3)** %100 şeffaf, sıfır sahte simülasyon · **(4)** Kasa (vault) mandalı.

**FAZ A–D yetenek GENİŞLİĞİNİ kapattı** (okuma → hafıza → ses → ihracat). Buna karşılık 2026-10-06 Tam Denetimi (PR #110 · `JULES_DENETIM_2026-10-06.md`), en ağır 10 eleştirisini tam da bu 4 ilkenin üstüne koydu. Bugün (`main` @ `162d7ec`) yapılan **kod okumasıyla** bu maddelerin hâlâ açık olduğu doğrulandı:

| # | Denetim maddesi | Bugünkü durum | Kanıt (`main` @ `162d7ec`) |
|---|---|---|---|
| **E-GÖZ3-1** | Vault kalıcılık bug'ı `#[ignore]` ile gizlenmiş | **AÇIK** 🔴 | `rust_core/src/vault.rs:281` → `#[ignore = "VAULT_PERSISTENCE_BUG: age file truncated on store->reload (CI 2026-08-26)"]` |
| **E-GÖZ2-8** | Çocuk kırmızı çizgisi API sınırında zorlanmıyor | **AÇIK** 🔴 | `grep -c 'minor_gate' backend/api.py` → **0**. Kapı yalnız omurga içinde: `agent_core/capabilities/runner.py:80-82` |
| **E-GÖZ1-1 / 2-1** | Worker fail-open (sessiz in-memory fallback) | **AÇIK** 🟡 | `agent_core/workers/agent_worker.py:28-40` → ImportError/Redis hatası yutulup `logger.warning` + fallback |
| **E-GÖZ1-3** | Omurga bypass: doğrudan `httpx` | **AÇIK** 🟡 | 8 dosya: `services/search_engine.py:4` · `services/vision_analyzer.py:5` · `services/socid_enricher.py:15` · `agents/human_behavior.py:16` · `services/media_forensics.py:36` · `capabilities/adapters_sensors.py:28` · `services/llm_gateway.py:15` · `utils/security.py:18` |
| **E-GÖZ3-4** | UI tiyatrosu ("dolu görünen boş") | **AÇIK** 🟡 | `frontend/src/components/AtlasPinealCockpit.svelte:973,979` → `\|\| 'Veri mevcut değil'`; `'Yetersiz Kanıt'` → frontend'de **0 hit** |
| **E-GÖZ1-2** | Korumaşız paralel işlem | **AÇIK** 🟡 | 11 `asyncio.gather` çağrısı; korumasız **8 dosya**: `human_behavior` · `pillar_orchestrator` · `holehe_scanner` · `routed_chat` · `socid_enricher` · `vision_analyzer` · `local_jury` · `task_executor` |
| **E-GÖZ1-5** | Tip güvenliği zayıf | **AÇIK (kısmi)** 🟢 | `Dict[str, Any]`: `agent_core/` **169** · `backend/api.py` **1** (asimetri: omurga yolu geride) |

**Denetimden sonra düzeltilmiş görünenler (doğrulanacak):**

- **E-GÖZ2-2 `/v1/models`:** Gerçek uygulama var (`backend/api.py:1318` — `routed.executable_models(gateway)`) + e2e testi (`tests/e2e/test_openai_compatibility.py:375`). Denetimin "`[]` döner" iddiası **bayat** görünüyor → E0 ile kanıtlanıp kapatılır.
- **E-GÖZ2-3 Kasa bypass (kısmen):** `_check_vault_interlock` (`backend/api.py:3263`) **11+ uçta** kullanılıyor; `PolicyKernel` vault kapısı fail-closed (`capabilities/policy.py:94-95` → `policy:vault_locked`). **Ama:** scraper'ın *kendisi* kapı taşımıyor (`grep -rn 'vault' agent_core/scraper/` → yalnız cookie kullanımı). Kapı **yalnız omurgadan geçen yolda** var → **omurgayı atlayan yol = kapı yok.** (E3'ün gerekçesi budur.)

**Hüküm:** Yeni yetenek eklemenin önündeki tek ciddi engel, deponun kendi doktrini ile kodu arasındaki bu farktır. FAZ D "yetenek" fazıydı; **FAZ E "garanti" fazı** olmalı: 4 dokunulmaz ilkeyi sözden koda çevirmek.

> **Fazın adı: FAZ E — MÜHÜR & KAPI (Sertleştirme).**

---

## 2 · Kapsam

**Amaç:** K0'ın 4 ilkesini istisnasız makine-zorlamalı hale getirmek; denetimin KRİTİK/YÜKSEK maddelerini kapatmak; **her kapanışı sözleşme testiyle mühürlemek.**

**Kapsam dışı:** Yeni yetenek (→ FAZ F), model eğitimi, UI tasarım yenilemesi, `android/` · `functions/` · `worker.ts`.

**Yöntem kilidi (bu faza özgü kural):** Her madde üç parçadan oluşur —
**(a)** kod düzeltmesi, **(b)** onu bir daha kaçmayacak şekilde kilitleyen **contract testi**, **(c)** CHANGELOG kaydı.
Depo bu kültüre sahip (`tests/unit/test_ui_honesty_contract.py`, `tests/unit/test_capability_spine_faz0.py`); FAZ E bunu **istisnasız standarda** çevirir. Testsiz kapanan madde, kapanmamış sayılır.

---

## 3 · İş kalemleri

### E0 · Denetim regresyon paketi (şemsiye) 🟠
- **Ne:** `JULES_DENETIM_2026-10-06.md` içindeki tüm `DOĞRULA` komutlarını tek koşuda çalıştıran `scripts/audit_regression.sh` + CI adımı. Bilinen-açık listesi boşalana dek daralır.
- **Neden:** Denetim bulguları sessizce geri gelmesin; "/v1/models" gibi bayat iddialar bu paketle kesinleşir.
- **DoD:** CI'da koşar; çıktı `reports/` altına JSON olarak yazılır; her FAZ E maddesi bir satırını "AÇIK → KAPALI" gösterir.

### E1 · Kasa mührü: vault kalıcılık bug'ı 🔴 KRİTİK
- **Ne:** `rust_core` — age yazma/okuma döngüsündeki truncate bug'ı onarılır; `vault.rs:281`'deki `#[ignore]` **kaldırılır**; roundtrip testi aktive edilir.
- **Neden:** Kasanın kendisi veri kaybediyorsa Md.4 bir yanılsamadır. Denetimin **1 numaralı** maddesi; tek "gerçek bug" (diğerleri disiplin/borç).
- **DoD:** `cargo test --manifest-path rust_core/Cargo.toml` → **0 ignored** · `test_vault_roundtrip_store_reload_retrieve` **PASS** · aynı senaryo farklı boyutlarda (boş/tek anahtar/çok anahtar) test edilir.
- **Kanıt komutu:** `cargo test 2>&1 | grep -c ignored` → `0`
- **Boyut:** büyük (denetim tahmini: hafta) · **Dil:** Rust · **Bağımlılık:** yok → **ilk başlar.**

### E2 · Çocuk kırmızı çizgisini API sınırına taşı 🔴 KRİTİK
- **Ne:** `backend/api.py` — hedefe yönelik **tüm** uçlara (ör. `/api/tasks`, `/api/experimental/socid/extract`, OSINT ailesi) `MinorGate` zorlaması: middleware veya FastAPI dependency. Kapı **yeniden yazılmaz**; `agent_core/safety/minor_gate.py` + `MinorCaseLedger` **tek kaynak** olarak çağrılır (runner.py:80-82 emsali).
- **Neden:** Tüzük Md.5. Bugün API'den doğrudan hedef sorgulanabiliyor; kapı yalnız omurga derinliğinde.
- **DoD:** (a) `grep -c 'minor_gate\|MinorGate' backend/api.py` **> 0**; (b) contract testi: reşit olmayan işaretli hedef → **403 + ledger kaydı**, onaylı/yetişkin → geçer; (c) omurga dışı hiçbir hedef ucu kapısız kalmaz.
- **Boyut:** orta (gün) · **Bağımlılık:** yok.

### E3 · Omurga tek yol (spine-only) 🟡 YÜKSEK
- **Ne:** §1'de listelenen 8 dosyadaki doğrudan `httpx` kullanımı `run_capability` yoluna taşınır (ya da policy kontrolünden geçirilir). Sıra: önce `search_engine` (denetimin işaret ettiği), sonra sıcak yollar; `adapters_*` ve `llm_gateway` için **gerekçeli izin listesi** kararı ayrıca yazılır.
- **Neden:** `PolicyKernel` vault/bütçe/rate kilitleri (**fail-closed**) ancak omurgadan geçen yolda çalışıyor. Bugün delinebiliyor → Md.4 + bütçe güvencesi kırılgan.
- **DoD:** (a) yeni **saf-durum contract testi**: izin listesi dışında `httpx.AsyncClient` çağrısı **yok**; (b) kasa kilitliyken bu servislere ulaşan her yol `policy:vault_locked` döner; (c) hiçbir davranış regresyonu (mevcut testler yeşil).
- **Boyut:** orta-büyük (birkaç gün) — **dilim dilim ilerle, dilim başına ayrı PR.**

### E4 · Fail-closed worker 🟡 YÜKSEK
- **Ne:** `agent_core/workers/agent_worker.py:28-40` — sessiz in-memory fallback **kaldırılır**. Redis yoksa: (a) yüksek sesli log, (b) UI/telemetriye `degraded` durumu, (c) "çalışıyorum" sinyali **verilmez**.
- **Neden:** Kullanıcı iş yapıldığını sanıyor; iş yapılmıyor → Md.3 şeffaflık ihlali, sessiz veri kaybı.
- **DoD:** Contract testi: Redis'e bağlanamayan worker açık `degraded`/hata yolu döner; kodda `"in-memory fallback"` dizesi **kalmaz**.
- **Boyut:** küçük-orta (saat).

### E5 · Experimental uçlar: motor yoksa 400 🟡 YÜKSEK
- **Ne:** `backend/api.py:3310` (maigret) ve `:3330` (holehe) başta olmak üzere deneysel uçlar — motor/bağımlılık yoksa **200 değil 400 `motor_unavailable`**. Mevcut dürüst `available:false` sözleşmesi korunur; üstüne **HTTP seviyesi** eklenir.
- **Neden:** Md.1 uydurma yasağı; "boş süreç başlıyor" görüntüsü kalkar. (Not: docstring bugün dürüstlük iddia ediyor → **önce ölç**, sonra sıkılaştır; docstring'e güvenilmez.)
- **DoD:** Motor kapalıyken 3 deneysel uç → **400 + makine-okunur sebep**; contract testi yazılır.
- **Boyut:** küçük (saat).

### E6 · UI dürüstlüğü: "Yetersiz Kanıt" 🟡 ORTA
- **Ne:** `AtlasPinealCockpit.svelte:973,979` başta olmak üzere `|| 'Veri mevcut değil'` kalıpları **state bazlı "Yetersiz Kanıt"** uyarısına çevrilir; `tests/unit/test_ui_honesty_contract.py` bu bileşeni de kapsayacak şekilde genişletilir.
- **Neden:** Md.3. Boş veri, bugün "dolu" gibi görünüyor.
- **DoD:** `grep -rn "'Veri mevcut değil'" frontend/src` → **0**; yeni contract testi AtlasPinealCockpit'i kilitler; boş veri → kırmızı/uyarı durumu.
- **Boyut:** küçük (saat).

### E7 · `gather` = `return_exceptions` 🟡 ORTA
- **Ne:** 8 korumasız dosyada `asyncio.gather` çağrılarına `return_exceptions=True` + **kısmi sonuç raporlama**: tek ajan hatası tüm analizi düşürmez; düşen parça dürüstçe "alınamadı" olarak raporlanır (sessizce yutulmaz).
- **Neden:** Bugün tek hata bütün analizi çökertebiliyor (fail-open'un tersi: fail-crash).
- **DoD:** `grep -rn 'asyncio.gather' agent_core/ backend/` → her çağrı ya `return_exceptions` ya gerekçeli `# noqa: ...` taşır.
- **Boyut:** küçük-orta.

### E8 · Tip güvenliği (kademeli) 🟢 DÜŞÜK-ORTA
- **Ne:** `Dict[str, Any]` → Pydantic modelleri (`agent_core/` 169 yer). **İlk dilim:** API'ye en yakın 10-15 nokta (runtime `KeyError` riski en yüksek olanlar). Kalanı için görev listesi bu belgenin ekinde tutulur.
- **Neden:** `KeyError` operasyon anında patlıyor; şema doğrulaması yok.
- **DoD:** İlk dilim için hatalı payload senaryoları test edilir; `agent_core` sayısı ölçülür ve düşüş CHANGELOG'a yazılır.
- **Boyut:** büyük (kademeli, faz boyunca).

---

## 4 · Faz kabul kapıları (hepsi birden)

1. `cargo test --manifest-path rust_core/Cargo.toml` → **0 ignored**, vault roundtrip **PASS**.
2. `pytest --cov-fail-under=80` yeşil (denetim tabanı: **1781 passed / 2 skipped / %85.88**).
3. Yeni contract testleri: **minor gate · spine-only · worker fail-closed · UI dürüstlük**.
4. **Kasa kilitli + internet yokken:** hiçbir uç dışarı çıkmaz (`policy:vault_locked`), hiçbir uç "başarılı" görünmez, hiçbir sayı uydurulmaz.
5. E0 regresyon paketi: denetimin KRİTİK+YÜKSEK satırları **KAPALI**.
6. CHANGELOG + ilgili `docs/` güncel; `docs/reports/FAZ_E_KAPANIS_*.md` yazılı.

---

## 5 · Sıra ve bağımlılıklar

```
E1 (Rust, bağımsız, en uzun)  ──────────────► ilk başlar, paralel yürür
E0 (şemsiye, ilk gün kurulur) ──────────────► CI'ya girer, faz boyunca daralır
E2 ─┐
E6 ─┴─ (safety + UI, bağımsız)     ─────────► hızlı kazanımlar
E4 ─┐
E5 ─┴─ (fail-closed ailesi)        ─────────► E0 ile aynı dilim
E3 (en geniş dokunuş)              ─────────► izin listesi netleşince, dilim dilim
E7 · E8 (kademeli temizlik)        ─────────► faz boyunca arka planda
```

Her madde **ayrı PR**; her PR'da CI yeşil + contract testi zorunlu (depo kuralı).

---

## 6 · Riskler ve önlemler

| Risk | Önlem |
|---|---|
| E3 çok geniş dokunur, regresyon üretir | Alt sistem başına dilim; her dilim kendi PR'ı + kendi contract testi |
| E1 Rust tarafında derinlik bilinmiyor | İlk iş **minimal repro**: hatayı yeniden üreten en küçük test; sonra onarım |
| E2 yanlış pozitif (meşru yetişkin hedefi bloklar) | `MinorCaseLedger` zaten gerekçe kodu + kayıt tutuyor; testte **iki yön** kanıtlanır (red + izin) |
| E5/E4 "dürüst 400" mevcut UX'i bozar | Hata gövdesi makine-okunur (`motor_unavailable`, `degraded`) + UI'da açık mesaj |
| Kapsam kayması (yeni özellik cazibesi) | Bu fazda **yeni yetenek yok**; yeni fikirler FAZ F listesine yazılır |

---

## 7 · Ufuk: FAZ E'den sonra ne var?

**FAZ F — Kalan yaralar (yetenek fazı).** Bugün ölçülen boşluklar:
- **Y1** Tersine görsel arama — **0 hit** (`reverse_search|google_lens`); D3'ün pHash/EXIF zemini var, arama yok.
- **Y3** Hedef tekrarı/ısrar takibi — **0 hit** (`repeat_target`).
- **Y4** Sosyal graf (yorum yazarları, ortak takipçi, ilişki kenarları) — **0 hit** (`social_graph|co_follower`).
- **Y9** Kalıcı zaman serisi deposu (DuckDB) — **0 hit**; kalibrasyon (`threshold_calibration.py`) tarihçesiz.
- *(Y2 → E2'de kapanır · Y6/Y7/Y8/Y10 → A–D'de kapandı/kısmen kapandı.)*

**FAZ G — Erişilebilirlik & dağıtım (T-kalemleri).** Görme engelli operatör için sesli rapor (MOSS-TTS sınıfı, hedef sesi taklit edilmeden), masaüstü paketleme (Pake/Tauri kararı), TR/EN i18n + imzalı dışa aktarım.

---

## 8 · Dürüstlük bölümleri (depo geleneği)

**ÖLÇÜM ÖNCESİ:** `main` @ `162d7ec` · FAZ D birleşik · denetim tabanı (2026-10-06): 1781 passed, 2 skipped, %85.88 coverage · CI kapısı `--cov-fail-under=80`.

**DOĞRULANAMAYANLAR:** Bu plan hazırlanırken sandbox ortamında Python bağımlılıkları kurulu değildi (`fastapi` yok) → **testler koşulmadı**; tüm sayımlar `grep` + doğrudan kod okumasıyla yapıldı. `/v1/models` düzeltmesi "e2e testi mevcut" gerekçesiyle *muhtemelen kapalı* sayıldı — **kanıtı E0 getirir**. `cargo` da bu ortamda koşulmadı; E1'in DoD'si ilk ölçümle netleşir.

**BAKILMAYANLAR:** `android/` · `functions/` · `worker.ts` · UI görsel stilleri (CSS) — denetimin kapsam notuyla aynı çizgide bu planın da dışında.

**DUR ve SOR:** (1) E1 Rust onarımı bu fazda mı, ayrı bir "vault PR"ı olarak mı yürüsün? (2) Sıra onayı: E1+E0 paralel mi, yoksa önce hızlı kazanımlar (E2/E6/E4/E5) mı? Bu belge "E1+E0 paralel" öneriyor.

---

*Bu belge bir öneridir; onaylanmadan hiçbir kod değişikliği yapılmaz. Denetim kodu değiştirmez — düzeltmeyi uygulama fazı yapar.*
