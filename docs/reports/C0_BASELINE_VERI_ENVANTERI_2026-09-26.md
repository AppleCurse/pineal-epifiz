# C0 — Baseline veri envanteri (salt-okunur)

**Tarih:** 2026-09-26

**Durum:** C0 tamamlandı · envanter sonucu: tarihsel, hedefe bağlı baseline için kaynak kanıtı yok

**Kapsam:** Profil girdisi, zaman damgası üretimi/aktarımı, zaman serisi tüketicileri, test verileri, rapor/UI çıktıları ve kalıcılık yolları.

**Değişiklik sınırı:** Analiz motoru veya şema eklenmedi; uygulama kodu değiştirilmedi. Bu dosya incelemenin dokümantasyon çıktısıdır. Canlı profil kazıması yapılmadı.

## Sonuç

Mevcut depo ve incelenen üretim akışları, bir hedefin geçmiş görevler arasında korunmuş, kaynağı doğrulanabilir zaman serisini **göstermiyor**. Standart Instagram yolu bir görev sırasında mevcut profilden en fazla 12 postluk örnek alıyor; P7 zaman motorları bu göreve verilen örnek üzerinde hesap yapıyor. Raporlar ve kanıt öğeleri görev bazında saklanabiliyor, ancak hedef kimliğine göre birleştirilmiş kaynak-post arşivi veya tekrar kullanılabilir kişisel referans dönemi yok.

Bu nedenle şu an desteklenebilen ifade, varsa, **“incelenen örneklemde gözlenen değişim/aralık”** olabilir. “Kişinin normalinden sapma” veya psikolojik/yaşamsal neden iddiası desteklenmiyor. Özellikle `SILENCE_GAP`, tarihli gönderiler arasındaki paylaşım boşluğudur; olay nedeni değildir.

## 1. Kaynak ve giriş envanteri

| Yol | Gerçekte gelen veri | Baseline açısından sınırlama |
|---|---|---|
| `/api/initiate` → `platform_registry.scrape_instagram` | İstek gövdesi URL ve kullanıcı alanlarını alır; gönderi corpus’u yüklemez. Instagram profili canlı kazınır ve görev payload’ına eklenir. | Her görevdeki anlık örnek dışında bir tarihsel kaynak/denominator sağlamaz. |
| `scripts/run_task.py` → aynı registry | URL varsa aynı Instagram kazıma ve `target_profile` eşlemesi kullanılır. | Ayrı bir corpus deposu veya tarihsel birleştirme adımı yoktur. |
| Cross-platform/public-OSINT dalı (`backend/api.py`) | Arama snippet’leri `posts` alanına konabilir; `post_times` ve `posts_meta` boş bırakılır. Arama sonucu yoksa üretilmiş dossier/placeholder metinleri de atanabilir. | Bunlar timestamp’li gönderi serisi değildir; placeholder metinler gerçek kaynak postu sayılamaz. `extract_post_series` bunlardan zaman serisi çıkarmaz. |
| Doğrudan `PinealExecutor.execute_task` çağrısı | `target_profile` genel bir `dict` olarak alınır; burada kaynak türünü ve paralel listelerin hizasını zorunlu kılan bir giriş modeli yoktur. | Çağıran taraf sentetik veya farklı kaynaklı veri sağlayabilir. Kaynak doğruluğu yalnız bu sözleşmeden çıkarılamaz. |
| Testler ve rapor dosyaları | Zaman serisi testleri Python içinde oluşturulmuş metin, tarih ve etkileşim sayıları kullanır. Depodaki `reports/9router_preflight_latest.json` router ön kontrol çıktısıdır. | Test/rapor çıktıları gerçek hedef corpus’u değildir. İncelenen çalışma ağacında kazınmış profil geçmişi veya profil corpus’u dosyası bulunmadı. |

### Instagram kaynağının gerçek kapsamı

