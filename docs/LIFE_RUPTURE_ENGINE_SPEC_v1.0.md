# Life Rupture Engine — Teknik Sözleşme

**Sürüm:** 1.0 — tasarım sözleşmesi  
**Kapsam:** Kişiye özel bir hikâye veya teşhis üretmeden, zaman içinde gözlenebilir dijital izlerdeki değişimleri tespit etmek.  
**Durum:** Tasarım şartnamesi ve onaylı referans sözleşme.

---

## 1. Amaç ve Sınırlar

Motorun tek görevi, aynı veri sahibine ait zaman damgalı gözlemlerde kişinin kendi başlangıç çizgisine göre anlamlı değişimler olup olmadığını belirlemek; yeterli kanıt varsa bu değişimlerin aynı dönemde kümelenip kümelenmediğini raporlamaktır.

Motor **şunları yapmaz**:
- Depresyon, travma, yalnızlık, yaşam standardı veya “derman kaybı” teşhisi koymaz.
- Fotoğrafta bir nesnenin görünmemesini, o nesnenin kişinin gerçek hayatından kaybolduğunun kanıtı saymaz.
- İki dönem arasındaki farktan tek başına bir neden çıkarmaz.
- Veri eksikliğini `0`, “yok” veya “değişmedi” olarak kodlamaz.
- Bir profil adı, kullanıcı adı, kişi hakkındaki ön kabul veya önceden seçilmiş bir hikâyeye göre algoritma davranışını değiştirmez.

İzin verilen sonuç, *“belirtilen veri kapsamı içinde şu sinyallerde ölçülebilir bir değişim gözlendi/gözlenmedi; kanıtın kapsamı ve sınırları şunlardır”* biçimindedir.

---

## 2. Temel Kavramlar

- **Observation (gözlem):** Kaynağa ve zamana bağlı tek ölçüm.
- **Absence (yokluk gözlemi):** Yalnızca bakılan ve ölçülebilir durumdaki bir kaynakta bir özelliğin bulunmadığının kaydı. Görsel analiz yapılamadıysa yokluk değildir (`not_measurable` != `absence`).
- **Inference (çıkarım):** Ölçümlerden hesaplanan sonuç.
- **Baseline period:** Kişinin geçmiş verilerinden çıkarılan kişisel referans dönemi.
- **Comparison period:** Baseline ile karşılaştırılan dönem.
- **Deviation:** Bir sinyalin, kendi türüne ve beyan edilmiş toleransına göre baseline'dan anlamlı farkı.
- **Persistence (kalıcılık):** Bir sapmanın yeterli gözlem sıklığı ve kapsama ile birden çok zaman diliminde devam etmesi. İlk ve son kayıt arasındaki takvim süresi tek başına kalıcılık değildir.
- **Cluster (küme):** Aynı zaman aralığında görülen, bağımsızlığı doğrulanmış yeterli sayıda sapma.
- **Confounding / medium change (karıştırıcı etken):** Görsel üretim/çekim biçimi gibi bir değişimin bazı ölçümleri karşılaştırılabilir olmaktan çıkarması.
- **Unknown (bilinmiyor):** Mevcut verinin bir hükmü desteklemeye yetmediğinin açık sonucu.

---

## 3. Veri Sözleşmesi

Her gözlem en az şu alanları taşır:
```text
SignalObservation
  signal_id: str
  timestamp: datetime
  value: numeric | categorical
  source_ref: str
  measurement_status: measured | partial | not_measurable | invalid
  signal_family: str
  provenance: optional structured source metadata
```

Her sinyal için bir `SignalSpec` gerekir:
```text
SignalSpec
  signal_id: str
  kind: binary | continuous | count | ratio | circular | categorical
  meaningful_delta: numeric
  circular_period: optional numeric
  expected_cadence: daily | weekly | monthly | event_based | configured
  family: str
  dependencies: list[str]
  eligible_axes: list[str]
```

---

## 4. Ölçülebilirlik ve Yokluk Kuralları

Ölçümün üç ayrı sonucu vardır:
1. `measured`: Kaynak başarıyla gözlendi ve metrik hesaplandı.
2. `not_measurable`: Kaynak yok, indirilemedi, analiz edilemedi ya da metrik güvenilir biçimde çıkarılamadı.
3. `partial`: Kaynağın bir bölümü ölçüldü, fakat kapsam eksik.

