# 17 kapı denetimi

Python: `/home/user/pineal-epifiz/.venv/bin/python`

Bayrak/paket/import/preflight/test/canlı yürütme ayrı kanıtlardır. Kasa ve oran sınırı aşılmadı.
Bilinmeyen oran sınırı `null` olarak kalır; sıfır veya uygun kabul edilmez.

| Kapı | Bayrak | Paket | CLI | Servis | Kimlik | Depo testi | Karar | Engel / doğrulama boşluğu |
|---|---|---|---|---|---|---|---|---|
| ENABLE_MAIGRET | False | GEÇTİ | NOT_REQUIRED | YAPILAMADI | — | GEÇTİ | YAPILAMADI | gate_disabled, vault_locked, policy:vault_locked, live_target_not_verified |
| ENABLE_CROSS_PLATFORM | False | — | NOT_REQUIRED | YAPILAMADI | — | GEÇTİ | YAPILAMADI | gate_disabled, vault_locked, policy:vault_locked, live_target_not_verified |
| ENABLE_HOLEHE | False | GEÇTİ | NOT_REQUIRED | YAPILAMADI | — | GEÇTİ | YAPILAMADI | gate_disabled, vault_locked, policy:vault_locked, live_target_not_verified |
| ENABLE_CRAWL4AI | False | GEÇTİ | NOT_REQUIRED | YAPILAMADI | — | GEÇTİ | YAPILAMADI | gate_disabled, vault_locked, policy:vault_locked, live_target_not_verified |
| ENABLE_SCRAPLING | False | GEÇTİ | NOT_REQUIRED | YAPILAMADI | — | GEÇTİ | YAPILAMADI | gate_disabled, vault_locked, policy:vault_locked, live_target_not_verified |
| ENABLE_X_SENSOR | False | GEÇTİ | NOT_REQUIRED | YAPILAMADI | — | GEÇTİ | YAPILAMADI | no_session_pool, gate_disabled, vault_locked, policy:vault_locked, live_target_not_verified |
| ENABLE_IG_SECONDARY | False | GEÇTİ | NOT_REQUIRED | YAPILAMADI | KALDI | GEÇTİ | YAPILAMADI | gate_disabled, vault_locked, policy:vault_locked, identity_or_model_config_missing, live_target_not_verified |
| ENABLE_AGENT_REACH | False | — | KALDI | YAPILAMADI | — | GEÇTİ | YAPILAMADI | gate_disabled, vault_locked, policy:vault_locked, command_not_found:agent-reach, live_target_not_verified |
| ENABLE_SEARXNG | False | — | NOT_REQUIRED | YAPILAMADI | — | GEÇTİ | YAPILAMADI | gate_disabled, vault_locked, policy:vault_locked, service_endpoint_not_verified |
| ENABLE_LOCAL_TRANSLATE | False | — | KALDI | YAPILAMADI | — | GEÇTİ | YAPILAMADI | gate_disabled, vault_locked, policy:vault_locked, command_not_found:trans, service_endpoint_not_verified |
| ENABLE_LOCAL_JURY | False | — | NOT_REQUIRED | YAPILAMADI | KALDI | GEÇTİ | YAPILAMADI | gate_disabled, vault_locked, policy:vault_locked, identity_or_model_config_missing, service_endpoint_not_verified |
| ENABLE_COMPANY_TARGETING | False | — | KALDI | YAPILAMADI | — | GEÇTİ | YAPILAMADI | gate_disabled, vault_locked, policy:vault_locked, command_not_found:theHarvester, live_target_not_verified |
| ENABLE_REPORT_FACTORY | False | GEÇTİ | GEÇTİ | YAPILAMADI | — | GEÇTİ | YAPILAMADI | gate_disabled, vault_locked, policy:vault_locked |
| ENABLE_INTERPRETER | False | KALDI | NOT_REQUIRED | YAPILAMADI | — | GEÇTİ | YAPILAMADI | gate_disabled, vault_locked, no_registered_capability, package_probe_failed |
| ENABLE_MEDIA_FORENSICS | False | GEÇTİ | GEÇTİ | YAPILAMADI | — | GEÇTİ | YAPILAMADI | gate_disabled, vault_locked, policy:vault_locked, service_endpoint_not_verified, live_platform_download_not_verified |
| ENABLE_LOCAL_TTS | False | — | KALDI | YAPILAMADI | KALDI | GEÇTİ | YAPILAMADI | gate_disabled, vault_locked, policy:vault_locked, command_not_found:piper, identity_or_model_config_missing, service_endpoint_not_verified |
| ENABLE_LOCAL_STT | False | — | KALDI | YAPILAMADI | — | GEÇTİ | YAPILAMADI | gate_disabled, vault_locked, policy:vault_locked, command_not_found:whisper, service_endpoint_not_verified |

Ham komutlar, çıkış kodları ve tam çıktılar `audit.json` ve yanındaki log dosyalarındadır.
Depo testleri fixture içerebilir; canlı servis/hedef başarısı kanıtlamaz.
