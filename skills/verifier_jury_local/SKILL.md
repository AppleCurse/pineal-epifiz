---
name: verifier_jury_local
description: Aynı iddia ve kanıtı birden çok YEREL modelde bağımsız oylar; oybirliği ya da yeter sayılı çoğunluk karar olur. Uzak uç reddedilir; motor yoksa karar UYDURULMAZ.
---

# verifier_jury_local

Aynı iddia ve kanıtı birden çok YEREL modelde bağımsız oylar; oybirliği ya da yeter sayılı çoğunluk karar olur. Uzak uç reddedilir; motor yoksa karar UYDURULMAZ.

- **Yetenek kimliği:** `verifier.jury.local`
- **Tür:** `verifier`
- **Lisans:** yerel uç (ollama/llama.cpp/vLLM); kod gömülmez
- **Kapılar:** ENABLE_LOCAL_JURY, vault

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
    "name": "verifier_jury_local",
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
