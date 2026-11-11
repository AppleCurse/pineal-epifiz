---
title: "Pineal Audit Core A - agents aspasia chat domain engines"
tags: [pineal, audit]
status: active
created: 2026-11-09
---

# Pineal Audit Core A (`agent_core/{agents,aspasia,chat,domain,engines}`)

- **Hedef Repo:** `C:\Projects\pineal-epifiz` (`HEAD 61c414c5`, `3.0.0-rc.2`)
- **Kapsam:** `agent_core/agents/` (15 modül), `agent_core/aspasia/` (3 modül), `agent_core/chat/` (1 modül), `agent_core/domain/` (10 modül), `agent_core/engines/` (10 dosya / 8 motor + spektrum + şema)
- **Denetim Modu:** Salt-Okunur (Read-Only) Statik & Mantıksal Kod Denetimi
- **Not:** `agent_core/investigation/` dizini mevcut değildir; soruşturma yaşam döngüsü `agent_core/lifecycle/investigation.py` ve `agent_core/agents/osint_investigator.py` içindedir.

---

## 1. Modül Envanteri ve Erişilebilirlik Matrisi

| Dizin / Modül | LOC | Üretimde Kullanan (Tüketici) | Durum / Not |
|---|---:|---|---|
| `agents/authenticity_auditor.py` | 155 | `task_executor.py` | Aktif — LLM + görsel/metin tutarlılık |
| `agents/autonomous_verifier.py` | 966 | `task_executor.py` | Aktif — Çapraz jüri + kanıt kapısı (`_audit_vote` içinde P0 hata var) |
| `agents/cognitive_profiler.py` | 29 | `task_executor.py` | Aktif — `TargetPsycheProfiler` ince kabuğu |
| `agents/depth_analyst.py` | 189 | `task_executor.py` | Aktif — QuoteGuard entegreli, şemada `data_confidence` eksik |
| `agents/friction_detector.py` | 28 | `task_executor.py` | Aktif — `TargetPsycheProfiler` ince kabuğu |
| `agents/human_behavior.py` | 556 | `task_executor.py` | Aktif — OpenCV + dilsel/zamansal forensik (`_temporal_forensics` kırık) |
| `agents/interpreter_agent.py` | 126 | `task_executor.py` (`ENABLE_INTERPRETER`), `backend/api.py:4826` | Opsiyonel — `open-interpreter` kurulu değil; global singleton & `input()` deadlock |
| `agents/lilith_growth.py` | 754 | Yalnızca kök `run_lilith.py` | **Boru hattından erişilemez (Orphan)** + `FreeTextGateway` dış ağ sızıntısı |
| `agents/mirror_truth.py` | 206 | `task_executor.py`, `shadow_executor.py` | Aktif — Placeholder anchor sızıntısı var |
| `agents/osint_investigator.py` | 571 | `task_executor.py` | Aktif — `aiohttp` egress bypass + URL path enjeksiyonu + silinmeyen `fallback_reason` |
| `agents/passion_mapper.py` | 25 | `task_executor.py` | Aktif — `TargetPsycheProfiler` ince kabuğu |
| `agents/pattern_interrupt.py` | 267 | `main.py`, `task_executor.py`, `shadow_executor.py` | Aktif — Yakalanmayan LLM istisnası + ölü/kopya metodlar |
| `agents/resonance_calculator.py` | 546 | `task_executor.py` | Aktif — Ortak sınırları çatışma (`contradicted`) sayan mantık hatası |
| `agents/resonance_synthesizer.py` | 182 | `task_executor.py` | Aktif — `data_confidence=False` iken sıfırlanmayan `confidence`/`resonance_score` |
| `agents/target_psyche_profiler.py` | 346 | `cognitive_profiler`, `friction_detector`, `passion_mapper` | Aktif — `profile_frictions` içinde yokluktan sınır/güven üretme zorlaması |
| `aspasia/aspasia_chief.py` | 408 | `backend/api.py` | Aktif — `"yerel"`/`"local"` kelimesiyle routing bypass + write-only geçmiş |
| `aspasia/interface.py` | 992 | `aspasia_chief.py`, `backend/api.py`, `backend/services/aspasia_state.py` | Aktif — `build_oversight_digest` kota bayrağı hatası + büyük harf/HTTP URL reddi |
| `aspasia/mobile_coach.py` | 145 | `backend/routes/mobile_coach.py` | Aktif — İstemci Dark Triad verisini "sunucudan gelen bağlam" diye modele sunuyor |
| `chat/dialogue_manager.py` | 241 | `backend/api.py` | Aktif — Prompt injection + LLM hatasında bozulan geçmiş (`add_message` sırası) |
| `domain/channel_status.py` | 182 | `task_executor.py`, `backend/api.py` | Aktif |
| `domain/content_basis.py` | 220 | `authenticity_auditor`, `human_behavior`, `target_psyche_profiler` | Aktif — Motorlar (`engines/`) `post_evidence_types` ayrımını uygulamıyor |
| `domain/evidence_models.py` | 90 | `autonomous_verifier`, `services/*` | Aktif |
| `domain/memory_models.py` | 228 | Tüm ajanlar, `task_executor.py`, `backend/api.py` | Aktif — `extra="allow"` ve `model_copy` alias senkron sorunu |
| `domain/message_context_models.py` | 48 | `pattern_interrupt.py`, `services/message_context_adapter.py` | Aktif |
| `domain/pillar_models.py` | 192 | `engines/*`, `domain/pillar_wave2_models.py` | Aktif — `FrequencyReport.phase_shifts` hiç doldurulmuyor |
| `domain/pillar_wave2_models.py` | 129 | `engines/*` | Aktif |
| `domain/pipeline_status.py` | 25 | `task_executor.py`, `domain/*`, `backend/api.py` | Aktif |
| `domain/responsibility.py` | 242 | `task_executor.py`, `backend/api.py` | Aktif — `seal_trail` içinde `halted_frequency`/`unavailable` boşluğu |
| `domain/task_execution_state.py` | 49 | `task_executor.py`, `backend/api.py` | Aktif — `dict` snapshot ile `"unknown"` dönüyor, `decision_state` sabit `"unknown"` |
| `engines/pillar_orchestrator.py` | 70 | `task_executor.py` | Aktif — 7 sütun orkestratörü |
| `engines/frequency_engine.py` | 192 | `pillar_orchestrator.py`, `seismos_engine.py`, `strata_engine.py` | Aktif — Sınırsız `while t <= max(grids)` döngüsü + `posts` dict etkileşim kaybı |
| `engines/gravity_engine.py` | 81 | `pillar_orchestrator.py` | Aktif — `posts_meta` yoksa `posts` dict olsa bile her zaman `INSUFFICIENT_DATA` |
| `engines/key_engine.py` | 92 | `pillar_orchestrator.py` | Aktif — Kural tabanlı sentez |
| `engines/pulse_engine.py` | 59 | `pillar_orchestrator.py` | Aktif — Dar emoji regex'i + yanlış `emoji_diversity` + sabit z-skor tabanları |
| `engines/seismos_engine.py` | 118 | `pillar_orchestrator.py` | Aktif — 15 kelimelik çekimsiz/olumsuzlamasız `POS`/`NEG` sözlüğü |
| `engines/spectrum.py` | 179 | `frequency_engine.py` | Aktif — FFT periodogram (temiz ve deterministik) |
| `engines/strata_engine.py` | 99 | `pillar_orchestrator.py` | Aktif — `void_engine._presence` alt-dize hatasından doğrudan etkileniyor |
| `engines/void_engine.py` | 103 | `pillar_orchestrator.py`, `strata_engine.py` | Aktif — **P0:** `_presence` alt-dize araması Türkçe eklerle sahte sinyal üretiyor |

---

## 2. Özet Bulgu Tablosu (Önem Derecesine Göre)

