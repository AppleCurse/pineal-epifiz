---
name: sensor_identity_phone_probe
description: Telefon numarasını E.164 standardına çevirir, operatör/şebeke ve hat türünü çözümler, WhatsApp/Telegram doğrudan varlık protokollerini ve açık web dijital ayak izini tarar.
---

# sensor_identity_phone_probe

Telefon numarasını E.164 standardına çevirir, operatör/şebeke ve hat türünü çözümler, WhatsApp/Telegram doğrudan varlık protokollerini ve açık web dijital ayak izini tarar.

- **Yetenek kimliği:** `sensor.identity.phone_probe`
- **Tür:** `sensor`
- **Lisans:** native
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
    "name": "sensor_identity_phone_probe",
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
