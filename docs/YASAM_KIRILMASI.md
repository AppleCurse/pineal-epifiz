# Yaşam Kırılması katmanı (`agent_core/lifecycle`)

Bu katman tek bir soruya cevap verir: **kişinin kendi geçmişine göre ne değişti,
ne zaman başladı, ne kadar sürdü ve bu değişimi okuyabilir miyiz?**

Cevabın sınırı da sözleşmenin parçasıdır:

* Teşhis YOKTUR. Rapor `root_cause = "UNKNOWN"` taşır; "depresif", "mutsuz",
  "tükenmiş" gibi hiçbir yorum kökü metne giremez (testle kilitli).
* Kişiye özel kod YOKTUR. Aynı fonksiyon her özne için koşar; kişiye özel olan
  tek şey, kişinin kendi verisinden çıkan baseline'dır.
* Sabit eşik YOKTUR. "Günde 3 paylaşım normaldir" gibi bir varsayım yerine
  kişinin kendi dağılımı (merkez + yayılım) ölçülür.
* Uydurma YOKTUR. Tarihi olmayan kanıt zaman serisine çevrilmez; ölçülemeyen
  eksen "ölçüldü" diye raporlanmaz.

## Akış

```
target_profile (posts / post_times / post_evidence_types)
visual_evidence (frames: tarihli kare kayıtları)      ─┐
frequency_map (Wave-1 samples)                        ─┼→ observation_adapter
strata_map (7-sütun fosil/kayma)                      ─┘        │
                                                               ↓  list[SignalObservation]
                                                     baseline_builder (kişinin kendi normali)
                                                               ↓  BaselineProfile
                                                     medium_change (üretim biçimi BASELINE'A göre değişti mi?)
                                                               ↓  MediumChangeAssessment
                                                     deviation_detector (sapma + confound kaydı)
                                                               ↓  DeviationFinding → EvidenceItem
                                                     persistence (dilim bazlı kalıcılık: iki uç nokta yetmez)
                                                               ↓  PersistenceRecord
                                                     cluster_analyzer (3+ BAĞIMSIZ eksen, kalıcılık, rebound)
                                                               ↓  RuptureCluster (veya aday/bilinmiyor)
                                                     report (life-rupture-v1, mühürlü zaman çizelgesi)
```

Tek giriş noktası: `agent_core.lifecycle.pipeline.analyze_life_rupture(...)`.
Fonksiyon **asla hata fırlatmaz**; durumu raporlar:

| Durum | Anlamı |
| --- | --- |
| `INSUFFICIENT_DATA` | Tarihli gözlem üretilemedi; sapma iddiası kurulmadı. |
| `INSUFFICIENT_BASELINE` | Baseline penceresinde güvenilir sinyal yok. |
| `NO_RUPTURE` | Ölçüm yapıldı, kalıcı/çok eksenli sapma bulunmadı. |
| `RUPTURE_CONFIRMED` | Aynı pencerede 3+ **bağımsızlığı doğrulanmış** eksende kalıcı sapma. |
| `RUPTURE_CANDIDATE` | Çok eksenli kalıcı sapma var ama bağımsızlık DOĞRULANMADI (korelasyon ölçülemedi). Kesin küme değildir. |
| `RUPTURE_CONFOUNDED_BY_MEDIUM_CHANGE` | Sapma var ama üretim biçimi de değişti; mekân/bakış/ritüel eksenleri yaşam değişimi olarak OKUNAMAZ. |

Rapor ayrıca sözleşme §10'un beş küme durumunu `cluster_state` alanında taşır:
`DETECTED`, `CANDIDATE`, `INSUFFICIENT_EVIDENCE`, `NO_SIGNIFICANT_CLUSTER`,
`CONFOUNDED`. "Veri yetersiz" ile "değişim yok" aynı statü değildir.

## Fail-closed kuralları

1. **Eksik medya = eksik gözlem, yokluk değil.** İndirilemeyen görsel için
   "arka plan yok" denmez; sinyal hiç üretilmez ve eksen `suppressed` olarak
   gerekçesiyle raporlanır.
