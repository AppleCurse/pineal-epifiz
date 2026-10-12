# PINEAL MCP — yetenekler standart kapıdan dışarıda

> FAZ D · D1 · 2026-10-07
> Bu belge, Pineal'in yeteneklerini **Model Context Protocol** üzerinden başka
> araçlara (Claude Desktop, kendi ajanlarınız, betikler) açan sunucuyu anlatır.

## 1 · Ne var, ne yok

**Var:** ``CapabilityRegistry``deki her yetenek, MCP **aracı** olarak yayınlanır;
çağrılar ``CapabilityRunner`` üzerinden koşar. Yani dışarıdan gelen çağrı,
içerideki bir çağrıyla **aynı mandallardan** geçer:

```
çocuk kilidi → politika kapıları (vault · budget · rate · ENABLE_*) →
availability → run() → EvidenceItem
```

Ayrı bir "dış yol" yoktur; ayrı yol ayrı gerçek olurdu.

**Yok (dürüst sınırlar):**

- Kaynak/istem (``resources``/``prompts``) ilan EDİLMEZ. İlan edilmeyen ilkel
  için örnek ``METHOD_NOT_FOUND`` döner.
- Şu an yalnız **stdio** taşıması vardır; ağ üzerinden HTTP taşıması yoktur.
- Yaş sinyali UYDURULMAZ: bir hedefin 18 altı olduğu bilgisi MCP çağrısının
  içinde yoktur (bkz. §5).

## 2 · Çalıştırma

```bash
python -m agent_core.mcp          # stdio sunucusu (MCP istemcileri bunu başlatır)
```

Claude Desktop / uyumlu istemci yapılandırması:

```json
{
  "mcpServers": {
    "pineal": {
      "command": "python",
      "args": ["-m", "agent_core.mcp"],
      "cwd": "/tam/yol/pineal-epifiz",
      "env": {
        "PINEAL_API_URL": "http://127.0.0.1:8000",
        "PINEAL_MCP_CLIENT_ID": "operator"
      }
    }
  }
}
```

**Ön koşul:** Pineal API'si çalışıyor olmalıdır — kasa mandalının sahibi odur.
API kapalıysa sunucu yine açılır ama mandal **kilitli** sayılır (fail-closed):
hiçbir yetenek koşmaz, sebep dürüstçe döner.

## 3 · Protokol sürümleri

MCP'nin güncel sürümü **2026-07-28**'dir ve protokol artık **stateless**'tır:
``initialize`` el sıkışması kaldırılmış, sürüm her isteğin ``_meta``'sında
taşınmaktadır. Eski istemciler el sıkışma konuşmaya devam eder. Bu sunucu
**ikisini birlikte** destekler:

| İstemci tipi | Nasıl konuşur | Sunucu davranışı |
|---|---|---|
| 2026-07-28 (stateless) | Her istekte ``params._meta["io.modelcontextprotocol/protocolVersion"]`` | El sıkışma GEREKMEZ; ``server/discover`` ile keşif |
| 2025-11-25 ve öncesi | ``initialize`` → ``notifications/initialized`` | El sıkışma yanıtlanır; sürüm aynen onaylanır |
| Bilinmeyen sürüm (legacy) | ``initialize`` | Sunucu KENDİ desteklediği en yeni sürümü döner; istemci kabul etmezse bağlantıyı kapatır |
| Bilinmeyen sürüm (stateless) | ``_meta`` sürümü | ``-32022`` + desteklenen sürüm listesi (gizlenmez) |

Desteklenen sürümler: ``2026-07-28`` · ``2025-11-25`` · ``2025-06-18`` ·
``2025-03-26`` · ``2024-11-05``.

Yöntemler: ``server/discover`` · ``tools/list`` · ``tools/call`` · ``ping`` ·
``logging/setLevel`` · ``notifications/initialized`` · ``notifications/cancelled``.

## 4 · Araçlar

| Araç | Kaynak | Not |
|---|---|---|
| ``pineal_status`` | sunucunun kendisi | Envanter + her yeteneğin ŞU AN koşup koşamadığı. **Kanıt üretmez.** |
| ``<yetenek_kimliği>`` (noktalar ``_``) | ``CapabilityRegistry`` | Örn. ``sensor.identity.maigret`` → ``sensor_identity_maigret`` |

- Liste her istekte defterden türetilir: **bayat liste yoktur**. Deftere yetenek
  eklenince araç listesi kendiliğinden büyür.
- Sıra deterministiktir (istemci önbelleği + prompt önbelleği için).
- Ad dönüşümü birebir değildir; çakışma olursa sunucu gürültülü hata verir
  (sessizce bir yeteneğin üstüne yazmaz).

### Girdi şeması

Yetenek kendi şemasını ``mcp_input_schema`` ile beyan eder; beyan yoksa
sözleşme varsayılanı geçerlidir:

```json
{"type": "object", "properties": {"subject": {"type": "string"}}, "required": ["subject"]}
```

Eşleme kuralı: ``subject`` → ``CapabilityContext.subject``, kalan argümanlar →
``CapabilityContext.params``.

## 5 · Dürüstlük sözleşmesi (çağrı davranışı)

