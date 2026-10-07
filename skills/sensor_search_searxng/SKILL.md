---
name: sensor_search_searxng
description: Anahtarsız metasearch; arama maliyetini ve sağlayıcı bağımlılığını kırar.
---

# sensor_search_searxng

Anahtarsız metasearch; arama maliyetini ve sağlayıcı bağımlılığını kırar.

- **Yetenek kimliği:** `sensor.search.searxng`
- **Tür:** `sensor`
- **Lisans:** AGPL-3.0 (ayrı servis — kod gömülmez, HTTP ile çağrılır)
- **Kapılar:** ENABLE_SEARXNG, vault

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
    "name": "sensor_search_searxng",
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