`0` yalnızca metriğin gerçekten ölçülmüş ve değerin sıfır olduğu durumda geçerlidir. Fotoğraf indirilemediyse veya sentetikse `visual.object.dog = 0` yazılamaz; `not_measurable` kalır.

---

## 5. Baseline Sözleşmesi ve Sabit Baseline (`spread ≈ 0`)

Sabit baseline'da standart z-skoru tanımsızdır. Sistem bunu `z=0` diye yorumlayıp değişimi yok sayamaz.
- `distance <= meaningful_delta` ise anlamlı sapma yoktur.
- `distance > meaningful_delta` ise `constant_break` yöntemiyle sapma adayı oluşur.
- Baseline güvenilir değilse `insufficient_baseline` döner; sapma hükmü verilmez.

Dairesel zaman sinyalleri (günün saati) dairesel istatistikle hesaplanır (23:30 ile 00:30'un ortalaması öğlen kabul edilmez).

---

## 6. Kalıcılık ve Süreklilik Sözleşmesi

Kalıcılık her sinyal için ayrı hesaplanır:
```text
Persistence
  first_observed_at: datetime
  last_observed_at: datetime
  observed_windows: int
  eligible_windows: int
  consecutive_deviation_windows: int
  coverage_rate: float
  longest_unobserved_gap: int
  persistence_days: int
  status: persistent | intermittent | transient | insufficient_coverage
```

- Takvim süresi tek başına kanıt değildir.
- Pencere içi en az 3 ardışık alt dilimde düzenli gözlem şarttır.

---

## 7. Bağımsız Sinyal Sayımı ve Korelasyon İlkesi

- Korelasyon matrisi yoksa veya örneklem yetersizse sinyaller bağımsız kabul **edilmez**.
- İlişki durumu `unknown` kalır; `unknown` bağımsızlık demek değildir.
- Yüksek ilişki (korelasyon > 0.5) gösteren sinyaller tek bir kanıt olarak sayılır.
- 3+ bağımsız sinyal şartı, ancak bağımsızlık açıkça kanıtlandığında (`confirmed`) sağlanmış olur.

---

## 8. Görsel Üretim Biçimi ve Karıştırıcı Etken (Confounding)

- `media.is_authored` oranı **baseline ile comparison period arasında** karşılaştırılır.
- Baseline'da da yüksekse bu durum karıştırıcı etken değildir (kişinin normalidir).
- Yalnızca hedef dönemde belirgin oran artışı varsa (`target_rate - baseline_rate > threshold`), ilgili görsel/habitat eksenleri `confounded` olarak işaretlenir.

---

## 9. Rapor Sözleşmesi

Her bulgu şunları içerir:
```text
Finding
  finding_id: str
  signal_id: str
  signal_family: str
  baseline_value: float
  observed_value: float
  direction: increase | decrease | divergence
  deviation_method: str
  persistence_days: int
  observation_count: int
  source_refs: tuple[str, ...]
  measurement_status: measured | partial | not_measurable | confounded
  contradictions: tuple[str, ...]
  limitations: tuple[str, ...]
```

Üst rapor yalnız ölçümleri özetler:
```text
LifeRuptureReport
  verdict: RUPTURE_CONFIRMED | RUPTURE_CONFOUNDED_BY_MEDIUM_CHANGE | INDEPENDENCE_UNVERIFIED | INSUFFICIENT_EVIDENCE | NO_SIGNIFICANT_CLUSTER
  findings: tuple[Finding, ...]
  window: (start, end) | None
  signal_count: int
  persistence_days: int
  continuity_ratio: float
  independence_verified: bool
  confounded_axes: tuple[str, ...]
  timeline: EvidenceTimeline
  uncertainties: tuple[str, ...]
  reason: str
```

---

## 10. Güvenli Karar Kuralı

Motor yalnız şu üç durumdan birini açıkça üretir:
1. **Ölçülebilir değişim kümesi bulundu (`RUPTURE_CONFIRMED` / `RUPTURE_CONFOUNDED_BY_MEDIUM_CHANGE`)**
2. **Yeterli veri incelendi, kuralı karşılayan küme bulunmadı (`NO_SIGNIFICANT_CLUSTER`)**
3. **Sonuç belirsiz / kanıt yetersiz (`INSUFFICIENT_EVIDENCE` / `INDEPENDENCE_UNVERIFIED`)**

**Merkez İlke:** Motor hikâye anlatmak için veri seçmez; verinin neyi desteklediğini, neyi desteklemediğini ve neyi ölçemediğini kaydeder.