- `InstagramPost` modelinde kaynak shortcode, opsiyonel `taken_at`, caption ve opsiyonel like/comment sayıları bulunur. `InstagramProfile.posts` doğrulayıcısı post listesini **12 ile sınırlar**.
- Scraper, tarihli postları artan zamana sıralar; tarihsizler sona alınır. Bir gönderinin tarihi yoksa uydurulmaz.
- Instagram profili eşlemesi `posts`, `post_times` ve `posts_meta` listelerini aynı sırada taşır. Gerçek `post_times`, post modelindeki `taken_at` alanından gelir; bilinmeyen tarih boş string olarak kalır.
- Parser’daki post ayrıntısı yolu, bazı eksik tarihleri sayfa JSON-LD/meta alanlarındaki `uploadDate` / `datePublished` / `dateCreated` veya `article:published_time` değerlerinden de doldurabilir. Bunlar tek `taken_at` alanına indirgeniyor; downstream payload’da hangi timestamp çıkarım yolunun kullanıldığına ilişkin alan başına provenance taşınmıyor.
- Eşleme `shortcode`, profil `post_count`, `scraped_at`, `evidence_source` ve `platform` alanlarını `target_profile`’a aktarmıyor. Dolayısıyla kaynağın verebildiği toplam post sayısı örneklem denominator’ı olarak kullanılamıyor; post düzeyinde kaynak ID’si de zaman motorlarına ulaşmıyor.
- Üretim yönlendiricisi platformu Instagram olarak biliyor; ancak eşlenmiş profilde `platform` bulunmadığı için `_profile_scope` platformu `unknown`, Frequency raporu ise varsayılan `primary` olarak görebiliyor. Bu, kaynak sınıfı ile rapor provenance’ı arasında mevcut bir aktarım boşluğudur.

## 2. Mevcut zaman serileri: ölçüm var, tarihsel baseline yok

| Tüketici | Kullanılan seri ve mevcut referans | Ne değildir? |
|---|---|---|
| `FrequencyEngine` | Paylaşılan `extract_post_series`’ten tarihli kayıtları alır; en erken kaydın saatine yuvarlanmış başlangıçtan son kayda kadar 24 saatlik kovalar üretir. Ortalama/standart sapma ve z-skorları aynı görev örnekleminden hesaplanır. | Başlangıçtan önceki dönem için sıfır kovası veya geçmiş görevlerden saklanan normal dönem yoktur; hesaplanan normlar örneklem-içidir. |
| `SeismosEngine` | En az 5 tarihli kayıtla ardışık post aralıklarını hesaplar. `baseline_inter_post_hours`, **aynı girdideki** aralıkların medyanıdır. Varsayılan sessizlik eşiği `max(72 saat, 4 × bu medyan)` olur. | Ayrı ve kalıcı kişisel baseline değildir. `SILENCE_GAP` yalnız timestamp’li postlar arasındaki boşluğu işaretler; nedenini doğrulamaz. |
| `StrataEngine` | En az 12 tarihli kayıt ister; serinin ilk ve son üçte birlik post gruplarındaki bazı metin/etkileşim ölçülerini karşılaştırır. Tarih aralığı ve toplam örneklem derinliği raporlanır. Scraper üst sınırı olan 12 tarihli postun hepsi varsa, ilk 4 ile son 4 karşılaştırılır; ortadaki 4 bu karşılaştırmaya girmez. | Sabit süreli, geçmişten saklanmış referans dönem değildir. Karşılaştırma eşit sayıda post içerir; grupların takvim süresi eşit olmak zorunda değildir. Scraper’ın 12-post sınırı nedeniyle üretimde çalışması için örneklemin tamamının tarihli olması gerekir. |
| `timing_forensics` | Mevcut `post_times` üzerinden saat dağılımı, ilk/ikinci yarı medyan farkı ve bir trajectory üretir. `TaskStatus`/WS sonucu olarak raporlanır. | Hedefe bağlı, sonraki görevlere taşınan zaman referansı değildir. |
| `HumanBehaviorAnalyzer._temporal_forensics` | Saat metninin başındaki parçayı tamsayıya çevirmeye çalışır; eşik aşılırsa `insomnia_isolation` adlı mikro-sinyal üretebilir. | Baseline değildir. Gerçek Instagram eşlemesi ISO tarih-saat verdiğinden, bu parser ISO girdide tarihli prefix’i tamsayıya çeviremez ve temporal sinyali atlar. Saat biçiminde başka bir girdi sinyal üretse bile bu, psikolojik/sağlık bulgusu kanıtı sayılmaz. |

