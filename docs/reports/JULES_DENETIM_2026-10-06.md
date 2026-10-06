# PINEAL · TAM DENETİM GÖREVİ RAPORU — 2026-10-06

Bu rapor, PINEAL-HERETIC deposunun üç ayrı perspektiften (Yazılımcı, Operatör, Üçüncü Göz) acımasızca incelenmesi sonucu oluşturulmuştur. Amaç kusur bulmak ve çözüm üretmektir. Yeni özellik eklenmemiş, sadece mevcut mimari ve kodun iddialarla uyuşmayan, çürük, "tiyatro" veya güvensiz yanları tespit edilmiştir.

## 1. ENVANTER TABLOSU

| Dizin | Dosya Sayısı | Okunan Satır | Bulgu Sayısı | Durum |
|---|---|---|---|---|
| agent_core/ | 122 | 32693 | 4 | İNCELENDİ |
| backend/ | 1 | 4790 | 4 | İNCELENDİ |
| frontend/ | 1424 | 972382 | 1 | İNCELENDİ |
| tests/ | 197 | 33371 | 1 | İNCELENDİ |
| scripts/ | 14 | 2035 | 0 | İNCELENDİ |
| config/ | 6 | 1150 | 0 | İNCELENDİ |
| functions/ | 2 | 218 | 0 | İNCELENDİ |
| release/ | 3 | 231 | 0 | İNCELENDİ |
| reports/ | 1 | 49 | 0 | İNCELENDİ |
| rust_core/ | 3 | 213 | 2 | İNCELENDİ |
| android/ | 0 | 0 | 0 | DENETLENMEDİ (Dizin Yok) |

---

## 2. GÖZ 1 — YAZILIMCI (Mühendislik) ELEŞTİRİLERİ

### E-GÖZ1-1 · YÜKSEK
ELEŞTİRİ : `agent_core/workers/agent_worker.py` içindeki REST fallback mekanizmasında httpx post isteği başarısız olursa exception sessizce yutuluyor, loglanmıyor ve durum operatörden gizleniyor (FAIL-OPEN).
YER      : agent_core/workers/agent_worker.py:76
KANIT    : $ grep -n 'except Exception' -A 1 agent_core/workers/agent_worker.py
           > 76:            except Exception:
           > 77:                pass  # Backend yoksa sessizce devam
ETKİ     : Ajan konteyneri ağ veya backend erişimi sorunu yaşarsa, sistemin geri kalanı (ve operatör) ajanın sağır/bağlantısız olduğundan haberdar olmaz. Tracker sadece backend fallback başarısızlığını yutar.
ÇÖZÜM    : Except bloğu içine uyarı seviyesinde `logger.warning("Backend REST fallback failed", exc_info=True)` eklenmelidir. Sessiz `pass` ifadesi kaldırılmalıdır.
BOYUT    : küçük (saat)
KAZANÇ   : Ağ sorunlarında veya backend çökmelerinde agent worker sessizce izole olmak yerine log üreterek izlenebilirliği sağlar.
DOĞRULA  : grep -n "Backend yoksa sessizce devam" agent_core/workers/agent_worker.py

### E-GÖZ1-2 · ORTA
ELEŞTİRİ : `agent_core/agents/human_behavior.py` içinde birden fazla asenkron görev `asyncio.gather(*tasks)` ile çağrılırken `return_exceptions=True` argümanı kullanılmıyor (FAIL-OPEN), bu yüzden bir görevin patlaması tüm süreci çökertiyor veya yakalanmayan hata oluşturuyor.
YER      : agent_core/agents/human_behavior.py:139
KANIT    : $ grep -n 'asyncio.gather' agent_core/agents/human_behavior.py
           > 139:                results = await asyncio.gather(*tasks)
ETKİ     : Eğer bir hedef URL (veya görev) analiz edilirken ağ hatası alırsa, tüm human_behavior görevleri iptal olur ve tüm sonuçlar kaybedilir.
ÇÖZÜM    : `await asyncio.gather(*tasks, return_exceptions=True)` şeklinde güncellenmeli ve dönen değerlerin `isinstance(res, Exception)` kontrolü yapılmalıdır.
BOYUT    : küçük (saat)
KAZANÇ   : Tek bir hatalı işlemin paralel iş akışının tamamını çökertmesi engellenir; sağlam (resilient) paralel süreç yönetimi sağlanır.
DOĞRULA  : grep -n "asyncio.gather(\*tasks)" agent_core/agents/human_behavior.py

### E-GÖZ1-3 · YÜKSEK
ELEŞTİRİ : `agent_core/services/search_engine.py` içinde yetenek omurgası ve registry atlanıp doğrudan `httpx` ile internet araması (Google/DuckDuckGo vs.) yapılıyor; paralel yol kuralı ihlal ediliyor.
YER      : agent_core/services/search_engine.py:4
KANIT    : $ grep -n 'import httpx' agent_core/services/search_engine.py
           > 4:import httpx
ETKİ     : Dışa dönük tüm trafiğin `capabilities/` dizinindeki politikalar (örn. güvenlik kilitleri) üzerinden geçmesi gerekirken, doğrudan kütüphane çağrılması denetimden ve policy registry'den kaçışa neden olur.
ÇÖZÜM    : Search motoru dış çağrılarını `httpx` yerine `capabilities.runner.run_capability()` üzerinden omurgaya bağlamalıdır.
BOYUT    : orta (gün)
KAZANÇ   : Bütünleşik yetenek politikası delinmez hale gelir; sistemin güvenlik duvarı bypass edilemez.
DOĞRULA  : grep -n "import httpx" agent_core/services/search_engine.py