| ID | Önem | Dosya ve Satır | Kategori | Kısa Başlık |
|---|---|---|---|---|
| **CORE-A-01** | **P0** | `agent_core/engines/void_engine.py:24-30`, `strata_engine.py:12,65-69` | Sahte/Bozuk Metrik | Kelime sınırı olmayan alt-dize (`c in corpus`) araması nedeniyle Türkçe eklerin (`-miş`→`iş`, `-din`→`din`, `artık`→`art`) sahte varlık ve fosil üretmesi |
| **CORE-A-02** | **P0** | `agent_core/agents/autonomous_verifier.py:118-136, 308-345` | Mantık Hatası | `claim_support_ratio >= 0.5` kapısının `YALAN` ve `ÇELİŞKİLİ` jüri oylarını sistematik olarak `BİLİNMİYOR`'a düşürmesi ve olumsuzlamayı görmezden gelmesi |
| **CORE-A-03** | **P0** | `agent_core/agents/osint_investigator.py:18, 162-169, 228-237, 289-295, 442, 496-498` | Güvenlik / Egress / Mantık | `aiohttp` ile merkezi egress/SSRF bypass'ı, `clean_username` URL path injection açığı ve başarılı Maigret/Holehe sonrasında silinmeyen `fallback_reason`/`error_code` |
| **CORE-A-04** | **P0** | `agent_core/chat/dialogue_manager.py:8, 51, 95-97, 196-232` | Prompt Injection & Durum Bozulması | Ham profil/mesaj enjeksiyonu, LLM çağrısı öncesi `add_message` nedeniyle hata anında bozulan diyalog geçmişi ve sabit `MAX_DIALOGUE_MESSAGE_CHARS` uyuşmazlığı |
| **CORE-A-05** | **P0** | `agent_core/agents/lilith_growth.py:13-14, 221-251, 313-349` | Veri Sızıntısı / Kırık Entegrasyon | "Canlı çağrı yapılmaz" beyanına rağmen `FreeTextGateway`'in `text.pollinations.ai` adresine profil verisini POST etmesi ve `from_cli_credentials` içinde yutulan parametreler |
| **CORE-A-06** | **P1** | `agent_core/agents/human_behavior.py:341-342, 423-451, 456-488, 507-556` | Kırık Forensik / Ölü Kod | `_temporal_forensics`'in ISO-8601/epoch zaman damgalarını %100 reddetmesi, `visual_edge_density` vs `tension` sinyal uyuşmazlığı ve ölü/sabit köprü metodları |
| **CORE-A-07** | **P1** | `agent_core/agents/resonance_calculator.py:203-230, 286-309, 360-383` | Mantık Hatası | Ortak hassasiyet/sınırların çatışma (`contradicted`) sayılması, `BaseModel` nesnelerinin `_collect_terms` tarafından yutulması ve `bool`/`NaN` vektör hatası |
| **CORE-A-08** | **P1** | `agent_core/agents/autonomous_verifier.py:416-419, 448-472, 734-764` | Mantık Hatası | Tek bir iddianın arama hatasında tüm doğrulama döngüsünün iptal edilmesi ve azınlık jüri koltuğunun kanıt URL/alıntısının çoğunluk kararına yazılması |
| **CORE-A-09** | **P1** | `agent_core/aspasia/aspasia_chief.py:78-95, 322-360, 378-389, 399-404` | Routing Bypass & Hafıza Kaybı | Mesajda `"yerel"`/`"local"` geçtiğinde `selected_model="local"` ile zincirin bypass edilmesi, `aspasia_session` geçmişinin prompt'a hiç verilmemesi ve sessiz `except: pass` |
| **CORE-A-10** | **P1** | `agent_core/engines/frequency_engine.py:37-61, 81-103`, `gravity_engine.py:27-31` | DoS Riski & Veri Kaybı | Sınırsız `while t <= max(grids)` zaman kovası döngüsü, `posts` dict içindeki beğeni/yorumların yoksayılması ve `post_evidence_types` kontrol eksikliği |
| **CORE-A-11** | **P1** | `agent_core/agents/resonance_synthesizer.py:154-169`, `memory_models.py:63, 135` | Sahte/Sınırsız Skor | `has_valid_evidence=False` olduğunda sıfırlanmayan `confidence` ve `resonance_score` değerleri ile eksik Pydantic `[0.0, 1.0]` sınırları |
| **CORE-A-12** | **P1** | `agent_core/agents/target_psyche_profiler.py:81-83, 175-177, 193, 205, 265` | Sahte Kanıt / Prompt Hatası | `profile_frictions` prompt'unun ketum/az paylaşımlı profillerde `0.1-1.0` güvenle sınır sinyali uydurmayı zorlaması ve boş `visual_evidence` dict kontrol hatası |
| **CORE-A-13** | **P1** | `agent_core/agents/interpreter_agent.py:37-65, 84-99` | Deadlock & Güvenlik | Global `interpreter` singleton mutasyonu, `auto_run=False` iken arka plan thread'inde `input()` beklemesi (deadlock) ve `LLMGateway` bypass'ı |
| **CORE-A-14** | **P2** | `agent_core/agents/depth_analyst.py:35-49, 146-152, 167-189` | Şema & Sessiz Hata | `DepthReport` modelinde eksik `data_confidence`/`fallback_reason`, loglanmadan yutulan `except Exception:` ve kafeslenmemiş `target_profile` JSON'u |
| **CORE-A-15** | **P2** | `agent_core/agents/pattern_interrupt.py:95-96, 147-151, 217-267` | Hata Yönetimi & Ölü Kod | Yakalanmayan `query_json_chain` istisnası, 50 karakterde kesilen kanıt metni (`evidence[:50]`) ve birebir kopya ölü metodlar |
| **CORE-A-16** | **P2** | `agent_core/aspasia/interface.py:48-59, 457-465, 896-906` | Mantık Hatası | `build_oversight_digest` içinde `has_content` bayrağının `unknown` kotaları yazdırması ve `_normalize_target_url` içinde büyük harf/HTTP URL reddi |
| **CORE-A-17** | **P2** | `agent_core/aspasia/mobile_coach.py:38-47, 109-112, 126` | Güvenlik / Epistemik İhlal | İstemciden gelen doğrulanmamış Dark Triad ve `manipulation_strategy` alanlarının sistem prompt'una "sunucudan gelen bağlam" olarak enjekte edilmesi |
| **CORE-A-18** | **P2** | `agent_core/engines/pulse_engine.py:29-50`, `strata_engine.py:48-53` | Bozuk Metrik | Dar `[😀-🙏]` emoji regex'i, yanlış isimlendirilmiş/normalize edilmemiş `emoji_diversity` ve sabit kodlanmış z-skor referans değerleri |
| **CORE-A-19** | **P2** | `agent_core/engines/seismos_engine.py:13-15, 31-36, 82-105` | Bozuk Metrik | 15 kelimelik çekimsiz ve olumsuzlamasız `POS`/`NEG` sözlüğü nedeniyle kırık `polarity()` hesabı ve 4 adet kodlanmamış `SeismicKind` enum değeri |
| **CORE-A-20** | **P2** | `agent_core/domain/task_execution_state.py:26-49`, `responsibility.py:180-197` | Sözleşme Boşluğu | `dict` snapshot verildiğinde `"unknown"` dönen `task_state_fields`, sabit `decision_state="unknown"` ve `seal_trail` içinde `halted_frequency`/`unavailable` boşluğu |
| **CORE-A-21** | **P3** | `agent_core/domain/memory_models.py:9-11, 52, 69, 74-90, 102, 107-116` | Şema Hijyeni | Docstring'deki `extra="forbid"` beyanına rağmen tüm modellerde `extra="allow"` kullanılması ve `model_copy` sonrası eski alias değerinin korunması |
| **CORE-A-22** | **P3** | `agent_core/agents/mirror_truth.py:71-72, 100-101, 147-155, 182, 201` | Placeholder Sızıntısı | Kanıt yokken üretilen `"bilinmeyen_caba"` ve `"belirsiz_frekans"` yer tutucularının prompt'a ve `ResonanceCalculator` terim havuzuna sızması |
| **CORE-A-23** | **P3** | `agent_core/agents/target_psyche_profiler.py:8, 341-346` | Performans | `profile_all` metodunun paralel (`asyncio.gather`) yerine sıralı çalışması ve `_extract_target_context`'i 3 kez tekrarlaması |
| **CORE-A-24** | **P3** | `agent_core/agents/osint_investigator.py:30-31`, `domain/pillar_models.py:59` | Ölü Şema Alanları | Hiçbir zaman doldurulmayan `OsintProfile.digital_footprint_score`, `dark_web_hits` ve `FrequencyReport.phase_shifts` alanları |

---

## 3. Detaylı Bulgular, Kanıtlar ve Düzeltme Talimatları

### [CORE-A-01] [P0] `void_engine.py` ve `strata_engine.py`: Kelime Sınırı Olmayan Alt-Dize (`c in corpus`) Eşleşmesi Nedeniyle Türkçe Eklerin Sahte Varlık ve Fosil Üretmesi

- **Dosya Yolu ve Satır Numarası:**
  - `agent_core/engines/void_engine.py:10-30, 54-60`
  - `agent_core/engines/strata_engine.py:12, 65-80`
- **Önem Derecesi:** **P0 (Kritik — Deterministik Motorun Yanlış Ölçüm Üretmesi)**
- **Kanıt:**
  `agent_core/engines/void_engine.py:10-30`:
  ```python
  CATEGORY_LEXICON = {
      "politics": {"cues": {"siyaset", "seçim", "politics", "vote"}, "baseline": 0.18},
      "religion": {"cues": {"inanç", "dua", "faith", "din"}, "baseline": 0.12},
      ...
      "romance": {"cues": {"aşk", "sevgili", "dating"}, "baseline": 0.15},
      "career": {"cues": {"kariyer", "job", "ofis", "iş"}, "baseline": 0.28},
      "money": {"cues": {"para", "money", "yatırım"}, "baseline": 0.16},
      ...
      "art_creation": {"cues": {"sanat", "müzik", "tasarım", "fotoğraf", "art"}, "baseline": 0.25},
  }

  def _presence(corpus, cues):
      hits = sorted(c for c in cues if c in corpus)
      n = sum(corpus.count(c) for c in hits)
      return float(1 - np.exp(-0.45 * n)), n, hits[:8]
  ```
  `_presence` fonksiyonu kelime sınırı (`\b`) veya token listesi yerine birleştirilmiş `corpus` karakter dizisi üzerinde doğrudan `c in corpus` ve `corpus.count(c)` çalıştırmaktadır:
  - `"iş"` (`career`): Türkçe `-miş` geçmiş zaman eki alan fiillerde (`gelmiş`, `gitmiş`, `demiş`, `etmiş`) ve `kişi`, `işte`, `değişik`, `ilişki`, `gelişim` kelimelerinde alt-dize olarak geçer.
  - `"din"` (`religion`): Türkçe `-din` 2. tekil şahıs geçmiş zaman ekinde (`geldin`, `gittin`, `dedin`, `sevdin`), `kendin`, `şimdiden`, `aydın`, `dinle` kelimelerinde alt-dize olarak geçer.
  - `"art"` (`art_creation`): `artık`, `şart`, `kart`, `mart`, `parti`, `tartışma` kelimelerinde geçer.
  - `"aşk"` (`romance`): `başka`, `başkan`, `şaşkın`, `taşkın` kelimelerinde geçer.
  - `"para"` (`money`): `numara`, `parantez`, `paragraf`, `imparator` kelimelerinde geçer.
  `1 - exp(-0.45 * n)` formülü yalnızca `n = 5` alt-dize eşleşmesinde `0.895` değerine ulaştığından, 40+ kelimelik sıradan bir Türkçe metinde `career`, `religion`, `art_creation`, `romance` kategorileri gerçekte hiç konuşulmasa bile `actual_presence ≈ 0.90-1.00` almakta; gerçek boşluk (`VoidSignal`) sinyalleri bastırılmakta ve `_presence` fonksiyonunu import eden `strata_engine.py:66-69` içinde yanlış `early_presence` / `late_presence` hesabı yüzünden sahte `FossilRecord` kayıtları üretilmektedir.