`pillar_evidence_adapter`, Seismos olayını `observation` olarak `event only; cause unknown` kapsamıyla taşır; motorun olası nedenlerini ayrı, doğrulanmamış `inference` öğeleri olarak işaretler. Bu mevcut tip/kapsam ayrımıdır; **görevler arası baseline karşılaştırıcısı değildir** ve tek başına hedefin geçmişini oluşturmaz.

`FrequencyEngine.extract_post_series` timestamp önceliğini `post_times`, post nesnesindeki `created_at`/`timestamp`, sonra `posts_meta` tarih alanları olarak uygular ve geçerli tarihli kayıtları sıralar. Ancak listelerin eşit uzunlukta/hizalı olduğunu doğrulamaz; uzunlukların maksimumuna kadar indeksler ve tarih taşıyan boş/eksik post yuvalarını da seri kaydı yapabilir. Üretim Instagram eşlemesi hizayı korusa da doğrudan payload’lar için typed bir koruma yoktur.

## 3. Kapsam, kalite ve provenance sınırları

1. **Örneklem kapsamı:** Üretim Instagram yolu en fazla 12 post verir. Bu, hesabın tarihsel corpus’u değildir. Parser’da bulunan `post_count` eşlemeye taşınmadığından 12 kaydın toplam hesaba oranı hesaplanamaz.
2. **Boş caption farkı:** `extract_post_series` timestamp’i olan caption’ı boş bir postu ritim serisine dahil edebilir. `_profile_scope` ise `timestamped_post_count` ve zaman penceresini yalnızca metni boş olmayan postlardan hesaplar. Görsel içeren, caption’sız postlar varsa rapor kapsam sayısı ile motorun zaman serisi sayısı uyuşmayabilir.
3. **Etkileşimde bilinmeyen ≠ sıfır:** Instagram modelinde like/comment sayıları opsiyoneldir ve eşleme `None` değerini korur. `extract_post_series` ise `or 0` dönüşümüyle eksik sayıyı sıfıra çevirir; böylece ölçülmemiş değer ile gerçek sıfır downstream ölçümlerde ayrışmaz. Bu, engagement tabanlı karşılaştırmalar için kalite kısıtıdır.
4. **Kaynak ID’si:** Scraper’ın bildiği `shortcode` payload eşlemesinde kaybolur. Frequency/Seismos referansları zaman damgasından üretilen iç referanslardır (`post:<platform>:<timestamp>` / `post:<timestamp>`); Instagram’ın post ID’si değildir. Strata referansları da rapor/aralık düzeyindedir. Bunlar aynı postu farklı kazımalarda güvenilir biçimde eşleştirme veya deduplikasyon kanıtı oluşturmaz.
5. **Zaman semantiği:** Profil JSON’undaki post timestamp’i ile ayrıntı sayfası yayın tarihi fallback’i tek alanda birleştirilir. Alan başına yöntem/provenance görünmediği için farklı tarih semantiği taşıyan girdiler sonradan ayrıştırılamaz.
6. **Platform scope:** `target_profile.platform` gerçek Instagram eşlemesinde yoktur. Bu nedenle mevcut scope/engine provenance’ı Instagram’ı kesin ifade etmeyebilir.
7. **Bağımsız scope hesapları:** Adapter, kendi timestamp çıkarımını yapar; boş string gibi mevcut ama parse edilemeyen tarih değerinde dict/meta fallback’ine geçmez. Engine ise parse başarısızlığında fallback uygulayabilir. Ayrıca adapter yalnız `posts` üzerinden dönerken engine daha uzun paralel listeleri tüketebilir. Serbest biçimli payload’larda coverage ve zaman penceresi raporu ile engine sayımı ayrışabilir.

