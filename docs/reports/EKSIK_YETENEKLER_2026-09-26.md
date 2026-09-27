# Yedi Önerilen Eksiklik — Kod Tabanı İncelemesi

**Tarih:** 2026-09-26

**Kapsam:** Bu checkout'taki `agent_core/`, `backend/`, ilgili frontend çağrıları ve bunların profil analiz akışına bağlandığı yerler. Bu belge yedi belirli öneriyi değerlendirir; tüm ürün güvenliği veya veri saklama politikasının denetimi değildir.

## Okuma kuralı

“Bulunamadı” ifadesi, ilgili özelliğin bu incelemede aranan dosya/çağrı akışlarında entegre bir uygulamasının görülmediği anlamına gelir; tek başına `grep` ile tüm olası davranışların yokluğu kanıtlanmış olmaz. Pozitif eşleşmelerin ilgili kaynak kodu ayrıca okundu. Aşağıdaki **kısmi** etiketleri, yakın bir mekanizmanın varlığını bildirir; önerilen yeteneğin tamamlandığı anlamına gelmez.

## Özet

| # | Öneri | Sonuç | Kaynakta görülen yakın işlev / sınır |
|---|---|---|---|
| 1 | Fotoğrafın kaynağını tersine arama / catfish doğrulaması | **Kısmi; tersine arama yok** | Görsel-metin tutarlılık yorumu ve takipçi-etkileşim heuristiği var. Bunlar fotoğrafın çalıntı olduğunu veya hesabın gerçek kimliğini kanıtlamaz. |
| 2 | Hedefin yaşı ve rızası için zorunlu güvenlik kapısı | **Bulunamadı** | Pattern Interrupt prompt'unda rıza/sınır dili var; bu yaş kontrolü veya yapılandırılmış rıza kapısı değil. |
| 3 | Kullanıcının tekrar tekrar farklı hedefleri incelemesini izleme | **Kısmi; hedefe özgü izleme yok** | API'de genel kimlik-temelli hız sınırları ve görev kapasite sınırı var; farklı hedefleri zaman içinde sayıp kötüye kullanım örüntüsü çıkaran kapı bulunmadı. |
| 4 | Sosyal graf / ilişki ağı | **Kısmi; etkileşim sayıları var** | Takipçi/takip edilen ve post beğeni/yorum adetleri alınabiliyor; yorum yazarları, etkileşim kenarları ve ortak takipçi ağı profil hattına taşınmıyor. |
| 5 | Video ve ses içeriği analizi | **Kısmi; video metadata'sı var, içerik hattı yok** | Scraper video/Reels türü ve URL'sini tanıyabiliyor; normal profil adaptörü video URL'sini aktarmıyor. Caption metni post metni olarak kullanılıyor; kare çıkarımı veya ses transkripti görülmedi. |
| 6 | Skor kalibrasyonu ve gerçek sonuçtan geri besleme | **Bulunamadı** | Kodda 0.70'lik sabit bir görev eşiği ve farklı heuristik skorlar var; gerçek kullanıcı sonuçlarından öğrenen kalibrasyon/backtest döngüsü görülmedi. |
| 7 | Dil tespiti ve otomatik çeviri | **Kısmi; sınırlı iki dilli ayrıştırma var** | Scraper bazı İngilizce/Türkçe profil biçimlerini ve sayı etiketlerini ayrıştırıyor; genel dil tespiti veya çeviri katmanı görülmedi. |

## Bulgular

### 1. Görsel kaynağı / catfish

- `VisionAnalyzer.analyze_images()` en çok dört görsel URL'sini indirip multimodal modele görünür nesne, ortam, eylem ve estetik özeti çıkarttırır; tersine görsel araması çağrısı değildir (`agent_core/services/vision_analyzer.py:165-245`).
- `AuthenticityAuditor` biyografi/gönderi metinlerini bu görsel özetle karşılaştırır. Çıktısı LLM yorumudur; fotoğraf kökeni, yüz kimliği veya profil sahibinin gerçek kimliği için doğrulama sağlamaz (`agent_core/agents/authenticity_auditor.py:17-89`).
- `audit_followers()` takipçi ve beğeni/yorum **adetlerinden** etkileşim oranı hesaplar; düşük oran için “şüpheli/şişirme şüphesi” heuristiği üretir. Bu, tek başına bot veya catfish tespiti değildir (`agent_core/services/follower_audit.py:19-105`).

**Sonuç:** Tersine görsel arama ve kaynak/kimlik doğrulaması bulunmadı. Görsel-metin tutarlılığı ve etkileşim heuristiği yalnızca komşu, sınırlı işlevlerdir.

### 2. Yaş / rıza kapısı

- `agent_core/`, `backend/` ve `frontend/` içinde yaş doğrulaması, reşit olmayan hedef tespiti veya rıza onayı ile analiz/mesaj rotasını durduran bir kapı bulunmadı.
- `PatternInterrupt` istemi saygı, sınır ve rızaya uygun mesaj ister (`agent_core/agents/pattern_interrupt.py:111-136`); metin talimatı, doğrulanmış yaşı veya rızayı makine tarafından kontrol eden kapı değildir.
- Gizli profilde erişilebilir gönderi yoksa scraper yetersiz kanıtla durabilir (`agent_core/scraper/instagram_ghost.py:498-500`); bu da yaş/rıza kontrolü değildir.

**Sonuç:** Önerilen yaş/rıza ön-kapısı bulunmadı. Bu, sistemdeki diğer API erişim kontrollerinden ayrı bir ürün/safety açığıdır.

### 3. Tekrarlanan hedef / kötüye kullanım örüntüsü

