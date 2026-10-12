---
name: extractor_text_language
description: Metnin dilini deterministik ölçer (tr/en/de/es/fr/ru/az); model ve ağ yok, sinyal yoksa etiket uydurmaz.
---

# extractor_text_language

Metnin dilini deterministik ölçer (tr/en/de/es/fr/ru/az); model ve ağ yok, sinyal yoksa etiket uydurmaz.

- **Yetenek kimliği:** `extractor.text.language`
- **Tür:** `extractor`
- **Lisans:** yerel/deterministik (kod içi, harici bağımlılık yok)
- **Kapılar:** vault

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
    "name": "extractor_text_language",
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
