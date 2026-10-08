---
name: sensor_company_people
description: Kurumun kendi sayfalarında YAYINLADIĞI kişi künyesi (schema.org/Person: ad + rol) ve herkese açık iletişim adresleri. Kişi avı değildir.
---

# sensor_company_people

Kurumun kendi sayfalarında YAYINLADIĞI kişi künyesi (schema.org/Person: ad + rol) ve herkese açık iletişim adresleri. Kişi avı değildir.

- **Yetenek kimliği:** `sensor.company.people`
- **Tür:** `sensor`
- **Lisans:** dahili (yalnız HTTP GET + stdlib ayrıştırma)
- **Kapılar:** ENABLE_COMPANY_TARGETING, vault

## Girdi şeması

```json
{
  "additionalProperties": false,
  "properties": {
    "subject": {
      "description": "Hedef: kullanıcı adı, e-posta, URL ya da yeteneğin beklediği metin (CapabilityContext.subject sözleşmesi).",
      "type": "string"
    }
  },
  "required": [
    "subject"
  ],
  "type": "object"
}
```

## MCP ile çağrı

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "sensor_company_people",
    "arguments": {
      "subject": "<hedef>"
    },
    "_meta": {
      "io.modelcontextprotocol/protocolVersion": "2026-07-28"
    }
  }
}
```

## Dürüstlük sözleşmesi

- Kapılar kapalıysa (kasa kilitli, `ENABLE_*` kapalı, hız sınırı dolu) yetenek **koşmaz**; çağrı `isError: true` ve makine-okunur sebeple döner.
- Kanıt üretilmediyse sonuç başarı sayılmaz: `structuredContent.ok` yalnız kanıt varsa `true` olur.
- Bu dosya `scripts/export_skills.py` tarafından defterden üretilir; elle düzenlenmez (bayat paket CI'da yakalanır).
