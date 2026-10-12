---
name: analyzer_media_similarity
description: Görselin algısal parmak izini (pHash) çıkarır ve yerel indekste en yakın görselleri bulur.
---

# analyzer_media_similarity

Görselin algısal parmak izini (pHash) çıkarır ve yerel indekste en yakın görselleri bulur.

- **Yetenek kimliği:** `analyzer.media.similarity`
- **Tür:** `analyzer`
- **Lisans:** OpenCV + kendi pHash uygulaması (dahili)
- **Kapılar:** ENABLE_MEDIA_FORENSICS, vault

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
    "name": "analyzer_media_similarity",
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
