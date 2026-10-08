# P0 — Personal Baseline Infrastructure

**Tarih:** 2026-09-26

**Durum:** Kapsam kayda alındı · tasarım/onay aşaması · uygulama başlamadı

**Amaç:** Bir hedefe ait, tekrarlı görevlerden gelen zaman damgalı kaynak gözlemlerini izlenebilir biçimde biriktirecek altyapıyı tanımlamak. P0, tek başına baseline hesaplamaz ve “normalden sapma” kararı üretmez.

## Kapsam

1. **Hedefe bağlı kimlik** — Görevler arasında aynı hedefi güvenilir ve doğru yetki sınırında tanıyacak bir kimlik sözleşmesi.
2. **Çapraz-görev post corpus’u** — Tek görevin raporundan ayrı, kaynak gönderi gözlemlerinin tekrar eden yakalamalar boyunca ilişkilendirilebildiği bir kayıt yolu.
3. **Saklama ve silme kuralları** — Kaynak ve türetilmiş kayıtların ne kadar tutulacağı, nasıl silineceği ve silmenin hangi bağlı depolara uygulanacağı.
4. **Tekrar kazıma ve tekilleştirme** — Aynı kaynağın tekrar yakalanmasını tanıma; kaynak gönderisini farklılaştırma ile gönderinin zaman içinde değişebilen ölçümlerini (ör. beğeni/yorum sayısı) ayrı ele alma.
5. **Provenance manifest** — Her yakalama için kaynağın, kapsamın, zamanların, sınırların ve eksikliklerin denetlenebilir kaydı.

## P0 için kabul ölçütleri

- Görev kimliği, hedef kimliği yerine kullanılmaz. Görevler arası bağ ancak hedef eşlemesi açıkça çözüldüğünde ve izin sınırı içinde kurulur.
- Kaynak post kimliği, kaynakta gerçekten varsa taşınır. Kaynak-native kimlik yoksa yalnız metin veya timestamp’ten kesin post kimliği türetilmez; eşleşemeyen kayıt belirsizliğiyle tutulur ve baseline girdisi sayılması ayrıca engellenebilir.
- **Kaynakta yayınlanma zamanı** ile **sistemin yakalama zamanı** ayrı alanlar/semantikler olarak korunur. Hangi timestamp’in hangi kaynak alanından ya da fallback yönteminden geldiği manifestte kaydedilir; bilinmeyen değer uydurulmaz.
- Her yakalama için istenen/alınan örnek kapsamı ve sınırlamalar kaydedilir: platform/kaynak, yakalama zamanı, scraper/şema sürümü, örnekleme veya sayfa sınırı, alınan ve tarihli kayıt sayıları, zaman penceresi, eksik alanlar ve varsa kaynağın verdiği toplam sayı.
- Aynı post yeniden görüldüğünde post kimliği tekilleştirilir; farklı yakalama zamanlarında değişebilen metrikler geçmiş gözlem olarak korunur veya ayrı bir tarihçe kuralına bağlanır. Sonraki değer, önceki ölçümü sessizce silmez.
- Farklı kullanıcı/tenant kapsamındaki hedef verileri birbirine karışmaz. Okuma, yazma ve silme işlemleri denetlenebilir olur.
- Saklama süresi dolduğunda veya silme isteği geldiğinde kaynak kayıtları ve onlara bağlı türetilmiş kayıtlar belirlenmiş kapsamda silinir; başarısız alt-silme sessiz başarı sayılmaz.
- Corpus eksik, kaynağı belirsiz veya kimliği eşleşmeyen kayıtlar içeriyorsa bu durum görünür kalır. Yetersiz veri baseline olarak sunulmaz.

## P0’ın dışındaki işler

- Kişinin “normal” davranışını hesaplama veya baseline-deviation skoru üretme.
- Seismos’taki aynı-örneklem medyanını kişisel tarihsel baseline’a dönüştürme.
- Eksik kayıtlardan post/timestamp/source ID tahmin etme.
- Psikolojik, klinik veya yaşamsal neden çıkarımı.
- Baseline’a dayanarak mesaj veya strateji üretme.

P0 tamamlanıp gerçek, izinli, hedefe bağlı corpus birikmeden “normalden sapma” iddiası kapalı kalır. P0’ın varlığı tek başına baseline yeterliliği anlamına gelmez; metrik bazında minimum kapsam ve zaman aralığı eşikleri ayrı bir sonraki karardır.

## Mevcut mimariyle sınır

- `CanonicalMemory` kanıt/rapor zincirini `task_id` bazında saklar. Bu, hedefe göre anahtarlanmış kaynak-post geçmişi değildir.
- `HindsightMemory`’nin semantic index’i de mevcut akışta `task_id` ile bağlıdır; kaynak doğruluğu ve tekrarlı post tekilleştirmesi için baseline source-of-truth olarak kullanılmamalıdır.
- Mevcut `target_profile` içindeki `shortcode`, profil toplam post sayısı ve `platform` alanları üretim eşlemesinde taşınmadığı için P0 öncesinde bu provenance boşluklarının tasarımda ele alınması gerekir.
- P0 kaynak gözlemlerinin kalıcı deposudur; P7 raporları ve görev kanıt zinciri türetilmiş analiz olarak ayrı kalır. Görev raporu, ham/tekrarlı kaynak corpus’un yerine geçmez.

## Uygulamadan önce açıkça kararlaştırılması gerekenler

1. **İzin ve amaç:** Hangi yetki/onayla hedef profili görevler arasında saklanabilir? Saklama amacı tam olarak nedir?
2. **Hedef kimliği:** Hangi platform kimliği kullanılacak; kullanıcı adı değişikliği, hesap taşıma veya kimlik belirsizliği nasıl ele alınacak? Kimlik hangi tenant/operatör alanında benzersiz olacak?
3. **Saklama ve silme:** Süreler; ham caption/metadata saklama kapsamı; türetilmiş rapor, önbellek, yedek ve silme doğrulaması.
4. **Yakalama kapsamı:** Mevcut 12-post sınırı mı kalacak, yoksa kaynakta izinli başka bir toplama biçimi mi var? Her görevde ne sıklıkla tekrar yakalanacak?
5. **Tekilleştirme ve değişen metrikler:** Kaynak ID’si bulunmayan kayıtların davranışı; düzenlenen/silinen postlar; değişen like/comment sayılarının gözlem modeli.
6. **Baseline yeterliliği:** Her metrik için gerekli minimum tarih aralığı, timestamp kapsamı ve kaynak sayısı. Bu eşikler P0’ın verisi görülmeden varsayılmamalı.
7. **Depolama/güvenlik:** Tenant izolasyonu, erişim denetimi, şifreleme, migration ve eşzamanlı yazma/okuma gereksinimleri.

## Aşama sınırı

- **C (daraltılmış kapsam):** Mevcut tek görev örneklemi içindeki ölçülebilir değişim ve corpus kapsamı; “kişisel baseline” veya “normalden sapma” iddiası yok.
- **P0:** Yukarıdaki veri yaşam döngüsü altyapısı. Bu belge yalnız kapsamı ve karar kapılarını kaydeder; kod/schema/DB oluşturmaz.
- **Daha sonraki baseline aşaması:** Yalnızca P0’ın gerçekten biriktirdiği veri kapsamı doğrulandıktan ve ölçütler tanımlandıktan sonra değerlendirilir.