Bir çağrı **reddedilirse** sonuç ``isError: true`` döner ve sebep
makine-okunurdur:

```json
{
  "content": [{"type": "text", "text": "extractor.text.language: KOŞMADI — policy:vault_locked\nreddeden kapı: vault"}],
  "isError": true,
  "structuredContent": {
    "capability_id": "extractor.text.language",
    "available": false, "ok": false,
    "unavailable_reason": "policy:vault_locked", "denied_by": "vault",
    "evidence_count": 0, "evidence_ids": []
  }
}
```

Kurallar:

1. **Kanıtsız iddia yok.** ``structuredContent.ok`` yalnız ``available`` +
   hata yok + en az bir ``EvidenceItem`` ise ``true``'dur.
2. **Sebep gizlenmez.** ``denied_by`` hangi kapının reddettiğini, ``error``
   koşu hatasını, ``unavailable_reason`` uygunluk sebebini taşır.
3. **Kasa tek kaynaktan.** Sunucu, kasa durumunu çalışan Pineal API'sinden
   (``GET /api/vault/status``) okur. Adres **yalnız yerel** olabilir; uzak
   adres reddedilir, yönlendirmeler takip EDİLMEZ. API'ye ulaşılamıyorsa
   kasa KİLİTLİ sayılır.
4. **Hız sınırı.** Araç başına kayan pencere (varsayılan 20 çağrı / 60 sn).
   Sınır dolduysa yetenek HİÇ koşmaz: ``denied_by: "rate"``.
5. **Kırpma gizlenmez.** Uzun kanıt kırpılırsa ``structuredContent.truncated``
   işaretlenir; kanıt kimlikleri (``ev_…``) her koşulda döner.
6. **Sürüm dürüstlüğü.** ``structuredContent`` 2025-06-18 ve sonrası
   istemcilere, ``resultType`` yalnız 2026-07-28 istemcilerine gönderilir.

### Çocuk kırmızı çizgisi (Tüzük Md.4/A)

MCP katmanı **yaş sinyali üretmez**. Operatör bir hedefin 18 altı olduğunu
``PINEAL_MCP_MINOR_SUBJECTS`` ile **beyan ederse** o hedef MCP yolunda
kilitlenir: vaka bağlamı (aile bilgisi, doğrulama, konsorsiyum onayı)
taşınmadığı için ``MinorGate`` reddeder ve sonuç ``denied_by: "minor_safe"``
olur. Beyan "izin" değil **"dur"** demektir; tam vaka yalnız normal operatör
akışından açılabilir.

## 6 · Ortam değişkenleri

| Değişken | Varsayılan | Anlam |
|---|---|---|
| ``PINEAL_API_URL`` | ``http://127.0.0.1:8000`` | Kasa durumunun okunduğu API. YALNIZ yerel adres. |
| ``PINEAL_MCP_CLIENT_ID`` | ``default`` | Kasa odası (operatör oturumu). |
| ``PINEAL_MCP_RATE_LIMIT`` | ``20`` | Araç başına pencere içi çağrı tavanı. |
| ``PINEAL_MCP_RATE_WINDOW`` | ``60`` | Pencere (saniye). |
| ``PINEAL_MCP_MINOR_SUBJECTS`` | boş | Virgülle ayrılmış çocuk beyanı (bkz. §5). |
| ``ENABLE_*`` | kapalı | Yetenek kapıları; ``pineal_status`` hangisinin neden kapalı olduğunu yazar. |

## 7 · Skills paketi

Aynı defterden bir **Agent Skills** paketi üretilir (her yetenek için
``skills/<araç_adı>/SKILL.md``):

```bash
python scripts/export_skills.py           # üret (idempotent)
python scripts/export_skills.py --check   # tazelik denetimi (bayatsa exit 3)
```

Paket deterministiktir (zaman damgası yok) ve defterle uyuşmalıdır: elle
düzenlenmiş ya da defterde olmayan bir yeteneğin dosyası CI'da yakalanır.

## 8 · Durum ucu (kokpit)

```bash
curl -s "http://127.0.0.1:8000/api/mcp/status?client_id=default" | python -m json.tool
```

Dönen alanlar: ``available`` · ``transport`` · ``command`` · ``capabilities`` ·
``tools`` · ``protocol_current`` · ``protocol_supported`` · ``vault_locked`` ·
``rate_limit``. Sayılar defterden okunur; uç **hiçbir yeteneği koşturmaz**.
Kokpitte **MCP** pili bu gerçeği gösterir: ``MCP: 16 ARAÇ · AÇIK`` ya da
``MCP: 16 ARAÇ · KİLİTLİ``.

## 9 · Sınama

```bash
pytest tests/unit/test_mcp_protocol.py tests/unit/test_mcp_tools.py \
       tests/unit/test_mcp_results.py tests/unit/test_mcp_server.py \
       tests/unit/test_mcp_state_bridge.py tests/unit/test_export_skills.py \
       tests/integration/test_mcp_server_stdio.py -q
```

Entegrasyon testi sunucuyu **gerçek bir alt süreç** olarak başlatır, stdio
üzerinden konuşur ve yalnız kasa cevabını taklit eder — ölçülen şeyin kendisi
(sevkiyat + mandallar) taklit edilmez.