- Genel limitler vardır: `initiate` için 5 istek/60 saniye; Aspasia ve deneysel uçlar için de ayrı kovalar tanımlanır (`backend/api.py:482-494`). Kimlik, sunucunun belirlediği rate identity'den alınır (`backend/api.py:585-619`); görev başlatma bu kovayı uygular (`backend/api.py:2565-2571`).
- Bu limitler istek yoğunluğunu sınırlar. Hedef URL/kullanıcı adına göre görev geçmişi tutup farklı hedeflere tekrarlanan sorguları tespit eden davranışsal izleme olarak çalışmaz.

**Sonuç:** Genel API rate-limit'i mevcut; hedefe özgü tekrar/ısrar takibi bulunmadı.

### 4. Sosyal graf

- Instagram şeması follower/following sayıları ve post başına `like_count`/`comment_count` taşıyor (`agent_core/scraper/instagram_ghost.py:50-92`).
- Normal görev adaptörü post caption'larını, zamanlarını, beğeni/yorum sayılarını ve görsel URL'lerini geçiriyor; yorum metni/yazarı veya ilişki kenarları yok (`agent_core/services/platform_registry.py:184-214`). Takipçi denetimi bu sayımlardan türetilen oranları kullanıyor (`agent_core/services/follower_audit.py:34-105`).

**Sonuç:** Sayısal etkileşim metrikleri var; yorum etkileşimi çözümlemesi, ortak takipçiler ve ilişki ağı analizi bulunmadı.

### 5. Video / ses

- `InstagramPost` `is_video`, `post_type` (`video`, `reel`, vb.) ve `video_url` alanlarını tanımlar; scraper bunları bazı Instagram yanıtlarından çıkarır (`agent_core/scraper/instagram_ghost.py:50-68, 108-117, 239-257`).
- Normal profil adaptörü caption'ı `posts` alanına, `display_url` değerini `images` alanına ve tür bilgisini `post_types` alanına aktarır; `video_url` alanını hedef analiz girdisine koymaz (`agent_core/services/platform_registry.py:184-214`).
- `VisionAnalyzer` fotoğraf/görsel URL'lerini işler; video kareleri veya ses transkripti üretmez (`agent_core/services/vision_analyzer.py:165-235`). Kodda genel bir model-yönlendirme `video` kabiliyeti tanımı bulunması, Instagram profil akışına video/ses analizinin bağlandığını göstermez (`agent_core/services/final_routing_policy.py:157-190`).

**Sonuç:** Video/Reels türü ve URL metadata'sı kısmen toplanır; caption metni analiz girdisi olabilir. Video görüntüsü veya ses içeriği için entegre analiz/transkripsiyon akışı bulunmadı.

### 6. Kalibrasyon / sonuç geri beslemesi

- `ResonanceCalculator` `compatibility_score` değerini, görev yürütücüsünün ürettiği kullanıcı/hedef vektörlerinin cosine benzerliği olarak hesaplar. Vektörlerin girdisi model tahminidir (`agent_core/agents/resonance_calculator.py:102-119, 128-196`).
- `PinealExecutor`, `resonance_calc` çalışmışsa `< 0.70` sonucunda `halted_frequency` durumuna geçip deferred mesaj adımlarından önce döner (`agent_core/task_executor.py:1435-1448`). Eşik kodda sabittir; gerçek yaşam sonuçlarından kalibre edilmiş bir istatistik olarak sunulamaz.
- `KeyEngine.confidence`, altı raporun kaçının `OBSERVED`/`WEAK` olduğuna göre `active / 6` hesaplanır; kapsama oranıdır, doğruluk olasılığı değildir (`agent_core/engines/key_engine.py:72-90`).
- İncelenen profil/mesaj akışında gönderilen mesajın gerçek yanıtını toplayıp bu skorları kalibre eden veya backtest eden bir döngü bulunmadı.

**Sonuç:** Deterministik skor hesapları ve karar eşikleri var; ampirik kalibrasyon ve sonuç geri beslemesi bulunmadı.

### 7. Dil tespiti / çeviri

- `InstagramGhostScraper` bazı profil açıklaması şablonlarında `Instagram'da` ve `on Instagram` ifadelerini, ayrıca Türkçe/İngilizce sayı etiketlerini tanır (`agent_core/scraper/instagram_ghost.py:325-352`). Bu, sınırlı sayfa ayrıştırmasıdır.
- Rezonans modülünde Türkçe ve İngilizce stopword listesi vardır; metin çevirisi veya genel dil tespiti yapmaz (`agent_core/agents/resonance_calculator.py:65-77`).
- `agent_core/`, `backend/` ve `frontend/` kaynaklarında profil analizine bağlanan genel `language detection` veya otomatik çeviri adımı bulunmadı. Bir LLM'nin bazı dillerde yanıt verebilmesi, bu ürün sözleşmesinde dil tespiti/çeviri garantisi değildir.

**Sonuç:** Türkçe/İngilizce biçimlere yönelik sınırlı ayrıştırma işaretleri var; çok dilli analiz için dil tespiti/çeviri katmanı bulunmadı.

## Genel karar

Önceki “6'sı yok, biri kısmi” özeti fazla kaba kalıyor: **önerilen tam yeteneklerin hiçbiri bu incelemede tam uygulama olarak doğrulanmadı**, ancak 1, 3, 4, 5 ve 7 için bazı ilişkili/kısmi mekanizmalar mevcut. Bu kısmi mekanizmaları eksik özelliğin tamamı gibi sunmamak gerekir. Bu belge kaynak kodu incelemesidir; test veya canlı sağlayıcı doğrulaması yapılmadı.