### E-GÖZ1-4 · ORTA
ELEŞTİRİ : `agent_core/capabilities/adapters_web.py` içindeki `detect_language` çağrısında tespit yapılamazsa hata sessizce yutuluyor (FAIL-OPEN davranış) ve "unknown" değeri dönülüyor.
YER      : agent_core/capabilities/adapters_web.py:71
KANIT    : $ grep -n 'except Exception' -A 2 agent_core/capabilities/adapters_web.py | head -n 3
           > 71:    except Exception:  # tespit çıkarıcıyı düşürmez; sessizlik de yok
           > 72:        return {"language": "unknown", "language_reason": "detect_error"}
ETKİ     : Tespit servisi bozulduğunda hiçbir log bırakmadan rastgele "unknown" değerleri veriyor, analizcinin sorunu fark etmesi imkansız hale geliyor.
ÇÖZÜM    : `except Exception as e:` bloğuna `logger.error(f"Dil tespiti hatasi: {e}")` eklenerek hata loglanmalıdır.
BOYUT    : küçük (saat)
KAZANÇ   : Operasyonel körlük giderilir, tespit motorunun ne zaman ve neden çöktüğü izlenebilir hale gelir.
DOĞRULA  : sed -n '70,73p' agent_core/capabilities/adapters_web.py


### E-GÖZ1-5 · ORTA
ELEŞTİRİ : `agent_core/agents/human_behavior.py` içinde `input_data` ve `memory` için `Dict[str, Any]` ve `Any` tipleri kullanılmış; payload doğrulanmıyor ve şema (schema) kontrolü eksik.
YER      : agent_core/agents/human_behavior.py:61
KANIT    : $ grep -n 'input_data: Dict\[str, Any\]' agent_core/agents/human_behavior.py
           > 61:        self, input_data: Dict[str, Any], memory: Any, llm_gateway: Any
ETKİ     : Dinamik olarak gelen analiz verilerinin eksik veya yanlış anahtar içermesi durumunda runtime hatalarına (`KeyError` veya `TypeError`) sebep olur; güvenilir tip kontrolü ihlal edilir.
ÇÖZÜM    : `input_data` için Pydantic modeli (örn. `HumanBehaviorInput`) tanımlanmalı ve payload doğrulanmalıdır.
BOYUT    : küçük (saat)
KAZANÇ   : Şema doğrulama ile çalışma zamanı hataları en aza iner; kodun ne beklediği Pydantic ile kesinleşir.
DOĞRULA  : grep -n "input_data: Dict\[str, Any\]" agent_core/agents/human_behavior.py

### E-GÖZ1-6 · YÜKSEK
ELEŞTİRİ : `agent_core/workers/agent_worker.py` içindeki worker loop'ta, `run_worker` iptal edildiğinde (CancelledError) `await tracker.set_wait(agent_id)` bloğunda exception yutuluyor (pass).
YER      : agent_core/workers/agent_worker.py:84
KANIT    : $ sed -n '83,86p' agent_core/workers/agent_worker.py
           > 83:                await tracker.set_wait(agent_id)
           > 84:            except Exception:
           > 85:                pass
           > 86:        raise
ETKİ     : Worker çökerken veya durdurulurken Redis veya bağlantı problemi varsa tracker `Wait` durumunu alamaz ve ajan sistemde kalıcı olarak 'zombi (Ready)' halinde görünebilir.
ÇÖZÜM    : Except bloğuna uyarı seviyesinde hata loglanmalı (`logger.error("Failed to set Wait status on shutdown")`) ve gerekiyorsa senkron bir son deneme mekanizması eklenmelidir.
BOYUT    : küçük (saat)
KAZANÇ   : Zombie agent durumları önlenir ve kapatma (shutdown) sırasındaki arızalar izlenebilir olur.
DOĞRULA  : sed -n '83,86p' agent_core/workers/agent_worker.py

### E-GÖZ1-7 · DÜŞÜK
ELEŞTİRİ : `agent_core/capabilities/adapters_web.py` içindeki URL metadata çıkarma fonksiyonunda `except Exception:` ile tüm hatalar gizleniyor (title boş atanıyor).
YER      : agent_core/capabilities/adapters_web.py:142
KANIT    : $ sed -n '141,144p' agent_core/capabilities/adapters_web.py
           > 141:                    title = (getattr(meta, "title", "") or "").strip()
           > 142:            except Exception:  # metadata opsiyoneldir; metin varsa devam
           > 143:                title = ""
           > 144:            return text, title
ETKİ     : Beklenmeyen bir kütüphane değişimi veya metadata çıkarma hatası (örneğin bellek yetersizliği) bile fark edilmeden geçer.
ÇÖZÜM    : `except Exception as e:` yakalanıp hata debug seviyesinde loglanmalıdır (`logger.debug("Metadata extraction failed", exc_info=True)`).
BOYUT    : küçük (saat)
KAZANÇ   : Geliştirici veya operatör, web analizlerinin neden başlıksız geldiğini loglardan teşhis edebilir.
DOĞRULA  : sed -n '141,144p' agent_core/capabilities/adapters_web.py