- **Düzeltme Talimatı:**
  `void_engine.py:24-30` içindeki `_presence(corpus, cues)` fonksiyonunu ham alt-dize araması yerine `tokens = re.findall(r"[^\W\d_]+", corpus.lower())` üzerinden tam kelime eşleşmesi (veya 4+ harfli kökler için kontrollü önek eşleşmesi `any(t == c or (len(c) >= 4 and t.startswith(c)) for t in tokens)`) kullanacak şekilde değiştirin.

---

### [CORE-A-02] [P0] `autonomous_verifier.py`: `claim_support_ratio >= 0.5` Kapısının `YALAN` ve `ÇELİŞKİLİ` Oylarını İptal Etmesi ve Olumsuzlamayı Görmezden Gelmesi

- **Dosya Yolu ve Satır Numarası:** `agent_core/agents/autonomous_verifier.py:118-136, 308-345`
- **Önem Derecesi:** **P0 (Kritik — Doğrulayıcı Hakemin Yalan İddiaları Çürütememesi)**
- **Kanıt:**
  `agent_core/agents/autonomous_verifier.py:325-345`:
  ```python
  if vote is None:
      return VOTE_UNKNOWN, "oy_sozluk_disi"
  if vote not in CONCLUSIVE_VOTES:
      return VOTE_UNKNOWN, "oy_belirsiz"
  if vote in {VOTE_CONTRADICTED, VOTE_FALSE} and not (contradiction_detail or "").strip():
      return VOTE_UNKNOWN, "celiski_gerekcesi_yok"

  source_list = list(sources or ())
  content = cls._match_source(evidence_url, source_list)
  if content is None:
      return VOTE_UNKNOWN, "kanit_url_kaynaksiz"
  from agent_core.services.quote_guard import quote_matches
  if not quote_matches(evidence_quote or "", [content], observe=True, claim_id=claim_id):
      return VOTE_UNKNOWN, "kanit_alinti_kaynaksiz"
  support = claim_support_ratio(claim_text, content)
  if support < MIN_CLAIM_SUPPORT_RATIO:
      return VOTE_UNKNOWN, f"kanit_destek_orani_dusuk:{round(support, 2)}"
  return vote, f"kanit_kapisi_gecildi:{round(support, 2)}"
  ```
  1. **Çürütme İmkânsızlığı:** Bir biyografi iddiası (örn. `claim_text = "Harvard Üniversitesi mezunu ve Nobel ödüllü fizikçi"`) yalan olduğunda, dış kaynakta kişinin gerçek bilgisi (örn. `"Ahmet Yılmaz, Ankara Lisesi mezunu olup muhasebeci olarak çalışmaktadır"`) yer alır. Jüri koltukları bu kaynağı gösterip birebir alıntıyla (`QuoteGuard` onaylı) `YALAN` veya `ÇELİŞKİLİ` oyu verdiğinde, `_audit_vote` satır 342'de `claim_support_ratio(claim_text, content)` hesaplar. Uydurma kelimeler (`harvard`, `nobel`, `fizikci`) gerçek kaynakta geçmediği için `support` `< 0.5` çıkar ve kod, geçerli `YALAN` / `ÇELİŞKİLİ` oyunu `VOTE_UNKNOWN` (`"kanit_destek_orani_dusuk"`) olarak iptal eder! Sonuç olarak `_direct_refutation_is_audited` (satır 492) gerçek yalan iddialarda neredeyse hiçbir zaman `True` dönemez.
  2. **Alt-Dize ve Olumsuzlama Hatası:** `claim_support_ratio` satır 135'te `hits = sum(1 for t in tokens if t in corpus)` ile alt-dize araması yapmakta ve kaynak metindeki olumsuzlama kelimelerini (`değil`, `değildir`, `yok`, `asla`, `not`, `never`, `false`) kontrol etmemektedir. Kaynakta `"Ahmet Yılmaz Harvard mezunu değildir"` yazdığında `support = 1.0` hesaplanarak hatalı bir `DOĞRULANDI` oyunun kapıdan geçmesine izin verilmektedir.
- **Düzeltme Talimatı:**
  1. `_audit_vote` içinde `support < MIN_CLAIM_SUPPORT_RATIO` kontrolünü yalnızca `vote == VOTE_VERIFIED` için zorunlu tutun; `vote in {VOTE_FALSE, VOTE_CONTRADICTED}` durumunda `evidence_url` eşleşmesi, `quote_matches` doğrulaması ve `contradiction_detail` varlığı (artı alıntının veya kaynağın hedef kişi/iddia konusuyla ilişkisi) yeterli olmalıdır.
  2. `claim_support_ratio` içinde `t in corpus` alt-dize kontrolünü token kümesi kontrolüne (`corpus_tokens = set(_claim_tokens(source_text))`) çevirin.

---

### [CORE-A-03] [P0] `osint_investigator.py`: `aiohttp` ile Egress/SSRF Omurgası Bypass'ı, URL Path Injection ve Başarılı Tarama Sonrası Silinmeyen `fallback_reason`/`error_code`

- **Dosya Yolu ve Satır Numarası:** `agent_core/agents/osint_investigator.py:18, 162-169, 228-237, 289-295, 442, 451-460, 496-498, 532-539`
- **Önem Derecesi:** **P0 (Kritik — Güvenlik / Egress Sözleşmesi İhlali ve Yanlış Durum Raporlaması)**
- **Kanıt:**
  1. **Egress Omurgası Bypass'ı ve URL Enjeksiyonu (`osint_investigator.py:18, 442, 496-498`):**
     ```python
     clean_username = username.lstrip("@")
     ...
     async with aiohttp.ClientSession() as session:
         headers = self._get_alf_headers()
         async with session.get(f"https://api.osint.industries/v1/user/{clean_username}", headers=headers, timeout=15) as resp:
     ```
     Projedeki tüm dış HTTP çağrılarının `agent_core.capabilities.egress.open_client` üzerinden geçmesi kuralına rağmen burada doğrudan `aiohttp.ClientSession` kullanılmaktadır. Ayrıca `clean_username` üzerinde `urllib.parse.quote` veya karakter beyaz listesi uygulanmadığından `username` içine `../../` veya `?` karakterleri enjekte edilerek `self.osint_api_key` başlığıyla birlikte URL path traversal / query injection yapılabilir.
  2. **Başarılı Bağımsız Sensörlerden Sonra Silinmeyen `fallback_reason` ve `error_code` (`osint_investigator.py:162-169, 228-237, 289-295, 451-460`):**
     `OSINT_INDUSTRIES_KEY` tanımlı olmadığında (satır 459) `profile` başlangıçta `fallback_reason="provider_credentials_unavailable"` ile oluşturulur; API hata verdiğinde ise (satır 537) `fallback_reason="api_error", error_code=error_code` atanır. Ardından `_continue_independent_sensors` ile Maigret, `handle_probe` ve Holehe çalıştırılır. Ancak:
     - `_apply_username_scan` satır 166:
       `"fallback_reason": None if not profile.fallback_reason else profile.fallback_reason`
       Koşul ters yazılmıştır! `profile.fallback_reason` zaten `"provider_credentials_unavailable"` veya `"api_error"` olduğu için `not profile.fallback_reason` `False` döner ve Maigret 15 platform bulup `data_confidence=True` yapsa bile `fallback_reason="provider_credentials_unavailable"` olarak kalır!
     - `_apply_cross_platform_probe` (satır 233-237) ve `_apply_email_scan` (satır 289-295) ise `found_sites` dolu olduğunda `fallback_reason` ve `error_code` alanlarını hiç güncellemez.
- **Düzeltme Talimatı:**
  1. `aiohttp` importunu kaldırın; `agent_core.capabilities.egress.open_client(purpose="osint", timeout=15.0)` kullanın ve `clean_username` değerini `urllib.parse.quote(clean_username, safe="")` ile kodlamadan önce `re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", clean_username)` ile doğrulayın.
  2. `_apply_username_scan` (satır 166), `_apply_cross_platform_probe` (satır 233) ve `_apply_email_scan` (satır 289) içinde `found_sites` bulunduğunda (`data_confidence=True` olduğunda) `"fallback_reason": None, "error_code": None` ataması yapın.

