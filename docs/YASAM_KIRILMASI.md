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
                                                     deviation_detector (sapma + confound kaydı)
                                                               ↓  DeviationFinding → EvidenceItem
                                                     cluster_analyzer (3+ bağımsız eksen, kalıcılık, rebound)
                                                               ↓  RuptureCluster
                                                     report (life-rupture-v1, mühürlü zaman çizelgesi)
```

Tek giriş noktası: `agent_core.lifecycle.pipeline.analyze_life_rupture(...)`.
Fonksiyon **asla hata fırlatmaz**; durumu raporlar:

| Durum | Anlamı |
| --- | --- |
| `INSUFFICIENT_DATA` | Tarihli gözlem üretilemedi; sapma iddiası kurulmadı. |
| `INSUFFICIENT_BASELINE` | Baseline penceresinde güvenilir sinyal yok. |
| `NO_RUPTURE` | Ölçüm yapıldı, kalıcı/çok eksenli sapma bulunmadı. |
| `RUPTURE_CONFIRMED` | Aynı pencerede 3+ bağımsız eksende kalıcı sapma. |
| `RUPTURE_CONFOUNDED_BY_MEDIUM_CHANGE` | Sapma var ama üretim biçimi de değişti; mekân/bakış eksenleri yaşam değişimi olarak OKUNAMAZ. |

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
beden eksenlerine asla sızmaz. Aynı pencerede kurgu oranı 0.5'i aşarsa küme
"confounded" ilan edilir ve `confounded_axes` alanı hangi eksenlerin
okunamaz olduğunu söyler.

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
* **Bağımsızlık şarttır.** Aynı ailedeki üç sinyal üç eksen değildir; baseline'da
  |r| ≥ 0.8 olan aileler tek eksen sayılır. 7-sütun kanıtı küme sayısına
  eklenmez (`prior_pillar_counts_toward_cluster = false`).
* **Rebound küme düşürür.** Sapma sonra normale dönüyorsa "kalıcı" denmez.

## Henüz yapılmayanlar (dürüst boşluklar)

* `vision_analyzer` şu an **tarihli kare** üretmiyor: `frames` alanı boş
  geldiğinde `ritual`, `habitat`, `gaze` eksenleri `suppressed` olur ve rapor
  bunu gerekçesiyle yazar. Gerçek çıkarım için `VisualFrameRecord` üreten bir
  kare hattı gerekir.
* Bakış/bedensel ölçümler (FaceMesh + solvePnP) bu katmanda tüketilmeye hazır
  ama üretilmiyor. 2B kutu türevi "baş eğimi" gibi uydurma metrikler bilerek
  desteklenmez.
