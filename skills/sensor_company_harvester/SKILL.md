---
name: sensor_company_harvester
description: Kurum/alan adı hedefi: arama motorlarından e-posta, alt alan adı, IP ve URL toplar (theHarvester). Araç yoksa dürüstçe kapalıdır.
---

# sensor_company_harvester

Kurum/alan adı hedefi: arama motorlarından e-posta, alt alan adı, IP ve URL toplar (theHarvester). Araç yoksa dürüstçe kapalıdır.

- **Yetenek kimliği:** `sensor.company.harvester`
- **Tür:** `sensor`
- **Lisans:** GPL-2.0 (harici CLI — kod gömülmez)
- **Kapılar:** ENABLE_COMPANY_TARGETING, rate, vault

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
    "name": "sensor_company_harvester",
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