2. **Tarihsiz özet zaman serisi değildir.** `visual_evidence` düz (tarihsiz)
   özet taşıyorsa yalnız `none` durumu okunur; seriye sahte tarih yazılmaz ve
   teşhis defterine `undated_visual_summary_skipped` düşer.
3. **Paralel listeler hizalanmazsa reddedilir.** `len(posts) != len(post_times)`
   ise `zip` kaydırması yapılmaz; hiçbir gönderi tarihlenmez.
4. **Platform dışı satırlar dışlanır.** `post_evidence_types[i]` platform
   gönderisi değilse (arama snippet'i vb.) metin sinyaline girmez.
5. **Shortcode zamanı doğrulanır.** Instagram kısa kodu (Snowflake) medya
   kimliğidir; bildirilen tarih ±48 saatten fazla ayrışırsa kare/gönderi
   reddedilir. Bu, paralel diziler kaydığında (metin 5. gönderiye yapışmışsa)
   sessiz kaymayı yakalayan tek matematiksel kontroldür.
6. **Gelecek tarih kabul edilmez.** Şimdiden sonrası gözlem sayılmaz.
7. **`ritual.*` için 0.0 yokluktur**, "sıfır ölçtüm" değil: kanıt türü
   `absence` olur, notu da bunu söyler.

## Üretim biçimi (media provenance)

| Sınıf | Mekân (habitat) | Somatik (gaze) | Editoryal |
| --- | --- | --- | --- |
| `camera_incidental` + ölçülebilir arka plan | ✔ | ✔ | — |
| `camera_staged` (stüdyo/kurgu sahne) | ✘ | ✔ | — |
| `edited_composite` / `synthetic_or_render` | ✘ | ✘ | ✔ |
| `unknown` | ✘ | ✘ | ✘ |

Kurgulanmış/sentetik kareler **yalnız** editoryal eksene besler; mekân ve
beden eksenlerine asla sızmaz.

**Karıştırıcı etken MUTLAK oranla değil, kişinin KENDİ baseline'ıyla ölçülür:**

```
baseline_rate   = authored oranı (baseline penceresi)
comparison_rate = authored oranı (karşılaştırma penceresi)
delta           = comparison_rate − baseline_rate
status          = changed | stable | unknown
```

* `changed` (|delta| > eşik) → yalnız bu durumda habitat/bakış/ritüel eksenleri
  `confounded` işaretlenir.
* `stable` → oran **yüksek olsa da** dönemsel kayma yok; confound DEĞİL.
* `unknown` → iki taraftan birinde örneklem yetersiz; "confound yok" sonucu
  ÇIKARILAMAZ.

Eski "%50 üstü ise confound" kuralı bu yüzden kaldırıldı: her zaman yoğun kurgu
üreten bir hesabı, hiçbir şey değişmediği hâlde "değişti" diye işaretliyordu.

## Kare hattı (tarihli görsel kanıt)

`agent_core/services/frame_evidence.py` — havuzlanmış `VisualEvidence` özeti
zaman taşımaz; ondan seri üretmek sahte tarih yazmak olurdu. Bu hat her
gönderi için **tarihli** kare üretir:

```
posts / post_times / images (paralel, index hizalı)
        ↓ seçim (deterministik, maliyet tavanlı, fail-closed)
    FrameCandidate[frame_id, post_ref, observed_at, image_url]
        ↓ indirme (SSRF-güvenli, bütçe sınırlı, eşzamanlılık 4)
        ↓ yerel ölçüm (LLM YOK): parlaklık, doygunluk, kontrast,
          kenar yoğunluğu, renklilik  → 0..1 normalize
    VisualFrameRecord(data_confidence=True, capture_class="unknown")
```

İki kademe: bu hat **birinci** kademedir (0 LLM). İkinci kademe (pahalı
anlamsal analiz) yalnız `change_point_indices()` işaretlediği karelere
gider; henüz uygulanmadı, bu yüzden `detected_objects=[]` — **uydurulmaz**.

Dürüst sınırlar:

* `capture_class` = `unknown`: kamera/EXIF/üretim yazılımı kanıtı olmadan
  "gerçek çekim" demek, kurgu bir kareyi yaşam kanıtı saymak olurdu. Bu yüzden
  `habitat.*` ve `gaze.*` **kapalı** kalır.
* Ölçülen özellikler **yayınlanan karenin** özellikleridir → `media.frame_*`
  sinyalleri (editoryal eksen). "Oda karardı" yorumu bu sinyalden çıkarılmaz.
* İndirilemeyen/çözülemeyen kare **yokluk değildir**: kayıt üretilmez, sebep
  `frames_problems` altına yazılır. Bütçe aşılırsa `budget_exceeded=True` ve
  elde ne varsa o kullanılır (sahte kare eklenmez).

## Kanıt kimlikleri

`evidence_id = "ev_" + sha256("life_rupture|observed_at|kanonik_anahtar")[:20]`

Rastgelelik yoktur: aynı girdi aynı kimliği verir, aynı kimlik aynı kanıtı
gösterir. Zaman çizelgesi `agent_core.services.evidence_timeline` üzerinden
kurulur — 7-sütun kanıtlarıyla **aynı** kapıdan geçer (tek uygulama, tek sıra).

## Sinyal sözlüğü

Aileler: `timing.*`, `text.*`, `media.*`, `ritual.{obj,place}.*`, `habitat.*`,
`gaze.*`, `wave.*`, `strata.*`. Her sinyalin semantiği (binary / oran / sürekli /
saat) `default_specs.py` içinde **beyan edilmiştir**; beyan edilmeyen sinyal
baseline dışında kalır ve rapor bunu söyler (`unspecified_signals`).

Ritüel sözlüğü keşfedilir: baseline penceresinde yeterince görünen nesne/mekân
etiketleri (`ritual.obj.*`, `ritual.place.*`) sözlüğe girer ve **her tarihli
kare** için `1.0`/`0.0` üretilir. Böylece ölen bir ritüel, sözlükten düşüp
görünmez hâle gelmez.

## Kapatılan delikler (neden böyle)

* **Sabit baseline'da z-skoru anlamsızdır** (yayılım 0 → bölme). Yayılım ~0 ise
  `constant_break` kuralı işler: anlamlı fark var mı, yok mu.
* **Saat döngüseldir.** 23:30 ile 00:30'un ortalaması 12:00 değil 00:00'dır
  (birim vektör ortalaması); döngüsel sinyalde IQR kullanılmaz.
* **Uç-nokta karşılaştırması yoktur.** Tüm seri kaydırmalı pencereyle taranır;
  aksi hâlde mevsimsel dalgalanma "kırılma" sanılır.
* **Bağımsızlık şarttır — ve ölçülmelidir.** Aynı ailedeki üç sinyal üç eksen
  değildir; baseline'da |r| ≥ 0.8 olan aileler tek eksen sayılır. Korelasyon
  ÖLÇÜLEMİYORSA (sabit seri, ortak gözlem yok) sinyaller bağımsız SAYILMAZ:
  durum `unknown` olur ve küme `CANDIDATE` kalır. Eskiden `nan_to_num(..., 0.0)`
  ölçülemeyen ilişkiyi "ilişki yok" diye yazıyordu; bu kaldırıldı.
* **İki uç nokta kalıcılık değildir.** `persistence` modülü her sinyal için
  haftalık dilimlerde kapsama, kesintisiz dilim sayısı ve en uzun gözlem
  boşluğunu ölçer. 1 Ocak + 5 Mart (arada hiçbir gözlem yok) `insufficient_coverage`
  döner; `persistent` hükmü ardışık dilim + takvim yayılımı + kapsama şartlarının
  BİRLİKTE sağlanmasını ister. Eşikler `PersistenceConfig` ile beyan edilir ve
  rapora yazılır.
* **Rebound küme düşürür.** Sapma sonra normale dönüyorsa "kalıcı" denmez;
  `recoveries` bölümünde ayrıca raporlanır (geçmiş kayıt silinmez).
* **Çelişki silinmez.** Aynı ailede karşıt yönlü bulgular `contradictions`
  altında korunur.

## Rapor sözleşmesi (`life-rupture-v1`)

Her bulgu denetlenebilir bir kayıttır (`findings[]`):

```
finding_id · signal_id · signal_family
baseline_period {start, end, measured_count} · comparison_period {…}
baseline_value · observed_value · delta · direction
deviation_method · threshold_or_tolerance
persistence {status, observed_windows, consecutive_deviation_windows,
             coverage_rate, longest_unobserved_gap_days, persistence_days, config}
independence_status · measurement_status
source_refs[] · contradictions[] · alternative_explanations[] · limitations[]
```

Üst rapor ayrıca: `report_id` (kanıttan türetilir; `subject_id` ve `computed_at`
kimliği DEĞİŞTİRMEZ), `cluster_state`, `independence_assessment`,
`medium_change_assessment`, `data_coverage[]`, `contradictions[]`,
`recoveries[]`, `unknowns[]`, `excluded_evidence[]`, `decision_summary`.

`decision_summary` yalnız ölçümü özetler; "kişi yalnızlaştı" gibi kanıtlanmamış
bir sonuç üretmez.

## Testler: mutasyon ve sözleşme bekçileri

`tests/lifecycle/` altındaki dosyalar yalnız "yeşil" değil, **ısırdığını
kanıtlayan** testler içerir:

| Dosya | Kilitlediği |
| --- | --- |
| `test_lifecycle_baseline.py` | kişisel baseline matematiği, sabit baseline, dairesel saat |
| `test_lifecycle_adapter.py` | kayma/sızıntı/tarih/çorba fail-closed kuralları, shortcode |
| `test_lifecycle_media_provenance.py` | eksen yönlendirmesi (habitat/somatik/editoryal) |
| `test_lifecycle_ig_time.py` | Snowflake çözümü ve sapma toleransı |
| `test_lifecycle_persistence.py` | dilim kapsaması, iki uç nokta, boşluk, kesintisizlik |
| `test_lifecycle_medium_change.py` | yüksek-sabit oran, dönemsel kayma, ölçülemez durum |
| `test_lifecycle_deviation_detector.py` | deterministik kimlik, yokluk türü, yapısal confound |
| `test_lifecycle_cluster_analyzer.py` | kalıcılık, bağımsızlık dürüstlüğü, confound, rebound |
| `test_lifecycle_pipeline.py` | durum makinesi, `CANDIDATE`, denetlenebilir bulgu, determinizm |
| `test_lifecycle_mutations.py` | dört davranış mutasyonu + sinyal adı kayması STATİK kontrolü |

Mutasyon testleri gerçek davranışı bozar ve ilgili değişmezin kırıldığını
gösterir: (a) sabit baseline toleransı, (b) korelasyon yokken bağımsızlık,
(c) authored oranın baseline ile karşılaştırılması, (d) ölçülemez karenin
sıfır sayılması. Beşinci kontrol statiktir: paket içinde geçen her sinyal adı
`default_specs` içinde çözülmek zorundadır — `media.is_authored` gibi bir
kısaltma sessizce ölçüm dışında kalamaz.

## Henüz yapılmayanlar (dürüst boşluklar)

* **İkinci kademe anlamsal analiz yok.** Kare hattı yerel ölçümü üretiyor ama
  nesne/mekân etiketleri (ritüel sözlüğünün girdisi) ve yüz/bakış ölçümleri
  üretilmiyor. Bu yüzden `ritual.*`, `habitat.*`, `gaze.*` eksenleri hâlâ
  `suppressed` ve rapor bunu gerekçesiyle yazıyor. Değişim noktaları
  (`change_point_indices`) hesaplanıyor; pahalı analiz oraya yönlendirilecek.
* Bakış/bedensel ölçümler (FaceMesh + solvePnP) tüketilmeye hazır ama
  üretilmiyor. 2B kutu türevi "baş eğimi" gibi uydurma metrikler bilerek
  desteklenmez.
* Çok turlu soruşturma döngüsü (`InvestigationLoop`) yok: ajanlar hâlâ tek
  geçişte koşuyor. Kare hattı, o döngünün ikinci turda kazacağı zamanlı veriyi
  önce üretir — sıra bu yüzden böyleydi.
