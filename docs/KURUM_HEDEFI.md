# KURUM HEDEFİ — şirket/kuruluş/alan adı taraması

> FAZ D · D6 · 2026-10-07
> Kişi hedefinin yanında **kurum** hedefi: theHarvester + açık SEO + kurumun
> kendi yayınladığı kişi künyesi.

## 1 · Üç mod

| Mod | Yetenek | Ne üretir | Kaynak |
|---|---|---|---|
| `harvester` | `sensor.company.harvester` | e-posta · alt alan adı · IP · URL · arama motorlarında görünen kişi satırları | theHarvester CLI (GPL-2.0, ayrı süreç) |
| `seo` | `sensor.company.seo` | robots.txt · sitemap.xml · ana sayfa başlık/açıklama/dil/canonical · security.txt · sunucu/HSTS/CSP başlıkları | yalnız kurumun KENDİ dosyaları (HTTP GET) |
| `people` | `sensor.company.people` | kurumun kendi sayfalarındaki **schema.org/Person** kayıtları (ad + rol) ve herkese açık `mailto:` adresleri | kurumun kendi sayfaları |

**Kişi avı değildir**: ad/rol dışında hiçbir kişisel alan toplanmaz, profilleme
yapılmaz, LinkedIn kazınmaz. Her satır kaynak URL'siyle kanıt olur.

## 2 · Kurulum

```bash
pip install theHarvester            # ya da: pipx install theHarvester
export ENABLE_COMPANY_TARGETING=1
python -m uvicorn backend.api:app --port 8000
```

theHarvester PATH'te değilse tam komut verilebilir:

```bash
export PINEAL_HARVESTER_CMD="/opt/theHarvester/theHarvester.py"
export PINEAL_HARVESTER_SOURCES="duckduckgo,crtsh,bing"   # varsayılan
```

Kokpitte **KURUM** pili kaç modun hazır olduğunu gösterir; kapı kapalıysa
`KURUM: KAPALI` yazar (uydurma "hazır" göstergesi yoktur).

## 3 · Dürüstlük sözleşmesi

- **SEO puanı uydurulmaz.** Yalnız ölçülen yazılır (dosya var mı, kaç kayıt,
  hangi başlık). Harici SEO servisi çağrılmaz.
- **"Yok" iddiası yalnız kesin 404'te** (`epistemic_type="absence"`). Ağ
  hatası (timeout/refused) ne varlık ne yokluk üretir; yalnız `notes.errors`
  içinde görünür.
- **Araç yoksa ses çıkmaz**: `dependency_missing:theHarvester` (PATH'te yok)
  ya da `configured_command_not_found:PINEAL_HARVESTER_CMD` (yazılan komut
  bulunamadı). İkisi karıştırılmaz.
- **Boş tarama = yokluk kanıtı** yalnız tarama sıfır hatayla bittiğinde.
- **Kova tavanı**: kova başına 25 kanıt; aşan `truncated` ile işaretlenir
  (sessiz kırpma yok).
- **SSRF hijyeni**: hedef özel/yerel ağa çözülürse (`127.0.0.1`, `10.x`,
  `192.168.x`, `169.254.x`, `localhost`) tarama REDDEDİLİR. Yalnız operatör
  açıkça `PINEAL_COMPANY_ALLOW_PRIVATE=1` derse geçer.

## 4 · Uçlar

| Uç | Ne verir |
|---|---|
| `GET /api/company/status` | Üç modun gerçek durumu (defterden): `available` + makine-okunur `reason` + kapılar |
| `POST /api/company/scan` | `{domain, client_id, modes, limit}` → mod başına kanıt satırları (kaynak URL ile) |

Kapılar: `vault` (istisnasız) + `ENABLE_COMPANY_TARGETING` (varsayılan
**KAPALI**); `harvester` ayrıca `rate` kapısına tabidir (ağır CLI). HTTP hız
kovası: `company` (8 istek/60 sn).

## 5 · Sınama

```bash
pytest tests/unit/test_company_recon.py tests/unit/test_company_capabilities.py \
       tests/integration/test_company_api_faz_d.py -q
```

Testler gerçek yerel HTTP taklidi (robots/sitemap/meta/security.txt) ve
POSIX'te sahte theHarvester CLI kullanır; hiçbir test dış ağa çıkmaz.