---

### [CORE-A-04] [P0] `dialogue_manager.py`: Prompt Injection, LLM Hatasında Diyalog Geçmişi Bozulması ve Sabit Uzunluk Sınırı Uyuşmazlığı

- **Dosya Yolu ve Satır Numarası:** `agent_core/chat/dialogue_manager.py:8, 51, 95-97, 192, 196-232`
- **Önem Derecesi:** **P0 (Kritik — Güvenlik / Prompt Injection ve Oturum Durumu Bozulması)**
- **Kanıt:**
  `agent_core/chat/dialogue_manager.py:196-232`:
  ```python
  # Add target message to history.
  self.add_message(task_id, "target", target_message)

  # Build prompt.
  history_str = "\n".join(
      f"{message['role'].upper()}: {message['content']}"
      for message in ctx.history
  )

  prompt = f"""
  ...
  HEDEF PROFİLİ:
  {json.dumps(ctx.target_profile, ensure_ascii=False, indent=2)}
  ...
  DİYALOG GEÇMİŞİ:
  {history_str}
  ...
  """
  response = await self.llm.query_json(prompt, DialogueResponse)

  # Add our response to history.
  self.add_message(task_id, "agent", response.next_move)
  ```
  1. **Prompt Injection:** Satır 8'deki `"oturum durumu asla prompt'a ham dökülmez"` beyanının aksine `ctx.target_profile`, `ctx.user_profile` ve `target_message` hiçbir yapısal kafesleme (`<UNTRUSTED_...>`) veya rol öneki temizliği olmadan doğrudan prompt'a gömülmektedir. `target_message` içinde `\nAGENT: ...\nGÖREV: ...` gönderilerek diyalog geçmişi ve görev talimatı ele geçirilebilir.
  2. **Hata Anında Geçmiş Kirlenmesi (State Corruption):** `self.add_message(task_id, "target", target_message)` (satır 196), `await self.llm.query_json(...)` (satır 228) çağrısından **önce** çalıştırılmaktadır. LLM çağrısı hata verdiğinde veya zaman aşımına uğradığında `target_message` geçmişte kalıcı olarak bırakılır; istemci isteği tekrarladığında aynı hedef mesajı geçmişe ikinci kez eklenir.
  3. **Şema vs Runtime Uzunluk Sınırı Çatışması:** `DialogueResponse.next_move` (satır 51) modül yükleme anındaki sabit `MAX_DIALOGUE_MESSAGE_CHARS = 4000` değerini kullanırken, `self.max_message_chars` (satır 95) `PINEAL_MAX_DIALOGUE_MESSAGE_CHARS` env değişkeninden okunur. Env değişkeni `< 4000` olarak ayarlandığında LLM cevabı `DialogueResponse` doğrulamasından geçer ancak satır 231'deki `self.add_message(task_id, "agent", response.next_move)` çağrısında `DialogueInputError` fırlatır (ve hedef mesajı yine geçmişte asılı kalır!).
  4. **Standart Dışı İstisna:** Satır 192'de `raise ValueError("Diyalog oturumu işlem sırasında değişti.")` ham `ValueError` fırlatmaktadır (`DialogueInputError` yerine).
- **Düzeltme Talimatı:**
  1. `generate_response` içinde `self.add_message(task_id, "target", target_message)` çağrısını `await self.llm.query_json(...)` başarılı olduktan **sonra** (`self.add_message(task_id, "agent", ...)` ile atomik olarak) yapın; prompt için geçmişi `[ *ctx.history, {"role": "target", "content": target_message} ]` üzerinden oluşturun.
  2. `response.next_move` değerini `self.max_message_chars` sınırına göre kırpın veya doğrulamayı `add_message` öncesinde yapın.
  3. `ctx.target_profile` ve `history_str` bloklarını `<UNTRUSTED_TARGET_PROFILE>` ve `<UNTRUSTED_DIALOGUE_HISTORY>` etiketleriyle kafesleyin ve mesaj içindeki `\nAGENT:` / `\nTARGET:` satır başlarını sterilize edin.

---

### [CORE-A-05] [P0] `lilith_growth.py`: "Canlı Çağrı Yapılmaz" Beyanına Rağmen `FreeTextGateway` Üzerinden Üçüncü Taraf Sunucuya (`text.pollinations.ai`) Veri Gönderilmesi ve Yutulan CLI Argümanları

- **Dosya Yolu ve Satır Numarası:** `agent_core/agents/lilith_growth.py:13-14, 221-251, 313-349`
- **Önem Derecesi:** **P0 (Kritik — Yetkisiz Dış Ağ Çağrısı / Veri Sızıntısı ve Kırık Fabrika Metodu)**
- **Kanıt:**
  1. **Yanıltıcı Sözleşme ve Dış Ağ Çağrısı (`lilith_growth.py:13-14, 231-251, 334-335`):**
     Satır 13-14: `"FreeTextGateway (anahtar yokken: uydurma içerik ÜRETİLMEZ, dürüst 'gateway yok' yolu)"` ve satır 334-335: `"api_key yoksa sıfır-maliyet FreeTextGateway'e düşülür (canlı çağrı yapılmaz)."`
     Ancak satır 231-251'deki gerçek kod:
     ```python
     class FreeTextGateway:
         TEXT_API_URL = "https://text.pollinations.ai/"
         ...
         async def chat(self, messages: List[Dict[str, str]], ...) -> _ChatResponse:
             payload = {"messages": messages, "jsonMode": True}
             async with open_client(purpose="llm", timeout=self.timeout) as client:
                 resp = await client.post(
                     self.TEXT_API_URL,
                     json=payload,
                     headers={"Content-Type": "application/json"},
                 )
     ```
     API anahtarı verilmediğinde "canlı çağrı yapılmaz" denmesine rağmen `https://text.pollinations.ai/` adresine canlı HTTP POST isteği atılmakta ve hedef kişinin biyografisi, gönderileri, hassasiyetleri ve tutkuları kimlik doğrulamasız dış servise gönderilmektedir.
  2. **Yutulan CLI Parametreleri (`lilith_growth.py:337-340`):**
     ```python
     if use_main_line_gateway and api_key:
         from agent_core.services.llm_gateway import LLMGateway
         return cls(llm_gateway=LLMGateway())
     ```
     `use_main_line_gateway` varsayılan olarak `True` olduğu için, çağırıcı `from_cli_credentials(api_key="sk-...", base_url="...", model="...")` şeklinde özel anahtar/URL/model verdiğinde `LLMGateway()` argümansız çağrılmakta ve verilen parametrelerin tamamı yoksayılmaktadır.
- **Düzeltme Talimatı:**
  1. `FreeTextGateway.chat()` içindeki `https://text.pollinations.ai/` canlı ağ çağrısını kaldırın; API anahtarı yokken dış servise veri göndermek yerine deterministik olarak `RuntimeError("llm_credentials_unavailable")` fırlatın (böylece `execute()` güvenli `fallback_reason="llm_unavailable"` yoluna düşer).
  2. `from_cli_credentials` içinde `LLMGateway(api_key=api_key)` veya açık `base_url`/`model` verildiğinde ilgili yapılandırmayı koruyacak şekilde parametreleri aktarın.

---

### [CORE-A-06] [P1] `human_behavior.py`: Kırık Zaman Forensiği (`_temporal_forensics`), Sinyal Tipi Uyuşmazlığı (`visual_edge_density` vs `tension`) ve Ölü/Sahte Köprü Metodları

- **Dosya Yolu ve Satır Numarası:** `agent_core/agents/human_behavior.py:341-342, 423-451, 456-488, 507-556`
- **Önem Derecesi:** **P1 (Yüksek — Forensik Sinyallerin Üretimde Çalışmaması)**
- **Kanıt:**
  1. **ISO-8601 ve Epoch Zaman Damgalarının %100 Reddedilmesi (`human_behavior.py:428-436`):**
     ```python
     for value in post_times or []:
         try:
             hour = int(str(value).strip().split(":", 1)[0])
             if 0 <= hour <= 23:
                 total_valid += 1
                 if hour >= 23 or hour <= 4:
                     late_night_count += 1
         except (TypeError, ValueError):
             continue
     ```
     `post_times` listesi gerçek kazıyıcılarda ISO-8601 (`"2026-09-20T23:45:00Z"`) veya Unix epoch (`1726875900`) taşır. `"2026-09-20T23:45:00Z".split(":", 1)[0]` değeri `"2026-09-20T23"` olduğundan `int(...)` `ValueError` fırlatır ve `continue` ile yutulur. Epoch sayılar ise `0 <= hour <= 23` koşuluna takılır. Sonuç olarak `_temporal_forensics` gerçek veride her zaman `[]` döner.
  2. **Sinyal Tipi Uyuşmazlığı (`human_behavior.py:341-342` vs `462-464`):**
     `_analyze_visual_micro_img` omuz bölgesinde yüksek kenar yoğunluğu bulduğunda `signal_type="visual_edge_density"` üretir (satır 342). Ancak `_mine_contradictions` satır 463'te `s.signal_type in ("tension", "void")` kontrolü yapar; `"visual_edge_density"` kontrol edilmediği için omuz gerginliği sinyali hiçbir zaman çelişki üretemez.
  3. **Ulaşılamaz Çelişki Dalı (`human_behavior.py:478-486`):**
     `_mine_contradictions` metinsel sinyallerde `if s.signal_type == "contradiction":` arar; fakat `_linguistic_forensics` yalnızca `"authentic"`, `"passive_voice_observation"` ve `"defense"` üretir.
  4. **Ölü ve Sabit Metodlar (`human_behavior.py:507-556`):**
     `_identify_wound_as_bridge` ve `_calculate_resonance_potential` hiçbir yerden çağrılmaz. `_identify_wound_as_bridge` içindeki 5 farklı yara tipi (`visual_linguistic_mismatch`, `social_vs_alone`, `happy_vs_tired` vb.) tamamen aynı sabit sözlüğü döndürür; `_calculate_resonance_potential` ise bu sözlükte hiç bulunmayan `wound.get("defense_strength", 0.5)` anahtarını okur.
