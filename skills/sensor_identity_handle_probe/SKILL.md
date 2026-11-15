---
name: sensor_identity_handle_probe
description: Kullanıcı adını Instagram/Facebook/Threads/X/TikTok/GitHub/Reddit/Pinterest/YouTube/Telegram profil adreslerinde yoklar; 404/410 dışındaki her belirsizlik 'unknown' raporlanır.
---

# sensor_identity_handle_probe

Kullanıcı adını Instagram/Facebook/Threads/X/TikTok/GitHub/Reddit/Pinterest/YouTube/Telegram profil adreslerinde yoklar; 404/410 dışındaki her belirsizlik 'unknown' raporlanır.

- **Yetenek kimliği:** `sensor.identity.handle_probe`
- **Tür:** `sensor`
- **Lisans:** native
- **Kapılar:** ENABLE_CROSS_PLATFORM, vault

## Girdi şeması

```json
{
  "additionalProperties": false,
  "properties": {
    "audio": {
      "type": "string"
    },
    "audio_base64": {
      "type": "string"
    },
    "auto_bridge": {
      "type": "boolean"
    },
    "channels": {
      "type": "array"
    },
    "claim": {
      "type": "string"
    },
    "evidence": {
      "type": "array"
    },
    "language": {
      "type": "string"
    },
    "limit": {
      "type": "integer"
    },
    "max_chars": {
      "type": "integer"
    },
    "max_pages": {
      "type": "integer"
    },
    "path": {
      "type": "string"
    },
    "rate": {
      "type": "number"
    },
    "report": {
      "type": "string"
    },
    "sample_every": {
      "type": "integer"
    },
    "sources": {
      "type": "string"
    },
    "subject": {
      "description": "Hedef: kullanıcı adı, e-posta, URL ya da yeteneğin beklediği metin (CapabilityContext.subject sözleşmesi).",
      "type": "string"
    },
    "suffix": {
      "type": "string"
    },
    "target": {
      "type": "string"
    },
    "text": {
      "type": "string"
    },
    "title": {
      "type": "string"
    },
    "top_k": {
      "type": "integer"
    },
    "voice": {
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
    "name": "sensor_identity_handle_probe",
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