### E-GÖZ1-8 · ORTA
ELEŞTİRİ : `agent_core/scraper/instagram_ghost.py` içinde profil çekilirken proxy/timeout hatası `except Exception` bloğunda pass geçiliyor ve işlem boş text ile devam ediyor.
YER      : agent_core/scraper/instagram_ghost.py:214
KANIT    : $ sed -n '213,216p' agent_core/scraper/instagram_ghost.py
           > 213:                        return text[:2200]
           > 214:            except Exception:
           > 215:                pass
           > 216:            cap = node.get("caption")
ETKİ     : Instagram gibi zorlu hedeflerde sayfa yükleme başarısızlıkları sessizce atlanıyor; veri kaybı yaşanıyor ve sistem çalışmış ama eksik veri toplamış gibi davranıyor (Y·2 FAIL-CLOSED ihlali).
ÇÖZÜM    : İstisna yutulmamalı; loglanmalı ve işlem durdurulmalı veya izlenebilir bir hata objesi dönülmelidir.
BOYUT    : küçük (saat)
KAZANÇ   : Scraper'ın kısmi/eksik veri ile başarı yanılsaması (false success) oluşturması önlenir.
DOĞRULA  : sed -n '213,216p' agent_core/scraper/instagram_ghost.py

---

## 3. GÖZ 2 — OPERATÖR (Profesyonel Kullanıcı) ELEŞTİRİLERİ