`pillar_evidence_adapter._profile_scope` mevcut `source_count` değerini biyografi ve boş olmayan post metni segmentleri, `post_count` değerini gelen `posts` listesinin uzunluğu olarak tanımlar. `timestamped_post_count` ve `time_window` da boş olmayan post metniyle hizalı geçerli timestamp’lerden hesaplanır; undated metnin corpus’ta kalabileceği not edilir. Bu sayı, kaynak hesabın toplam post sayısı değildir.

## 4. “Baseline” gibi görünen ama kişisel tarihsel baseline olmayan alanlar

- **Void:** `CATEGORY_LEXICON` içindeki sabit kategori öncüllerini, opsiyonel `interests` / `following_topics` ile karşılaştırır. Adapter scope’u bunun kişisel geçmiş değil engine prior’u olduğunu açıkça yazar. Corpus’ta bir temanın görünmemesi, gizli yaşam olayı veya kişisel problem kanıtı değildir.
- **Pulse:** Metin ölçülerini sabit motor referans değerleri ve sapma katsayılarıyla karşılaştırır. `baseline_volatility` aynı geçerli metin örnekleminden ölçülen değişkenliktir. Kişisel tarihsel seri değildir.
- **Gravity:** Mevcut post corpus’undaki kelime tekrarını ve sağlanan etkileşim sayımlarını toplar; tarihsel dönemler arası değişim saklamaz.
- **Key:** Diğer raporları sentezler/öneri üretir. `confidence = active / 6` etkin rapor kapsam oranıdır; kalibre edilmiş doğruluk veya corpus reliability değildir. Strateji alanları baseline kanıtı değildir.

## 5. Raporlama ve kalıcılık

- `PillarOrchestrator` her görev için gelen payload üzerinde raporları hesaplar ve `pillar-full-v1` / `computed_at` içeren bundle döndürür. `computed_at`, hesaplama zamanıdır; kaynak corpus dönemi veya baseline başlangıcı değildir.
- `TaskExecutor`, yedi raporun tam çıktısını `status.evidence_chain` içindeki görev kaydına ve kanonik evidence adapter/timeline kayıtlarına koyar. Sonunda `memory.merge_evidence(task_id, ...)` çağrılır. Bu, ölçüm/rapor kalıcılığıdır; raw post arşivi veya baseline depo sözleşmesi değildir.
- `CanonicalMemory` dosyaları `task_id` ile anahtarlanır (`<task_id>.json`). Standart API/CLI görev kimlikleri her çalıştırmada yenidir. `HindsightMemory` indeksinde de anahtar `task_id`’dir; incelenen executor akışında hedefe göre tarihsel baseline arama/karşılaştırma çağrısı yoktur.
- `target_profile` görev içinde mevcut olur ve API’nin sonuç/WS taşıma payload’ında geri dönebilir; bu tek görev sonucu tarihsel, hedefe göre doğrulanmış corpus deposu anlamına gelmez. Executor’ın kanonik bellek yazımında raw `target_profile` için ayrı bir kaynak-post arşivi bulunmadı.
- Depoda `memory/` dizini veya profil corpus’u, SQLite/DB, CSV/JSONL türünde gerçek post zaman serisi bulunmadı. `memory/*.json` ve `memory/*.db` ignore kurallarında olduğundan başka bir dağıtımda dışarıda tutuluyor olabilir; bu envanter o harici depoya eriştiğini iddia etmez.

## 6. Fixture ve rapor ayrımı