- **Düzeltme Talimatı:**
  1. `_temporal_forensics` içinde `from agent_core.engines.frequency_engine import parse_timestamp` kullanarak önce tam zaman damgasından `.hour` değerini çıkarın, yalnızca `parse_timestamp` `None` dönerse `"HH:MM"` ayrıştırmasını deneyin.
  2. Satır 463'teki koşulu `s.signal_type in ("tension", "visual_edge_density", "void")` olarak güncelleyin.
  3. Çağrılmayan `_identify_wound_as_bridge` ve `_calculate_resonance_potential` metodlarını temizleyin.

---

### [CORE-A-07] [P1] `resonance_calculator.py`: Ortak Sınırların Çatışma (`contradicted`) Sayılması, `BaseModel` Girdilerinin Yutulması ve `bool`/`NaN` Vektör Hatası

- **Dosya Yolu ve Satır Numarası:** `agent_core/agents/resonance_calculator.py:203-230, 286-309, 360-383`
- **Önem Derecesi:** **P1 (Yüksek — Yanlış `contradicted` Hükmü ve Sessiz Terim Kaybı)**
- **Kanıt:**
  1. **Ortak Hassasiyetlerin Çatışma Sayılması (`resonance_calculator.py:360-374`):**
     ```python
     matches = sorted(user_terms & target_terms)
     if kind == "boundary":
         overlap = len(matches) / len(target_terms)
         if matches:
             return EvidenceOverlap(
                 domain=label,
                 state="contradicted",
                 overlap=overlap,
                 conflicting_evidence=matches,
                 ...
             )
     ```
     `user_terms` kullanıcının tüm profil/ayna kelimelerini, `target_terms` ise hedefin `frictions` (`sensitivities`, `stress_triggers`, `boundary_signals`, `evidence_quotes`) kelimelerini içerir. Kullanıcı ve hedef **aynı hassasiyeti/sınırı paylaştığında** (örneğin ikisi de `"gürültülü ortamlar"`, `"samimiyetsizlik"` veya `"geç saatte mesaj"` sevmediğini belirttiğinde), bu kelimeler kesiştiği için sistem bunu `state="contradicted"` (çatışma!) ilan etmekte ve `_aggregate_state` (satır 456) tüm rezonans kararını `"contradicted"` yapmaktadır. Ayrıca `_META_KEYS` içinde `"evidence_quotes"` olmadığı için alıntı cümlelerdeki sıradan kelimeler de sahte sınır çatışması tetiklemektedir.
  2. **`BaseModel` Nesnelerinin Yutulması (`resonance_calculator.py:286-309`):**
     `_collect_terms` yalnızca `str`, `dict`, `list`, `tuple` kabul eder; `input_data["passions"]`, `input_data["frictions"]`, `input_data["cognitive"]` veya `input_data["user_mirror"]` Pydantic `BaseModel` örneği olarak geldiğinde satır 309'da sessizce atlanır ve `0 anlamlı terim` nedeniyle `inference_gap` döner.
  3. **`bool` ve `NaN`/`Inf` Kontrol Eksikliği (`resonance_calculator.py:206-209, 215-218`):**
     `_has_required_dimensions` ve `_cosine_similarity` içinde `not isinstance(v, bool)` ve `math.isfinite(v)` kontrolü yapılmamaktadır (`isinstance(True, (int, float))` Python'da `True` döner). Vektör sözlüğündeki boolean alanlar `1.0`/`0.0` olarak cosine benzerliğine dahil edilmekte, `NaN`/`Inf` değerler ise `compatibility_score`'u `NaN` yapmaktadır.
- **Düzeltme Talimatı:**
  1. `_collect_terms` başına `if isinstance(node, BaseModel): node = node.model_dump()` ekleyin ve `_META_KEYS` kümesine `"evidence_quotes"` alanını dahil edin (veya sınır terimlerini yalnızca `sensitivities`, `stress_triggers`, `boundary_signals`, `forbidden_territories` alanlarından toplayın).
  2. `frictions` (`kind == "boundary"`) değerlendirmesinde hedefin sınırlarını kullanıcının tüm kelimeleriyle değil, kullanıcının *aktif eğilim/tutku* terimleriyle karşılaştırın.
  3. `_has_required_dimensions` ve `_cosine_similarity` içinde `_numeric_dim` yardımcı metodunu (`isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)`) kullanın.

---

### [CORE-A-08] [P1] `autonomous_verifier.py`: Tekil Arama Hatasında Tüm Doğrulama Döngüsünün İptali ve Azınlık Jüri Kanıtının Çoğunluk Kararına Yazılması

- **Dosya Yolu ve Satır Numarası:** `agent_core/agents/autonomous_verifier.py:416-419, 448-472, 734-764`
- **Önem Derecesi:** **P1 (Yüksek — Kısmi Doğrulama Kaybı ve Kanıt/Hüküm Uyumsuzluğu)**
- **Kanıt:**
  1. **Döngü İptali (`autonomous_verifier.py:747-764`):**
     `for claim in claim_data.claims:` döngüsünde N iddiadan 1'incisi doğrulandıktan sonra 2'nci iddianın arama çağrısı `not outcome.available` dönerse, satır 756'da doğrudan `return VerifierReport(..., overall_authenticity_score=0.0, status="UNVERIFIED", data_confidence=False, fallback_reason="search_unavailable")` çalıştırılarak döngü kırılmakta ve doğrulanmış diğer tüm iddialar geçersiz kılınmaktadır.
  2. **Azınlık Jüri Kanıtının Çoğunluk Hükmüne Yazılması (`autonomous_verifier.py:416-419`):**
     ```python
     if counted in CONCLUSIVE_VOTES:
         evidence_url = evidence_url or seat_url
         evidence_quote = evidence_quote or seat_quote
     contradiction = contradiction or str(getattr(outcome, "contradiction_detail", "") or "")
     ```
     Koltuk 1 (`google`) `YALAN` oyu verip `url_1`/`quote_1`/`contradiction_1` döndürdüğünde ve Koltuk 2 (`claude`) ile Koltuk 3 (`open`) `DOĞRULANDI` oyu verip `url_2`/`quote_2` döndürdüğünde, çoğunluk kararı `verdict = "DOĞRULANDI"` olur; ancak `evidence_url`, `evidence_quote` ve `contradiction_detail` ilk koltuktan (`or` operatörüyle) alındığı için `DOĞRULANDI` hükmünün yanına `YALAN` diyen koltuğun URL'i, alıntısı ve çelişki açıklaması yazılır!
- **Düzeltme Talimatı:**
  1. Satır 756'daki erken `return` ifadesini kaldırın; arama başarısız olduğunda ilgili iddiayı `VOTE_UNKNOWN` (`decision_rule="arama_kullanilamadi"`) olarak `verifications` listesine ekleyip `continue` ile sonraki iddiaya geçin (tüm iddialarda arama başarısız olduysa döngü sonunda `fallback_reason="search_unavailable"` verin).
  2. `_verify_with_panel` içinde `verdict` (`top_status`) belirlendikten sonra `evidence_url`, `evidence_quote` ve `contradiction_detail` değerlerini yalnızca `votes.get(seat) == verdict` olan koltukların çıktılarından seçin.

---

### [CORE-A-09] [P1] `aspasia_chief.py`: `"yerel"`/`"local"` Kelimesiyle İstenmeyen Model Override (Routing Bypass), Çok Turlu Hafıza Kaybı ve Sessiz Yutulan TasteFilter

- **Dosya Yolu ve Satır Numarası:** `agent_core/aspasia/aspasia_chief.py:78-95, 322-360, 378-389, 399-404`
- **Önem Derecesi:** **P1 (Yüksek — Merkezi Routing Bypass'ı ve Sohbet Hafızası Kaybı)**
- **Kanıt:**
  1. **Alt-Dize ile Routing Bypass (`aspasia_chief.py:340-358`):**
     ```python
     selected_model = model_override or self.preferred_model
     if not selected_model and any(w in user_message.lower() for w in ["yerel", "local", "kısıtlamasız", "ollama", "lmstudio"]):
         selected_model = "local"
     ...
     if selected_model:
         raw_response = await self.llm.query(..., model=selected_model, ...)
     ```
     Kullanıcı mesajında `"yerel"` veya `"local"` kelimesi geçen herhangi bir cümle (örn. `"Bu kişinin yerel işletmesi var mı?"`, `"Yerel saatle kaçta paylaşım yapıyor?"`) otomatik olarak `selected_model = "local"` atamakta, `query_chain` ve `AGENT_CHAINS["aspasia"]` zincirini atlayarak doğrudan yerel modele bağlanmaya çalışmakta ve yerel sunucu yoksa hata mesajına düşmektedir.
  2. **Write-Only Sohbet Geçmişi (`aspasia_chief.py:322-338, 399-404`):**
     Satır 402-403'te `room_state["aspasia_session"].add_message("user", user_message)` ve `add_message("aspasia", final_msg)` çağrılmasına rağmen, `chat()` içinde `room_state["aspasia_session"].conversation_history` **hiç okunmamakta** ve `context_prompt` içine dahil edilmemektedir. Aspasia önceki turlarda ne sorulduğunu ve ne yanıt verdiğini tamamen unutmaktadır.
  3. **Sessiz İstisna Yutma ve Eksik Telemetri (`aspasia_chief.py:93-94, 376-389`):**
     Satır 377'deki yorum `"olay telemetriye yazılır (neden düştüğü görünür)"` demesine rağmen `decision.kept == False` olduğunda `decision.reasons` hiçbir yere kaydedilmemekte; satır 93-94 ve 388-389'daki `except Exception: pass` blokları hataları loglamadan yutmaktadır.
- **Düzeltme Talimatı:**
  1. Satır 341-342'deki otomatik `"yerel"`/`"local"` kelime taramasını kaldırın; model seçimi yalnızca açık `model_override` veya `set_preferred_model` üzerinden yapılmalıdır.
  2. `room_state.get("aspasia_session")` içindeki son N mesajı (örn. son 8 mesaj) `context_prompt` içine `ÖNCEKİ SOHBET GEÇMİŞİ` olarak ekleyin ve `AspasiaSession.add_message` (`domain/memory_models.py:225`) içine maksimum mesaj sınırı (örn. 40 mesaj) koyun.
  3. `taste_filter` redlerini ve istisnalarını `logger.info` / `logger.warning` ile kayıt altına alın.

---

### [CORE-A-10] [P1] `frequency_engine.py` ve `gravity_engine.py`: Sınırsız Zaman Kovası Döngüsü (DoS/OOM), `posts` Dict Etkileşim Kaybı ve `content_basis` İhlali

- **Dosya Yolu ve Satır Numarası:**
  - `agent_core/engines/frequency_engine.py:37-61, 81-103`
  - `agent_core/engines/gravity_engine.py:27-39`
  - `agent_core/domain/content_basis.py:28-29, 130-139`
- **Önem Derecesi:** **P1 (Yüksek — DoS/OOM Riski ve Veri Kaybı)**
- **Kanıt:**
  1. **Sınırsız `while t <= max(grids):` Döngüsü (`frequency_engine.py:86-103`):**
     İlk gönderi zaman damgası (`start`) ile son gönderi zaman damgası (`max(grids)`) arasında yıllara yayılan bir fark (örn. sabitlenmiş eski gönderi veya hatalı ayrıştırılan 10-13 haneli sayısal zaman damgası) olduğunda, `while t <= max(grids):` her `bucket_hours` için bir `WaveSample` oluşturarak yüz binlerce iterasyon yapmakta ve CPU/bellek tükenmesine yol açmaktadır.
  2. **`posts` Dict İçindeki Etkileşim Verisinin Yoksayılması (`frequency_engine.py:46-58`, `gravity_engine.py:27-39`):**
     `extract_post_series` içinde `posts[i]` bir `dict` ise `created_at`/`timestamp` bu `dict` içinden okunabilmekte (satır 49), ancak `like_count`/`likes` ve `comment_count`/`comments` yalnızca `posts_meta[i]` (`m`) içinden okunmaktadır (satır 57-58). `GravityEngine._sync` (satır 29) ise `if len(posts) < 3 or len(meta) < 3:` koşulu yüzünden, `posts` listesi `dict` öğelerinden oluşan ama ayrı `posts_meta` listesi bulunmayan tüm profillerde her zaman `INSUFFICIENT_DATA` dönmektedir.
  3. **`post_evidence_types` Filtresi Eksikliği:**
     `domain/content_basis.py:28-29` ölçüm motorlarının arama snippet'larını kullanmamasını şart koşarken, `frequency_engine`, `gravity_engine`, `void_engine` ve `pulse_engine` `target_profile.get("post_evidence_types")` listesini kontrol etmeden `posts` dizisini ham olarak okumaktadır.
- **Düzeltme Talimatı:**
  1. `FrequencyEngine._sync` içinde `(max(grids) - start) // step > 2000` durumunda pencereyi son 2000 kovayla sınırlandırın veya `bucket_hours` değerini dinamik büyütün.
  2. Hem `extract_post_series` hem `GravityEngine._sync` içinde `posts_meta[i]` boş olduğunda `posts[i]` bir `dict` ise `like_count`/`likes` ve `comment_count`/`comments` alanlarını `posts[i]` üzerinden okuyun.
  3. Motorlarda `post_evidence_types` paralel dizisinde `"search_snippet"` olarak işaretlenmiş indeksleri filtreleyin.

---

### [CORE-A-11] [P1] `resonance_synthesizer.py` ve `memory_models.py`: `has_valid_evidence=False` İken Sıfırlanmayan `confidence`/`resonance_score` ve Eksik Şema Kısıtları

- **Dosya Yolu ve Satır Numarası:**
  - `agent_core/agents/resonance_synthesizer.py:154-169`
  - `agent_core/domain/memory_models.py:63, 135`
- **Önem Derecesi:** **P1 (Yüksek — Kanıtsız Çıktıda Yüksek Güven ve Rezonans Skoru Sızıntısı)**
- **Kanıt:**
  `agent_core/agents/resonance_synthesizer.py:154-169`:
  ```python
  has_bridge = bool(
      result.shared_passions or result.suggested_opening_message
  )
  conf, confidence_valid = normalize_confidence(getattr(result, "confidence", None))
  has_valid_evidence = has_bridge and confidence_valid and conf > 0.0
  ...
  return result.model_copy(update={
      "confidence": conf,
      "data_confidence": has_valid_evidence,
      "fallback_reason": reason,
  })
  ```
  - `has_bridge` `False` olduğunda (`has_valid_evidence = False`, `fallback_reason = "insufficient_grounded_evidence"`), `confidence` alanı `0.0`'a çekilmeden doğrudan `conf` (örn. `0.85`) olarak bırakılmakta ve `result.resonance_score` alanı ne `normalize_confidence` ile doğrulanmakta ne de `0.0`'a sıfırlanmaktadır.
  - Ayrıca `memory_models.py:135`'te `AuthenticBridge.resonance_score: float = 0.0` alanı `Field(ge=0.0, le=1.0)` kısıtına sahip değildir (`memory_models.py:63`'teki `PassionProfile.sentiment_polarity: float = 0.0` alanı da `Field(ge=-1.0, le=1.0)` kısıtına sahip değildir).
- **Düzeltme Talimatı:**
  `resonance_synthesizer.py:157-169` içinde `res_score, res_valid = normalize_confidence(getattr(result, "resonance_score", None))` doğrulaması ekleyin ve `model_copy` güncellemesini `"confidence": conf if has_valid_evidence else 0.0, "resonance_score": res_score if (has_valid_evidence and res_valid) else 0.0` olarak değiştirin. `memory_models.py` içinde `resonance_score` için `Field(default=0.0, ge=0.0, le=1.0)` ve `sentiment_polarity` için `Field(default=0.0, ge=-1.0, le=1.0)` tanımlayın.

---

### [CORE-A-12] [P1] `target_psyche_profiler.py`: Yokluktan Sınır Uyduran Prompt Talimatı, Taban Confidence (`0.1`) Zorlaması ve Boş `visual_evidence` Dict Hatası

- **Dosya Yolu ve Satır Numarası:** `agent_core/agents/target_psyche_profiler.py:81-83, 175-177, 193, 205, 265`
- **Önem Derecesi:** **P1 (Yüksek — Veri Yokluğunda Sahte Sınır ve Pozitif Güven Üretimi)**
- **Kanıt:**
  1. `agent_core/agents/target_psyche_profiler.py:193, 205`:
     - Satır 193: `"Profil az paylaşımlı, ketum veya mesafeli ise, bu mahremiyet ve sessizlik tercihini doğrudan somut bir sınır sinyali (boundary_signals) olarak işle."`
     - Satır 205: `"Confidence kuralı: confidence alanını verilen doğrudan ve gözlemsel kanıtın tamlığına göre 0.1 ile 1.0 arasında ölç."`
     Diğer tüm ajanlarda `"0.0 ile 1.0 arasında ölç; kanıt yetersizse 0.0 ve data_confidence=false döndür"` kuralı varken, `profile_frictions` modeli minimum `0.1` güven vermeye ve paylaşım azlığını `boundary_signals` olarak yazmaya zorlamaktadır. Böylece satır 231'deki `has_valid_evidence = has_frictions and confidence_valid and conf > 0.0` kontrolü kanıtsız profillerde bile her zaman `True` olmaktadır.
  2. Satır 83, 177 ve 265'te `if not bio and posts_text == "Gönderi metni bulunamadı." and not visual_evidence:` kontrolü yapılmaktadır. `visual_evidence` içi boş bir sözlük (`{"detected_objects": [], "aesthetic_style": ""}`) olduğunda `bool(visual_evidence)` `True` döner ve ajan hiçbir gerçek metin veya görsel kanıt olmadan LLM çağrısı yapar.
- **Düzeltme Talimatı:**
  1. `profile_frictions` satır 205'teki confidence kuralını `0.0 ile 1.0 arasında ölç; kanıt yetersizse 0.0 ve data_confidence=false döndür` olarak düzeltin ve satır 193'teki yokluktan sınır üretme talimatını kaldırın.
  2. `_extract_target_context` içinde `visual_evidence` sözlüğünün gerçekten dolu bir sinyal taşıyıp taşımadığını `authenticity_auditor.py:62-72`'deki gibi kontrol edin.

---

### [CORE-A-13] [P1] `interpreter_agent.py`: Global Singleton Mutasyonu, Arka Plan Thread'inde `input()` Deadlock'u ve `LLMGateway` Bypass'ı

- **Dosya Yolu ve Satır Numarası:** `agent_core/agents/interpreter_agent.py:37-65, 84-99`
- **Önem Derecesi:** **P1 (Yüksek — Thread Bloklanması / Oturum Karışması / Gateway Bypass)**
- **Kanıt:**
  1. Satır 39'da `from interpreter import interpreter` ile global singleton nesne import edilmekte, `_setup_interpreter` üzerinde `interpreter.llm.api_key` ve `interpreter.llm.model` mutasyona uğratılmakta ve `interpreter.messages` sıfırlanmamaktadır.
  2. Satır 41'de `interpreter.auto_run = False` yapıldıktan sonra satır 85'te `asyncio.to_thread` içinde `interpreter.chat(prompt, display=False)` çağrıldığında, `open-interpreter` kod çalıştırma onayı için standart girdiden (`input()`) onay bekler; sunucu ortamında bu çağrı worker thread'ini sonsuza dek bloklar veya `EOFError` üretir.
  3. Satır 48-54'te `LLMGateway` bütçe/kota/maliyet sistemi tamamen devre dışı bırakılarak doğrudan `https://openrouter.ai/api/v1` adresine istek yapılmaktadır. Satır 66 ve 70'teki `auto_run` parametresi ise `_setup_interpreter` içinde hiç kullanılmamaktadır.
- **Düzeltme Talimatı:**
  Global singleton yerine her görev için izole örnek oluşturun veya geçmişi temizleyin; `open-interpreter` çağrısında interaktif `input()` onayını tetikleyen akış yerine yalnızca kod önerisi üreten veya insan onayını API katmanında (`awaiting_authorization`) alan mimariyi kullanın.

---

### [CORE-A-14] [P2] `depth_analyst.py`: `DepthReport` Şemasında Eksik `data_confidence`/`fallback_reason`, Loglanmadan Yutulan İstisna ve Kafeslenmemiş Prompt Girdileri

- **Dosya Yolu ve Satır Numarası:** `agent_core/agents/depth_analyst.py:35-49, 146-152, 167-189`
- **Önem Derecesi:** **P2 (Orta — Şema Bütünlüğü ve Gözlemlenebilirlik Eksikliği)**
- **Kanıt:**
  1. `DepthReport` (satır 35-49) üzerinde `data_confidence`, `confidence` ve `fallback_reason` alanları tanımlı değildir. Satır 187-188'deki fallback bloğunda verilen `data_confidence=False, fallback_reason="llm_unavailable"` yalnızca `ConfigDict(extra="allow")` sayesinde kabul edilmekte; başarılı LLM çağrısında ise `DepthReport` üzerinde `data_confidence` hiç yer almamaktadır.
  2. Satır 179'daki `except Exception:` bloğu hiçbir loglama yapmadan hatayı yutmaktadır (`logging` modülü dosyada import bile edilmemiştir).
  3. Satır 146-150'de `tp` (`target_profile`), `visual`, `audit`, `timing`, `osint` ham `json.dumps` ile `<UNTRUSTED_...>` kafesi olmadan prompt'a eklenmektedir.
- **Düzeltme Talimatı:**
  `DepthReport` şemasına `confidence: float = Field(default=0.0, ge=0.0, le=1.0)`, `data_confidence: bool = False`, `fallback_reason: Optional[str] = None` alanlarını ekleyin; `guard_report` sonrasında bulgu kalmadıysa `data_confidence=False` atayın; `except Exception as exc:` içinde `logger.warning` çağırın ve `tp`/`osint` bloklarını `<UNTRUSTED_...>` etiketleriyle sarın.

---

### [CORE-A-15] [P2] `pattern_interrupt.py`: Yakalanmayan LLM İstisnası, 50 Karakterde Kesilen Kanıt Metni ve Birebir Kopya Ölü Metodlar

- **Dosya Yolu ve Satır Numarası:** `agent_core/agents/pattern_interrupt.py:95-96, 147-151, 217-267`
- **Önem Derecesi:** **P2 (Orta — Hata Dayanıklılığı ve Kod Kalitesi)**
- **Kanıt:**
  1. Satır 147'deki `result = await llm_gateway.query_json_chain(...)` çağrısı `try/except` bloğuna alınmamıştır; geçici bir LLM hatası `self._unavailable("llm_unavailable")` döndürmek yerine doğrudan istisna fırlatır.
  2. `_extract_specific_detail` (satır 217-236) ve `_extract_micro_signal` (satır 238-253) birebir aynı koddur; `_extract_specific_detail` ve `_extract_temporal_signal` (satır 255-267) hiçbir yerden çağrılmaz.
  3. `_extract_micro_signal` satır 251'de `return evidence[:50]` ile kanıt metnini 50 karakterde keserek prompt'a yarım cümle göndermektedir.
- **Düzeltme Talimatı:**
  `llm_gateway.query_json_chain` çağrısını `try/except Exception:` içine alıp `self._unavailable("llm_unavailable", context_id=...)` döndürün; ölü `_extract_specific_detail` metodunu silin ve `evidence[:50]` sınırını `evidence[:240]` yapın.

---

### [CORE-A-16] [P2] `aspasia/interface.py`: `build_oversight_digest` İçinde `has_content` Bayrağının `unknown` Kotaları Yazdırması ve Büyük Harf / HTTP URL Reddi

- **Dosya Yolu ve Satır Numarası:** `agent_core/aspasia/interface.py:48-59, 457-465, 896-906`
- **Önem Derecesi:** **P2 (Orta — Yanlış Denetim Özeti ve Hedef URL Reddi)**
- **Kanıt:**
  1. `agent_core/aspasia/interface.py:896-906`:
     ```python
     quotas = []
     for provider in ("groq", "cerebras"):
         q = QuotaReader(gateway=gateway).snapshot(provider)
         if q["status"] not in ("unknown", "unavailable"):
             has_content = True
         quotas.append(f"{provider}:{q['status']}" + ...)
     if quotas and has_content:
         lines.append("KOTA: " + " | ".join(quotas))
     ```
     `has_content` fonksiyon genelindeki bayraktır ve satır 833 (`ROUTING`) veya satır 886 (`MALİYET`) tarafından zaten `True` yapılmaktadır. Bu yüzden her iki sağlayıcının kotası `"unknown"` veya `"unavailable"` olsa bile `if quotas and has_content:` `True` olmakta ve `"KOTA: groq:unknown | cerebras:unknown"` satırı her zaman eklenmektedir.
  2. `_normalize_target_url` (satır 56-59) `http://` ile başlayan URL'leri `https://`'e çevirmek yerine `""` döndürerek reddetmekte; `parts.netloc` küçük harfe çevrilmediği ve `_TARGET_RE` (satır 457) büyük harf kabul etmediği için `https://Instagram.com/kullanici` gibi URL'ler reddedilmektedir.
- **Düzeltme Talimatı:**
  Satır 896'da yerel `has_quota_content = False` değişkeni tanımlayıp `if quotas and has_quota_content:` kontrolü yapın; `_normalize_target_url` içinde `http` şemasını `https` olarak normalize edin ve `parts.netloc.lower()` kullanın.

---

### [CORE-A-17] [P2] `aspasia/mobile_coach.py`: İstemciden Gelen Dark Triad ve Manipülasyon Alanlarının Sistem Prompt'una "Sunucudan Gelen Bağlam" Olarak Enjekte Edilmesi

- **Dosya Yolu ve Satır Numarası:** `agent_core/aspasia/mobile_coach.py:38-47, 109-112, 126`
- **Önem Derecesi:** **P2 (Orta — Epistemik/Etik Sözleşme İhlali ve İstemci Verisine Aşırı Güven)**
- **Kanıt:**
  `agent_core/aspasia/mobile_coach.py:38-47, 110`:
  ```python
  _ALLOWED_CONTEXT_FIELDS = (
      "username",
      "communication_tone",
      "core_passions",
      "narcissism",
      "machiavellianism",
      "psychopathy",
      "manipulation_strategy",
      "suggested_opening_message",
  )
  ...
  if ctx:
      lines = ["BİLİŞSEL PROFİL ÖZETİ (sunucudan gelen yapılandırılmış bağlam):"]
  ```
  İstemciden (mobil uygulamadan) gelen HTTP isteğindeki `profile_context` sözlüğü doğrulanmadan `"sunucudan gelen yapılandırılmış bağlam"` başlığıyla sistem prompt'una yazılmakta ve klinik/manipülatif `"narcissism"`, `"machiavellianism"`, `"psychopathy"`, `"manipulation_strategy"` alanlarını taşımaktadır.
- **Düzeltme Talimatı:**
  `_ALLOWED_CONTEXT_FIELDS` içindeki Dark Triad ve manipülasyon anahtarlarını kaldırıp `HolisticProfile` şemasındaki (`core_passions`, `sensitivities`, `boundary_signals`, `communication_tone`, `suggested_opening_message`) alanlarla sınırlandırın; başlığı `"İSTEMCİ TARAFINDAN SAĞLANAN PROFİL ÖZETİ"` olarak güncelleyin.

---

### [CORE-A-18] [P2] `pulse_engine.py` ve `strata_engine.py`: Dar Emoji Regex'i (`[😀-🙏]`), Yanlış `emoji_diversity` Hesabı ve Sabit Z-Skor Referansları

- **Dosya Yolu ve Satır Numarası:**
  - `agent_core/engines/pulse_engine.py:29-50`
  - `agent_core/engines/strata_engine.py:48-53`
- **Önem Derecesi:** **P2 (Orta — Eksik Emoji Kapsamı ve Normalize Edilmemiş Metrik)**
- **Kanıt:**
  1. `re.findall("[😀-🙏]", x)` yalnızca `U+1F600..U+1F64F` aralığını yakalar; `U+1F300..U+1F5FF` (🔥, ❤️, 💀), `U+1F680..U+1F6FF` (🚀), `U+1F900..U+1F9FF` (🤣, 🥰, 🤔) ve `U+2600..U+27BF` (☀️, ✅) bloklarındaki yaygın emojileri tamamen kaçırır.
  2. `pulse_engine.py:30`'daki `emo = float(np.mean([len(re.findall("[😀-🙏]", x)) for x in texts]))` ne çeşitliliği (`diversity`) ne de karakter başına yoğunluğu (`density`) ölçer; yalnızca gönderi başına ham emoji sayısını ölçer.
  3. `pulse_engine.py:34-39` içindeki `(base, sd)` değerleri sabit kodlanmış sayılardır.
- **Düzeltme Talimatı:**
  Emoji regex'ini `r"[\U0001F300-\U0001FAFF\u2600-\u27BF]"` olarak genişletin; `pulse_engine` içinde hem karakter/kelime başına yoğunluğu hem de benzersiz emoji oranını doğru adlandırın.

---

### [CORE-A-19] [P2] `seismos_engine.py`: 15 Kelimelik Çekimsiz ve Olumsuzlamasız `POS`/`NEG` Sözlüğü Nedeniyle Kırık `polarity()` Hesabı

- **Dosya Yolu ve Satır Numarası:** `agent_core/engines/seismos_engine.py:13-15, 31-36, 82-105` ve `agent_core/domain/pillar_models.py:80-86`
- **Önem Derecesi:** **P2 (Orta — Duygu Kırılması Tespiti Körlüğü)**
- **Kanıt:**
  `POS = {"harika", "mutlu", "güzel", "iyi", "süper", "happy", "great", "teşekkürler"}` ve `NEG = {"yorgun", "bitkin", "stres", "kötü", "üzgün", "sad", "bıktım"}` yalnızca tam kelime eşleşmesi (`x in POS`) yapar. Türkçe çekimli kelimeler (`mutluyum`, `yoruldum`, `üzgünüm`, `stresli`) eşleşmezken, `"mutlu değilim"` veya `"iyi değil"` ifadeleri `+1.0` pozitif polarite üretir. Ayrıca `SeismicKind` enum'undaki 6 değerden 4'ü (`ACTIVITY_BURST`, `STYLE_INVERSION`, `ENGAGEMENT_SHOCK`, `CADENCE_BREAK`) `SeismosEngine` içinde hiç kodlanmamıştır.
- **Düzeltme Talimatı:**
  `polarity(t)` fonksiyonuna Türkçe kök/önek eşleşmesi ve `"değil"`, `"yok"`, `"hiç"`, `"not"`, `"never"` olumsuzlama penceresi ekleyin; `SeismicKind` içindeki diğer kırılma türlerini (etkileşim şoku, aktivite patlaması) `SeismosEngine._sync` içinde gerçek metriklerle hesaplayın.

---

### [CORE-A-20] [P2] `task_execution_state.py` ve `responsibility.py`: `dict` Snapshot'ta `"unknown"` Dönen `task_state_fields`, Sabit `decision_state="unknown"` ve `seal_trail` Boşlukları

- **Dosya Yolu ve Satır Numarası:**
  - `agent_core/domain/task_execution_state.py:26-49`
  - `agent_core/domain/responsibility.py:180-197`
- **Önem Derecesi:** **P2 (Orta — Durum Projeksiyonu ve Mühür Doğrulama Boşluğu)**
- **Kanıt:**
  1. `task_execution_state.py:28-29`: `status = getattr(snapshot, "status", snapshot)` çağrısı, `snapshot` bir `dict` olduğunda tüm sözlüğü döndürür ve `task_phase="unknown", task_outcome="unknown"` üretir. Satır 39'daki `getattr(snapshot, "completion_policy", None)` da `dict` üzerinde selalu `None` döner. Ayrıca satır 49'daki `"decision_state": "unknown"` hiçbir koşulda değişmez.
  2. `responsibility.py:180-185`: `seal_trail` içinde `claimed` değeri `"halted_frequency"`, `"partially_completed"`, `"unavailable"` veya `""` olduğunda hem `if` hem `elif` atlanır ve satır 196'da `violation: None, sealed: True` olarak mühürlenir.
- **Düzeltme Talimatı:**
  `task_state_fields` içinde `snapshot.get(...) if isinstance(snapshot, dict) else getattr(snapshot, ...)` kullanın; `seal_trail` içinde `"halted_frequency"` ve `"unavailable"` durumlarını `elif` dalına ekleyin ve bilinmeyen `claimed` statülerinde `violation = "INVALID_CLAIMED_STATUS"` atayın.

---

### [CORE-A-21] [P3] `memory_models.py`: Docstring'deki `extra="forbid"` Beyanına Rağmen Tüm Modellerde `extra="allow"` Kullanılması ve `model_copy` Alias Senkronizasyon Hatası

- **Dosya Yolu ve Satır Numarası:** `agent_core/domain/memory_models.py:9-11, 52, 69, 74-90, 102, 107-116`
- **Önem Derecesi:** **P3 (Düşük — Şema Hijyeni ve Alias Tutarlılığı)**
- **Kanıt:**
  `PassionProfile._sync_aliases` ve `FrictionProfile._sync_aliases` yalnızca alanlardan biri boşken kopyalama yapar. `model_copy(update={"core_passions": ["yeni"]})` çağrıldığında `passion_anchors` eski değerinde kalır; `model_copy(update={"core_passions": []})` çağrıldığında ise eski `passion_anchors` değeri `core_passions` listesini tekrar eski haliyle doldurur.
- **Düzeltme Talimatı:**
  `model_copy` içinde `update` sözlüğünde açıkça güncellenen alanın alias karşılığını da `update` sözlüğüne yansıtın.

---

### [CORE-A-22] [P3] `mirror_truth.py`: Kanıt Yokken Üretilen `"bilinmeyen_caba"` / `"belirsiz_frekans"` Yer Tutucularının Prompt'a ve `ResonanceCalculator`'a Sızması

- **Dosya Yolu ve Satır Numarası:** `agent_core/agents/mirror_truth.py:71-72, 100-101, 147-155, 182, 201`
- **Önem Derecesi:** **P3 (Düşük — Placeholder Sızıntısı)**
- **Kanıt:**
  `_find_anchors` kelime bulamadığında `["bilinmeyen_caba"]`, `_extract_core_frequency` ise `"belirsiz_frekans"` döndürür. Bu değerler hem LLM prompt'una (satır 100-101) hem LLM hata fallback'ine (satır 148-151) hem de `ResonanceCalculator._user_evidence_terms` terim havuzuna gerçek kullanıcı kanıtı gibi girer.
- **Düzeltme Talimatı:**
  `_find_anchors` kelime bulamadığında `[]`, `_extract_core_frequency` ise `""` (veya `ResonanceCalculator._SKIP_VALUE_STRINGS` içinde tanımlı bir değer) döndürmelidir.

---

### [CORE-A-23] [P3] `target_psyche_profiler.py`: `profile_all` Metodunun Paralel Yerine Sıralı Çalışması

- **Dosya Yolu ve Satır Numarası:** `agent_core/agents/target_psyche_profiler.py:8, 341-346`
- **Önem Derecesi:** **P3 (Düşük — Performans)**
- **Kanıt:**
  `profile_all` üç lensi `await asyncio.gather(...)` yerine sıralı olarak `await` etmektedir.
- **Düzeltme Talimatı:**
  `return await asyncio.gather(self.profile_passions(payload), self.profile_frictions(payload), self.profile_cognitive(payload))` olarak güncelleyin.

---

### [CORE-A-24] [P3] `osint_investigator.py` ve `pillar_models.py`: Hiçbir Zaman Doldurulmayan Şema Alanları

- **Dosya Yolu ve Satır Numarası:** `agent_core/agents/osint_investigator.py:30-31`, `agent_core/domain/pillar_models.py:59`
- **Önem Derecesi:** **P3 (Düşük — Ölü Şema Alanları)**
- **Kanıt:**
  `OsintProfile.digital_footprint_score`, `OsintProfile.dark_web_hits` ve `FrequencyReport.phase_shifts` alanları hiçbir kod yolunda doldurulmamaktadır.
- **Düzeltme Talimatı:**
  `digital_footprint_score` değerini gözlenen platform/e-posta/telefon sayısından deterministik olarak hesaplayın veya kullanılmayan alanları şemadan kaldırın.