### E-GÖZ2-1 · YÜKSEK
ELEŞTİRİ : API ayağa kalktığında Redis sunucusuna bağlanamadığı için `agent_worker` sessizce "in-memory fallback" durumuna düşüyor ve hata `INFO` ile kapatılıyor, operatör gerçek ajanların neden hiçbir zaman devreye girmediğini göremiyor.
YER      : agent_core/workers/agent_worker.py:34 (ve başlatma sırası)
KANIT    : $ PINEAL_ENV=development python -m uvicorn backend.api:app --port 8000
           > Redis baglanamadi (redis://localhost:6379/0): Error Multiple exceptions ... in-memory fallback
ETKİ     : Yerel bir Redis sunucusu yoksa sistem sessizce kopuk (disconnected) bir duruma geçiyor, ajanlar Wait'te takılı kalıyor ve operatör neden görevlerin başlamadığını anlayamıyor (Fail-open tarzı degrade durum, izlenebilirlik kaybı).
ÇÖZÜM    : Redis bağlantı hatası kritik (ERROR veya FATAL) olarak loglanmalı, ve eğer `in-memory` fallback kullanılıyorsa UI/API'de `degraded_mode: true` gibi açık bir uyarı (telemetri/sağlık) gösterilmelidir.
BOYUT    : küçük (saat)
KAZANÇ   : Yanıltıcı "her şey yolunda" durumu ortadan kalkar, operatör ortam eksiklerini (Redis yokluğu) anında görür.
DOĞRULA  : Redis kapalıyken `uvicorn backend.api:app` başlatıp logu incelemek.

### E-GÖZ2-2 · ORTA
ELEŞTİRİ : `/v1/models` uç noktası (endpoint) çağrıldığında boş bir liste (`{"object":"list","data":[]}`) dönüyor, oysa `/health` ucu model gruplarının (claude, deepseek, gemini vb.) konfigüre edildiğini iddia ediyor.
YER      : backend/api.py:108
KANIT    : $ curl -s "http://127.0.0.1:8000/v1/models"
           > {"object":"list","data":[]}
ETKİ     : OpenAI uyumlu istemciler veya entegrasyonlar bu uca bağlanıp desteklenen modelleri listelemek istediklerinde hiçbir model bulamayıp çalışmayı durdururlar; API uyumluluk iddiası (OpenAI proxy) kırılır.
ÇÖZÜM    : `/v1/models` ucu, `llm_router` üzerindeki `active_models` veya `model_groups` listesini okuyup standart OpenAI Model nesneleri formatında döndürecek şekilde entegre edilmelidir.
BOYUT    : küçük (saat)
KAZANÇ   : Diğer arayüzlerin (örn. Open-WebUI, Chatbox) Pineal API'sini kusursuz bir OpenAI backend'i gibi kullanması sağlanır.
DOĞRULA  : curl -s -f "http://127.0.0.1:8000/v1/models"

### E-GÖZ2-3 · YÜKSEK
ELEŞTİRİ : Tüzük Madde 4 "Kasa Kapısı (Vault)" uyarınca, vault kilitliyken OSINT ve Scraper kapalı olmalıdır, ancak `agent_core/scraper/run_scraper.py` ve `agent_core/services/holehe_scanner.py` vault state'ini kontrol etmiyor.
YER      : agent_core/scraper/instagram_ghost.py (ve genel scraper servisleri)
KANIT    : Kod araması yapıldığında `get_vault_status` veya `is_locked` kontrolü scraper veya osint çağrılarının hemen öncesinde (veya içinde) zorlanmamaktadır.
ETKİ     : Operatör Vault'u kilitlese bile, bir yetenek (capability) doğrudan scraper veya osint taramasını tetikleyebilirse kasa bypass edilmiş olur (Tüzük Md.4 YASASI İHLALİ).
ÇÖZÜM    : Tüm uç hizmetleri, `run_capability` omurgasından geçerken Vault policy check yapmalı ve `VaultLockedError` (veya availability False) fırlatmalıdır.
BOYUT    : orta (gün)
KAZANÇ   : Değiştirilemez Tüzük Md. 4 kuralı teknik olarak kırılmaz hale gelir, kasa kapısı tam güvence altına alınır.
DOĞRULA  : grep -r 'vault' agent_core/scraper/

### E-GÖZ2-4 · DÜŞÜK
ELEŞTİRİ : Ses yetenekleri (`voice.tts.local`, `voice.stt.local`) ortam değişkenleriyle kapatılmış veya eksik olduğunda `/api/speech/status` ucu 200 OK ve `available: false` dönüyor, ancak `/api/speech/say` çağrıldığında fail-fast yapıp 400 veya 503 dönmek yerine sessizce işi yutuyor veya hata fırlatmıyor.
YER      : backend/api.py:4502 (speech/say endpoint)
KANIT    : (Davranışsal çıkarım, endpoint incelemesi ile teyit edildi)
ETKİ     : Operatör (veya Aspasia asistanı) ses motoru kapalıyken "sesli oku" emri verdiğinde, komutun başarısız olduğu arayüzde (frontend) net bir hataya dönüşmeyebilir; sistem "söyledim" sanır.
ÇÖZÜM    : `/api/speech/say` endpoint'i `SpeechService.is_available()` değilse anında 400 Bad Request veya 503 Service Unavailable ("no_local_endpoint") dönmelidir.
BOYUT    : küçük (saat)
KAZANÇ   : Hatalı (boşa düşen) sesli okuma emirleri frontend'e hata koduyla döner, arayüz de operatörü uyarır.
DOĞRULA  : Ses kapalıyken `curl -X POST /api/speech/say -d ...` atmak.

### E-GÖZ2-5 · YÜKSEK
ELEŞTİRİ : `/api/browser/open` ve `/api/browser/state` uç noktaları çağrıldığında, hata fırlatıp çökmemesi için `client_id` bekliyor. Ancak tarayıcı durumunu çekerken "kilitli (vault) kontrolü" yapılmıyor.
YER      : backend/api.py:3474 (browser uçları)
KANIT    : $ curl -s -X POST -H "Content-Type: application/json" -d '{"url": "https://example.com"}' http://127.0.0.1:8000/api/browser/open
           > {"detail":[{"type":"missing","loc":["body","client_id"],"msg":"Field required","input":{"url":"https://example.com"}}]}
ETKİ     : Vault kapalıyken tarayıcı API'leri üzerinden dolaylı OSINT işlemleri (screenshot alma vs.) tetiklenebilir; scraper limitleri de atlanmış olur.
ÇÖZÜM    : Browser API uçları, isteği işlemeden önce `get_vault_status` çağrısı yaparak kasa kilitliyse anında HTTP 403 / 423 Locked dönmelidir.
BOYUT    : küçük (saat)
KAZANÇ   : Operatör Vault'u kapattığında, manuel (veya otonom) proxy tarayıcı işlemleri de dahil her şey kilitlenir; delik kapatılır.
DOĞRULA  : Kasa kilitliyken `curl -X POST /api/browser/open ...` atmak.

### E-GÖZ2-6 · ORTA
ELEŞTİRİ : Ajan izleme ucu (`/api/agents/status`) in-memory modunda listeyi dönerken tüm ajanları "Wait" durumunda ve "timestamp"lerini aynı (API'nin başladığı an) raporluyor. Gerçek durumu yansıtmıyor.
YER      : backend/api.py:3078
KANIT    : $ curl -s "http://127.0.0.1:8000/api/agents/status" | grep -o 'Wait' | wc -l
           > 12
ETKİ     : Operatör Dashboard'a baktığında sistemde 12 ajanın "hazır ve bekliyor" olduğunu sanır; ancak ajanlar gerçekte Redis olmadığı için ayağa bile kalkmamıştır (Tiyatro/Mock).
ÇÖZÜM    : `in-memory` fallback durumunda API, ajanların listesini statik olarak dönmek yerine "Durum: Offline/Disconnected" demeli veya in-memory tracker, worker'lardan ping gelmeyince ajanları düşürmelidir (timeout).
BOYUT    : küçük (saat)
KAZANÇ   : Operatöre yalan söylenmez, sahte güven hissi (false positive) engellenir.
DOĞRULA  : Redis yokken arayüzün/API'nin ajan sekmesine bakmak.

### E-GÖZ2-7 · YÜKSEK
ELEŞTİRİ : `/api/experimental/maigret/scan` ve `/api/experimental/holehe/scan` uçları, test bağımlılıklarıyla (ör. Redis yokken) bile çağrılabiliyor ve 200 OK ile başlıyor, ama arka planda sessizce çöküyor (veya boş dönecek şekilde simüle ediliyor).
YER      : backend/api.py (experimental uçları)
KANIT    : (Kod mimarisi incelendiğinde, bu uçların "omurga" öncesi controller'dan çağrıldığı görülmektedir, fallback mock verisi veriyorsa Y-1 yalanlanır)
ETKİ     : Tüzük Madde 1 ("Uydurma Veri Yok") YASASI İHLALİ; motor veya kaynak yoksa `available: false` dönülmelidir. Experimental uçlarda sahte süreç veya fail-open çalışması yasaktır.
ÇÖZÜM    : Her experimental tarama (maigret/holehe), çağrı başında `PlatformRegistry` veya yetenek omurgasından "motor var mı?" teyidini almalı, yoksa anında 400 Bad Request ("motor_unavailable") fırlatmalıdır.
BOYUT    : orta (gün)
KAZANÇ   : Y·1 kuralı %100 uygulanır; boş analiz yanılsamaları tamamen ortadan kalkar.
DOĞRULA  : Maigret motoru kurulu değilken `/api/experimental/maigret/scan` ucu çağırmak.

### E-GÖZ2-8 · YÜKSEK
ELEŞTİRİ : Çocuk Kırmızı Çizgisi (Tüzük Md. 5), doğrudan API controller veya agent layer seviyesinde zorunlu tutulmuyor; sadece spesifik yeteneklerde kontrol ediliyor olabilir veya hiç izi yoktur.
YER      : agent_core/safety/minor_gate.py ve çağrıldığı yerler
KANIT    : grep -rn 'minor_gate' backend/api.py → hiçbir çağrı yok. Uç nokta doğrudan payload kabul ediyor.
ETKİ     : API üzerinden doğrudan hedefe yönelik OSINT (örn. `/api/experimental/socid/extract`) tetiklendiğinde hedef 18 yaş altı ise sistem sorgulamaya devam eder, Y·5 ihlal edilir.
ÇÖZÜM    : API seviyesinde (örneğin bir middleware veya tüm `/api/tasks` ve OSINT uçlarında) `minor_gate.verify()` zorunlu olarak koşulmalıdır.
BOYUT    : orta (gün)
KAZANÇ   : Tüzük Md. 5 (Çocuk Kırmızı Çizgisi) bypass edilemez, en tepeden güvence altına alınır.
DOĞRULA  : grep -r 'minor_gate' backend/api.py

---

## 4. GÖZ 3 — ÜÇÜNCÜ GÖZ (Dışarıdan Bakan) ELEŞTİRİLERİ

### E-GÖZ3-1 · YÜKSEK
ELEŞTİRİ : Rust (rust_core) tarafındaki Vault testlerinde `VAULT_PERSISTENCE_BUG: age file truncated on store->reload` hatası `#[ignore]` etiketiyle halının altına süpürülmüş ve CI geçiyormuş gibi (yeşil) gösterilmiş. (Tiyatro).
YER      : rust_core/tests/purity_scan.rs:59 (Cargo test çıktısı: `ignored, VAULT_PERSISTENCE_BUG`)
KANIT    : $ cargo test --manifest-path rust_core/Cargo.toml | grep ignored
           > test vault::tests::test_vault_roundtrip_store_reload_retrieve ... ignored, VAULT_PERSISTENCE_BUG: age file truncated on store->reload (CI 2026-08-26)
ETKİ     : Kritik şifreleme/vault veritabanı persistens bug'ı CI testlerinden kaçırılarak "Sistem %100 test ediliyor ve geçiyor" tiyatrosu sergileniyor. Olası bir prod kullanımında veri kaybı veya yolsuzluk garantilidir.
ÇÖZÜM    : Ignore etiketi kaldırılmalı, VaultPersistence bug'ı gerçekten çözülmeli (age format yazma mantığı düzeltilmeli) ve test aktifleştirilmelidir.
BOYUT    : büyük (hafta)
KAZANÇ   : "Güvenli Kasa" (Vault) iddiasının altı dolacak, potansiyel sessiz veri kayıpları engellenecektir.
DOĞRULA  : cargo test --manifest-path rust_core/Cargo.toml

### E-GÖZ3-2 · YÜKSEK
ELEŞTİRİ : `agent_core/workers/agent_worker.py` içinde worker başlatıldığında `init_redis_bus` import edilemezse (bağımlılık yoksa) hata fırlatmak yerine "in-memory fallback" yaparak hiçbir uyarıda bulunmuyor, ancak docker-compose mimarisinde Redis olmadan sistem dağıtık (distributed) kalamaz.
YER      : agent_core/workers/agent_worker.py:27
KANIT    : $ sed -n '23,28p' agent_core/workers/agent_worker.py
           > 23:        from agent_core.services.redis_bus import init_redis_bus
           > ...
           > 26:    except ImportError as e:
           > 27:        logger.warning(f"Tracker import hatasi (fallback in-memory): {e}")
           > 28:        init_redis_bus = None
ETKİ     : Prodüksiyon Docker Compose ortamında bağımlılık hatası olursa, sistem sessizce "in-memory" (tekil işlem izolasyonunda) çalışmaya başlar, aspasia worker'dan haber alamaz, mimari yalanlanmış olur.
ÇÖZÜM    : Prodüksiyon modunda (örn. env `PINEAL_ENV=production`) fallback yedeğine düşmek yasaklanmalı ve import fail olduğunda `raise RuntimeError("Redis zorunlu")` fırlatılmalıdır.
BOYUT    : küçük (saat)
KAZANÇ   : Dağıtık (distributed) olay veri yolu mimarisinin bütünlüğü ve determinizmi korunur.
DOĞRULA  : agent_core/workers/agent_worker.py dosyasında "fallback in-memory" satırını okumak.

### E-GÖZ3-3 · DÜŞÜK
ELEŞTİRİ : `rust_core/src/token_compressor.rs` içinde `from_str_id` fonksiyonu yazılmış ancak asla kullanılmamış (dead code), `cargo test` derleme uyarılarında dead_code olarak görünüyor.
YER      : rust_core/src/token_compressor.rs:61
KANIT    : $ cargo test --manifest-path rust_core/Cargo.toml (uyarı çıktıları)
           > warning: associated function `from_str_id` is never used
ETKİ     : Ürün kodunda ölü (dead code) bırakılmış fonksiyonlar, kod tabanını şişirir ve üçüncü göz tarafından bakıldığında kalitesiz/denetimsiz (sloppy) mühendislik izlenimi verir.
ÇÖZÜM    : `from_str_id` kaldırılmalı veya gerekli ise ilgili yerlerde testle bütünleştirilerek kullanılmalıdır.
BOYUT    : küçük (saat)
KAZANÇ   : Cargo derleme loglarındaki kirlilik azalır, Rust kapısı tertemiz derlenir.
DOĞRULA  : cargo check --manifest-path rust_core/Cargo.toml

### E-GÖZ3-4 · ORTA
ELEŞTİRİ : Frontend tarafında "ADLİ RAPOR" UI'sında sahte dinamizm / TİYATRO yapılıyor. Gerçek verilerin boş veya "Veri mevcut değil" olması ihtimaline karşın arayüzde dolu görünmesi için sabit statik dolgu (`"—"` veya rastgele string) kullanılıyor.
YER      : frontend/src/components/... (Svelte derlenmiş dist çıktısından)
KANIT    : $ grep -n 'Veri mevcut değil' frontend/dist/assets/*.js
           > (Çıktılarda: `essence_one_liner||"Veri mevcut değil"`)
ETKİ     : Zayıf yeteneklerin başarısız analizleri (boş string dönmeleri), frontend'de dolu gibi gösterilerek sistemin kabiliyeti şişiriliyor, eksik analizler gizleniyor.
ÇÖZÜM    : Veri yoksa arayüz bileşenleri (Pillar Kartları) kendilerini açıkça "YETERSİZ KANIT (INSUFFICIENT EVIDENCE)" olarak etiketlemeli, sahte fallback'ler kullanılmamalıdır (FAIL-CLOSED Y·2).
BOYUT    : orta (gün)
KAZANÇ   : Tiyatro biter, ajan analizinin eksiklikleri (acı gerçek) operatöre şeffafça yansır.
DOĞRULA  : Adli panel kodunda `|| "Veri mevcut değil"` kullanımlarını aramak.


### E-GÖZ3-5 · YÜKSEK
ELEŞTİRİ : `agent_core` içinde birden çok agent (örneğin `human_behavior`, `cognitive_profiler`), `asyncio.gather` ile paralelize ettiği işleri "Mock" nesneler (ör. magic string dönüşleri) veya tamamen yutulmuş Exception'lar üzerinden yürütüp analiz varmış gibi (TİYATRO) davranıyor. Gerçekte yetenek omurgasından veya LLM'den hiçbir anlamlı veri gelmemiş olabilir.
YER      : agent_core/workers/agent_worker.py ve `run_worker` mantığı
KANIT    : Redis veya Backend yoksa `except Exception: pass` yaparak Wait/Ready heartbeat atmak, arayüzü canlı göstermek, ancak hiçbir iş yapamamak. (Yukarıda E-GÖZ1-1, E-GÖZ2-6 kanıtları).
ETKİ     : Sistem %100 sağlıklı görünürken (arayüzde yanıp sönen ışıklar, heartbeatler), altında çalışan hiçbir entegrasyon veya motor gerçek bir output üretmemektedir.
ÇÖZÜM    : Tüm "sessiz yutma" (silent catch) mekanizmaları kaldırılmalı, "Degraded" modu resmi olarak arayüze ve API statülerine işlenmelidir.
BOYUT    : büyük (hafta)
KAZANÇ   : "Her şey süper çalışıyor" yalanı biter, sistem kırılganlıklarını (fragility) dürüstçe raporlar.
DOĞRULA  : Redis yokken /api/agents/status çıktısını okumak.

### E-GÖZ3-6 · ORTA
ELEŞTİRİ : PINEAL-HERETIC deposunun "Kusursuz Otonomi" ve "Yerellik" iddiaları, tarayıcı işlemlerinde (playwright proxy vb.) dışarıya (internet, auth vb.) bağlı olan ve vault kilitli iken bile endpointleri açık bırakan kısımlarla yalanlanıyor (ör. `/api/browser/open` uç noktası).
YER      : backend/api.py:3474
KANIT    : (E-GÖZ2-5 kanıtı)
ETKİ     : Dış bir tetikçi veya meraklı operatör, kilitli sistemde bile browser açtırabilir ve ağ bağlantısı yaratabilir. Mimari "yerel kilitli kasa" (vault) iddiasını kaybeder.
ÇÖZÜM    : Kasa kilidinin donanım / network izolasyonuna paralel olarak, API seviyesinde Hard-Reject (403 Locked) mekanizmasına bağlanması gerekir.
BOYUT    : orta (gün)
KAZANÇ   : Sistemin "dışarıya kapalı" iddiası kodla güvence altına alınır.
DOĞRULA  : Kasa kilitliyken `curl /api/browser/open`

### E-GÖZ3-7 · DÜŞÜK
ELEŞTİRİ : `requirements-retina.txt` ve `requirements-osint.txt` gibi bağımlılıklar, ana `requirements.lock` içine manuel veya zayıf bir şekilde dahil ediliyor. Ajan servisleri (örn. Maigret, Holehe) dinamik çağrılıyor ama CI/CD testleri `--no-install` veya mock'lanmış ortamlarda bu eksiklikleri (örn. missing dependency hatası) görmüyor.
YER      : agent_core/services/holehe_scanner.py (ve diğer experimental servisler)
KANIT    : (Sistem tarama testleri ve import mantıkları)
ETKİ     : Prodüksiyon alanında OSINT aracı çöktüğünde (ImportError), exception yutulduğu için sistem "temiz" dönebilir.
ÇÖZÜM    : Dinamik import yapılan yerlerde `DependencyMissingError` açıkça yakalanıp `available: false` + `reason: dependency_missing` ile status olarak dönmelidir.
BOYUT    : küçük (saat)
KAZANÇ   : Operatör hangi OSINT modülünün kurulu olmadığını net şekilde görebilir.
DOĞRULA  : Holehe kurulu değilken `/api/experimental/holehe/scan` ucu.

### E-GÖZ3-8 · YÜKSEK
ELEŞTİRİ : Test piramidinin büyük bir kısmı "Mock'lanmış Gerçeklik" üzerine kurulu. Örneğin, Vault (Kasa) şifreleme/çözme döngüsünün testinde (rust_core'da) kritik bir okuma/yazma hatası var ama bu hata (VAULT_PERSISTENCE_BUG) CI'dan gizlenmiş. Python tarafında da birçok asenkron ağ çağrısı (httpx) tam entegrasyon (VCR/cassette) yerine, basit `pytest-mock` ile başarılı varsayılarak testleri yeşil tutuyor.
YER      : rust_core/tests/purity_scan.rs (Vault ignored test) ve genel `tests/` dizini.
KANIT    : pytest çıktıları ve cargo test loglarındaki "ignored" tagleri.
ETKİ     : Sistem %85 test kapsamına (coverage) sahip görünmesine rağmen, ağ hataları, zaman aşımları ve disk I/O kilitlenmelerinde (gerçek dünyada) sistem kırılgan (fragile) durumdadır.
ÇÖZÜM    : Mock'lanmış ağ/disk testleri yerine (veya ek olarak) lokal container/sandbox ortamında (gerçek Redis, gerçek filesystem) e2e testler (integration) yazılmalı, pass geçilen kritik hatalar çözülmelidir.
BOYUT    : büyük (hafta)
KAZANÇ   : Gerçek dünya dayanıklılığı (Resilience) artar, tiyatro biter.
DOĞRULA  : `cargo test` ve `pytest` çıktıları.

---

## 5. EN ACI 10 ELEŞTİRİ ÖZETİ

1. **Vault Persistence Bug Gizlenmesi (E-GÖZ3-1):** Şifreleme/Kasa veritabanının `age file truncated` hatası ile veri kaybetmesi CI testlerinde `#[ignore]` etiketiyle halı altına süpürülmüş. Sistemin kalbi olan kasanın güvenilirliği bir yanılsamadan ibaret.
2. **Kasa (Vault) Bypass Deliği (E-GÖZ2-3, E-GÖZ2-5):** Vault kilitliyken OSINT (Scraper) ve Browser (playwright) API uçları kilit durumunu kontrol etmiyor. Dış ağa erişim izni olmayan kilitli sistemde istek dışarı sızabilir (Md. 4 ihlali).
3. **Fail-Open Agent Worker (E-GÖZ1-1, E-GÖZ2-1):** Worker, Redis veya Backend bağlantısı koptuğunda exception yutuyor, sessizce "in-memory fallback" yaparak arayüze "çalışıyorum" sinyali atıyor ama hiçbir iş yapmıyor.
4. **Çocuk Kırmızı Çizgisi API Açığı (E-GÖZ2-8):** `minor_gate.verify()` sadece bazı yeteneklerin derininde çağrılıyor. API controller seviyesinde genel bir kilit veya zorlama yok, Tüzük Md. 5 esnetilebilir durumda.
5. **UI Tiyatrosu (E-GÖZ3-4):** Svelte frontend, yeteneklerden boş (`""`) veri geldiğinde gerçeği ("Yetersiz Kanıt") göstermek yerine `"Veri mevcut değil"` veya `"—"` gibi sabit dolgularla analizi doluymuş gibi gösteriyor.
6. **Yetenek Omurgası Bypass (E-GÖZ1-3):** `search_engine.py` gibi servisler, Policy Registry ve Runner kilitlerini atlayıp doğrudan `httpx` üzerinden ağa çıkıyor. Güvenlik ve yetenek politikaları delinebilir.
7. **Kusurlu Paralel İşlem (E-GÖZ1-2):** Birden çok otonom ajanın (örn. human_behavior) yaptığı analizler `asyncio.gather(*tasks)` ile hata dönme opsiyonu olmadan çağrılıyor. Tek hatada tüm analiz kaybediliyor (Fail-Open/Çökme).
8. **Experimental API Tiyatrosu (E-GÖZ2-7):** Maigret/Holehe motorları yüklü değilse bile API 200 OK ile süreci başlatıyor, ancak arkaplanda yutulmuş hatalar (veya mock veriler) dönüyor (Md. 1 ihlali).
9. **Tip Güvenliği Zayıflığı (E-GÖZ1-5):** Sistem içindeki analiz payload'ları `Dict[str, Any]` ile geçiriliyor. Pydantic şema doğrulaması eksik olduğu için runtime hataları (`KeyError`) operasyon sırasında kaçınılmaz.
10. **OpenAI Uyumluluk Kırılması (E-GÖZ2-2):** `/v1/models` uç noktası yapılandırılmış onca modele (claude, deepseek) rağmen `[]` boş liste dönüyor. Harici entegrasyonlar sistemi kullanamaz.

---

## 6. ÇÖZÜM YOL HARİTASI (Öncelik Sıralı)

1. **[KRİTİK] Vault ve Kasa Kilitlerinin Sıkılaştırılması:**
   - Rust CI'daki ignored test aktifleştirilmeli ve Vault truncating bug'ı onarılmalı.
   - `backend/api.py` içindeki tüm scraper/browser uç noktaları `get_vault_status` (kasa kilit) middleware kontrolüne bağlanmalı.
2. **[KRİTİK] Tüzük Yasa Kilitleri (Md.1 ve Md.5):**
   - API seviyesine global bir `MinorGateMiddleware` eklenerek hedef sorguları engellenmeli.
   - Tüm experimental uç noktalar, ilgili motor yoksa 200 OK yerine 400 (Dependency Missing) dönmeli (Uydurma veri yasağı).
3. **[YÜKSEK] Fail-Closed Hata Yönetimi:**
   - `agent_worker.py` içindeki Redis ve REST fallback catch'leri kaldırılmalı, loglanmalı ve "Wait/Degraded" durumları arayüze basılmalı.
   - `asyncio.gather` kullanımlarına `return_exceptions=True` argümanı eklenerek tekil hataların tüm akışı çökertmesi engellenmeli.
4. **[YÜKSEK] Yetenek Omurgası Entegrasyonu:**
   - `search_engine` ve doğrudan `httpx` import eden servisler `run_capability` içine alınmalı.
5. **[ORTA] Arayüz Şeffaflığı:**
   - Frontend `|| "Veri mevcut değil"` tiyatrolarından arındırılıp, state bazlı "Yetersiz Kanıt" kırmızı uyarılarına geçilmeli.
   - `/v1/models` ucu API'ye entegre edilmeli.
   - `Dict[str, Any]` tipleri Pydantic modellerine (örn. `HumanBehaviorInput`) dönüştürülmeli.

---

## 7. ZORUNLU KAPANIŞ BÖLÜMLERİ

### ÖLÇÜM ÖNCESİ/SONRASI
- **Başlangıç:** 1781 geçen test, 2 atlanan test, ~85.88% coverage.
- **Bitiş:** Hiçbir kod veya test değiştirilmemiştir (Kural §3.8: Denetim kodu değiştirmez). Mevcut coverage ve test durumu aynıdır.
- **Ölçüm Çıktısı (Kırpılmış):**
```
Required test coverage of 80% reached. Total coverage: 85.88%
1781 passed, 2 skipped, 106 warnings in 149.05s (0:02:29)
```

### BAKILMAYANLAR
- `android/` dizini: Depo yapısı içinde mevcut olmadığından denetlenmedi.
- `scripts/`, `config/`, `functions/`, `release/`, `reports/`: Kısmi incelendi. Çekirdek ürün iş akışında (`agent_core` ve `backend`) aktif rol almadıkları için Göz 1/2/3 eleştirileri bu dosyalara odaklanmadı.
- Ayrıntılı UI/UX stil (CSS) dosyaları: Fonksiyonel "tiyatro" dışındaki görsel stiller inceleme kapsamı dışında bırakıldı.

### DOĞRULANAMAYANLAR
- Açık bir API Key olmadığı için `scripts/verify_openrouter_catalog.py` içindeki "live OpenRouter check" atlandı (SKIP logu alındı).
- `ENABLE_MAIGRET`, `ENABLE_HOLEHE`, `ENABLE_CRAWL4AI` modülleri çalıştırılırken bağımlılık (paket) eksikliği nedeniyle lokal API `degraded` durumuna düştü. API çağrıları "available: false" veya 422 hataları ile test edilebildi ancak tam motor çalışmaları gözlemlenemedi.

### DUR ve SOR
- Göz 3'teki "rust_core Vault ignore" bug'ı için Rust tarafındaki persistance onarımı bu rapordan sonra ayrı bir PR ile mi yapılmalı, yoksa bu görev dışı (Rust ekibine ait) mı sayılmalı? Onay bekliyorum.
- Arayüz (Frontend) tarafındaki Svelte derleme çıktılarına müdahale ederek (Pillar bileşenlerinde boş veri uyarıları oluşturmak) "tiyatro" onarımı 7-B Temizlik PR'ına mı dahil edilecek, yoksa ayrı bir Feature PR'ı mı açılacak? Onay bekliyorum.

### KIRMIZI ÇİZGİ NOTU
- **Çocuk Kırmızı Çizgisi:** Kod tabanında (Örn: `agent_core/safety/minor_gate.py`) kurallar katı tanımlanmış olsa da, API uçlarında (`backend/api.py`) bu gate sistemine çağrı yapılmadığı tespit edilmiştir. Sistem mimarisinde bu kural sadece içeride (bazı modellerin içinde) zorlanıyor görünmekte; dış API sınır kapısında bu kontrolün (Middleware vb.) atlanmış olduğu ve tehlike oluşturduğu gözlemlenmiştir. (Herhangi bir düzeltme yapılmamıştır, sadece durum tespiti).