- `tests/test_pillar_engines.py::data` sabit tarihler, elle hazırlanmış metinler, etkileşim sayıları ve büyük bir yapay zaman boşluğu üretir.
- `tests/unit/test_engine_determinism.py::sample_data` benzer şekilde kod içinde tarihler/metinler oluşturur.
- `tests/unit/test_wiring_timing.py` ISO timestamp’li sentetik bir örnekle zaman forensiği kablolamasını test eder.
- Bunlar motor davranışını doğrulayan **sentetik/in-memory fixture’lardır**; canlı kullanıcı profili veya tarihsel baseline kanıtı değildir.
- Mevcut JSON raporu `reports/9router_preflight_latest.json` router preflight verisidir; profil corpus’u değildir.

## C0 kararı

**Envanter tamamlandı. Mevcut kaynaklarla kişisel/tarihsel baseline oluşturma veya “normalden sapma” iddiası için GO yok.** Tarihli postlar bulunan bir görevde, sadece o anki örneklem içi değişim ve post aralığı gözlemi raporlanabilir; baseline bulunmadığı açıkça belirtilmelidir. Timestamp yoksa zaman karşılaştırması da yapılamaz. Nedensel/psikolojik yorum ve mesaj stratejisi bu ölçümden türetilmemelidir.

### C1 kapsam ayrımı

Bu çalışma ağacında Strata'nın **aynı görevdeki ilk/son üçte bir karşılaştırmasını** `EvidenceItem`'a aktaran parça zaten vardır: `adapt_pillar_bundle()` drift'i `observation`, geç alt kümede görülmeyen fossil konusunu `absence` olarak yazar; aralıkları ve kaynak metriklerini taşır, canonical `confidence` alanını `None` bırakır. `PinealExecutor` bu öğeleri `forensic_evidence` ve nötr timeline'a bağlar. Buna ilişkin `test_strata_drift_and_fossil_keep_their_scope_and_source_scores` testi de mevcuttur (`agent_core/services/pillar_evidence_adapter.py`, `agent_core/task_executor.py:961-1009`, `tests/unit/test_pillar_evidence_adapter.py:272-283`).

Bu, görev-içi Strata çıktısının kanıt sözleşmesine aktarımıdır; **kişisel tarihsel baseline veya görevler-arası değişim izleme değildir**. Tarihsel baseline/C1 kapsamı hâlâ başlatılmadı. Bunun için önce gerçek, izinli ve saklama politikası tanımlı corpus'un; hedef/source scope'un; post düzeyi kimlik ve timestamp provenance'ının; kapsama/eksik veri paydasının mevcut olduğu gösterilmelidir. Bu kanıtlar ve P0 kararları olmadan yeni baseline motoru yazılmamalıdır.

## İncelenen temel kod yolları

- `backend/api.py` — `InitiatePayload`, `run_mission`, Instagram/cross girişleri ve WS sonuçları.
- `scripts/run_task.py` — standart CLI/Rust görevi girdisi.
- `agent_core/scraper/instagram_ghost.py` — `InstagramPost` / `InstagramProfile`, tarih çıkarımı, 12-post sınırı ve kronolojik sıralama.
- `agent_core/services/platform_registry.py` — `ig_target_profile_update` ve canlı kazıma dönüşü.
- `agent_core/engines/frequency_engine.py`, `seismos_engine.py`, `strata_engine.py`, `pulse_engine.py`, `void_engine.py`, `gravity_engine.py`, `key_engine.py`, `pillar_orchestrator.py` — mevcut ölçüm ve rapor üretimi.
- `agent_core/services/timing_forensics.py`, `agent_core/agents/human_behavior.py` — P7 dışındaki timestamp tüketicileri.
- `agent_core/services/pillar_evidence_adapter.py`, `agent_core/domain/pillar_models.py`, `pillar_wave2_models.py` — rapor/scope sözleşmeleri.
- `agent_core/task_executor.py`, `agent_core/services/canonical_memory.py`, `hindsight_memory.py`, `agent_core/domain/memory_models.py` — görev raporu ve kalıcılık yolları.
- `tests/test_pillar_engines.py`, `tests/unit/test_engine_determinism.py`, `tests/unit/test_wiring_timing.py` — sentetik temporal fixtures.
