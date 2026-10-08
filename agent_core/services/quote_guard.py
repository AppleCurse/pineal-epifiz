import re
from difflib import SequenceMatcher
from typing import Dict, List, Tuple, Any, Optional

#: Hakem statüleri: yalnız bu statülerde `evidence_quote` DOLU olabilir, çünkü
#: AutonomousVerifier kanıt alanlarını SADECE kanıt kapısından geçen oydan
#: doldurur (evidence_url ∈ gerçek arama sonuçları + alıntı kaynak metninde
#: birebir var + destek oranı ≥ eşik). Dolayısıyla bu alıntılar zaten gerçek
#: bir kaynağa demirlidir; QuoteGuard korpusuna girmeleri kaynak-doğruluğunu
#: gevşetmez.
VERIFIED_QUOTE_STATUSES = frozenset({"DOĞRULANDI", "YALAN", "ÇELİŞKİLİ"})

#: Hakemin ürettiği kararlı iddia kimliği biçimi (autonomous_verifier._stable_claim_id).
_CLAIM_ID_RE = re.compile(r"\bclm_[0-9a-f]{20}\b")

def _normalize(text: str) -> str:
    t = (text or "").lower()
    t = re.sub(r"[\s\u00a0]+", " ", t)
    t = re.sub(r"[^\w\sçığöşüÇİĞÖŞÜ%.,:;@#()\-/'\"+]", "", t)
    return t.strip()

def _source_corpus(source_texts: List[str]) -> List[str]:
    return [_normalize(s) for s in source_texts if s and str(s).strip()]

def best_score(quote: str, corpus: List[str]) -> float:
    """Alıntının korpustaki EN YÜKSEK benzerlik skoru (0..1).

    [FAZ B · B5] Eşiğin ÖLÇÜLEBİLMESİ için karar tek bir sayıya indirilir:
    skor >= eşik ise alıntı "gerçek". Skor ledger'a yazılır, operatör daha
    sonra doğru/yanlış etiketi koyar; eşik o etiketlerden kalibre edilir.
    """
    q = _normalize(quote)
    if len(q) < 4:
        return 0.0
    best = 0.0
    for raw in corpus:
        # Korpus da aynı ölçekte normalize edilir: büyük/küçük harf ve noktalama
        # farkı yüzünden KAYNAKTA BİREBİR VAR olan alıntı "yok" sayılıyordu
        # (q alt-case, src değil -> `q in src` hiç tutmuyordu).
        src = _normalize(raw)
        if len(src) < 4:
            continue
        if q in src:
            return 1.0
        if len(src) <= len(q) * 3:
            best = max(best, SequenceMatcher(None, q, src).ratio())
        else:
            step = max(1, len(q) // 2)
            for i in range(0, len(src) - len(q) + 1, step):
                window = src[i:i + len(q) * 2]
                best = max(best, SequenceMatcher(None, q, window).ratio())
                if best >= 1.0:
                    return 1.0
    return round(best, 6)


def quote_matches(
    quote: str,
    corpus: List[str],
    threshold: Optional[float] = None,
    *,
    observe: bool = False,
    task_id: str = "",
    claim_id: str = "",
) -> bool:
    """Alıntı kaynak korpustaki herhangi bir metin parçasıyla eşleşiyor mu?

    [FAZ B · B5] ``threshold`` artık SABİT 0.70 değil: verilmezse kalibrasyon
    modülü ölçülen eşiği verir (veri yoksa 0.70 varsayılan kalır, kaynak
    ``varsayılan`` olarak raporlanır). Elle değer verilmesi hâlâ mümkündür —
    o zaman ölçüm devre dışı kalmaz, yalnız bu çağrı için sabitlenir.
    """
    if threshold is None:
        from agent_core.services.threshold_calibration import SCOPE_QUOTE, resolved_threshold

        threshold = resolved_threshold(SCOPE_QUOTE).value
    score = best_score(quote, corpus)
    if observe:
        try:
            from agent_core.services.threshold_calibration import SCOPE_QUOTE, record

            record(
                score,
                scope=SCOPE_QUOTE,
                matched=score >= threshold,
                task_id=task_id,
                claim_id=claim_id,
                note=f"eşik={threshold:.2f}",
            )
        except Exception:  # noqa: BLE001 - kalibrasyon kaydı kararı bozamaz
            pass
    return score >= threshold


def verification_claim_index(input_data: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
    """Executor'ın koyduğu hakem raporundan `claim_id → {truth_status, claim_text,
    evidence_quote}` haritası.

    Yalnız `claim_origin == "bio_extracted"` ve kimliği olan iddialar girer.
    Kanonik gözlem kontrolleri (`canonical_observation_checks`) BİLEREK dışarıda
    kalır: onların olgusal hükmü yoktur (NO_FACTUAL_VERDICT) ve alıntı taşımazlar.
    `verifications` alanı task_executor tarafından görev başında silinip yalnız
    autonomous_verifier çıktısıyla yeniden yazılır; çağıranın enjekte ettiği bir
    rapor buraya ulaşamaz.
    """
    raw = input_data.get("verifications")
    if not isinstance(raw, dict):
        return {}
    items = raw.get("verifications")
    if not isinstance(items, list):
        return {}
    index: Dict[str, Dict[str, str]] = {}
    for item in items:
        if not isinstance(item, dict) or item.get("claim_origin") != "bio_extracted":
            continue
        claim_id = item.get("claim_id")
        if not isinstance(claim_id, str) or not _CLAIM_ID_RE.fullmatch(claim_id.strip()):
            continue
        status = item.get("truth_status")
        quote = item.get("evidence_quote")
        index[claim_id.strip()] = {
            "truth_status": status if isinstance(status, str) and status else "BİLİNMİYOR",
            "claim_text": str(item.get("claim_text") or "")[:300],
            "evidence_quote": quote.strip()[:2000] if isinstance(quote, str) else "",
        }
    return index


def verification_quote_anchors(claim_index: Dict[str, Dict[str, str]]) -> Dict[str, str]:
    """`claim_id → normalize(evidence_quote)`; yalnız kesin statülü ve alıntılı iddialar.

    BİLİNMİYOR statülü bir kayıt alıntı taşısa bile (şema gereği taşımamalı)
    korpusa GİRMEZ: kanıt kapısından geçmemiş metin QuoteGuard çıpası olamaz.
    """
    anchors: Dict[str, str] = {}
    for claim_id, entry in claim_index.items():
        if entry.get("truth_status") not in VERIFIED_QUOTE_STATUSES:
            continue
        norm = _normalize(entry.get("evidence_quote") or "")
        if len(norm) >= 4:
            anchors[claim_id] = norm
    return anchors


def _link_finding_to_claim(
    finding: Dict[str, Any],
    real_quotes: List[str],
    claim_index: Dict[str, Dict[str, str]],
    anchors: Dict[str, str],
    stats: Dict[str, Any],
) -> Optional[str]:
    """Bulguyu hakem iddiasına DETERMİNİSTİK bağlar; statüyü yalnız kod yazar.

    Kural sırası:
      1. LLM `source_claim_id` yazdıysa hakemin GERÇEKTEN ürettiği bir kimlik
         olmalı; değilse bağ düşer (bulgu değil), `rejected_claim_ids` artar.
      2. Kimlik yoksa, bulgunun ayakta kalan alıntılarından biri bir hakem
         `evidence_quote`'u ile eşleşiyorsa o iddiaya bağlanır (quote_match).
      3. `verification_status` HER DURUMDA hakem kaydından kopyalanır; LLM'in
         yazdığı statü bağ yoksa silinir, bağ varsa ezilir.
    """
    basis: Optional[str] = None
    claim_id = finding.get("source_claim_id")
    if claim_id is not None:
        if isinstance(claim_id, str) and claim_id.strip() in claim_index:
            claim_id = claim_id.strip()
            basis = "llm_claim_id"
        else:
            stats["rejected_claim_ids"] += 1
            claim_id = None
    if claim_id is None:
        for cid, anchor in anchors.items():
            if any(quote_matches(q, [anchor]) for q in real_quotes):
                claim_id, basis = cid, "quote_match"
                break
    if claim_id is None:
        finding["source_claim_id"] = None
        finding["verification_status"] = None
        finding["verification_link_basis"] = None
        return None
    finding["source_claim_id"] = claim_id
    finding["verification_status"] = claim_index[claim_id]["truth_status"]
    finding["verification_link_basis"] = basis
    stats["linked_to_verification"] += 1
    return claim_id

def guard_report(report: Dict[str, Any], input_data: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """DepthReport sözlüğünü alıntı-bazlı temizler.

    [A-KAPANIŞ] Ek olarak her ayakta kalan bulguyu hakem iddiasına bağlar
    (`source_claim_id` / `verification_status` / `verification_link_basis`) ve
    rapor düzeyinde `verification_trace` yazar: hangi hakem sonucu hangi
    DepthReport bulgusunu etkiledi, izlenebilir olsun.
    """
    tp = (input_data.get("target_profile") or {})
    visual = input_data.get("visual_evidence") or {}
    audit = input_data.get("follower_audit") or {}
    timing = input_data.get("timing_forensics") or {}
    
    source_texts: List[str] = [str(tp.get("bio", ""))]
    source_texts += [str(p) for p in (tp.get("posts") or [])]
    source_texts += [str(t) for t in (tp.get("post_times") or [])]
    source_texts += [str(tp.get("username", ""))]
    if tp.get("followers"):
        source_texts.append(f"followers {tp.get('followers')}")
    if tp.get("following"):
        source_texts.append(f"following {tp.get('following')}")
    if tp.get("post_count"):
        source_texts.append(f"post_count {tp.get('post_count')}")
        
    for key in ("detected_objects", "environment_and_places", "activity_signals"):
        source_texts += [str(x) for x in (visual.get(key) or [])]
    if visual.get("aesthetic_style"):
        source_texts.append(str(visual["aesthetic_style"]))
    if visual.get("visual_evidence_summary"):
        source_texts.append(str(visual["visual_evidence_summary"]))
        
    source_texts += [str(e) for e in (audit.get("evidence") or [])]
    if audit.get("verdict"):
        source_texts.append(f"{audit.get('verdict')} engagement_rate {audit.get('engagement_rate', '')}")
    if timing.get("machine_note"):
        source_texts.append(str(timing.get("machine_note")))

    # [FAZ 4] Public-web kaynak metinleri (crawl4ai zenginleştirmesinden
    # available=True iken çağıranın koyduğu gerçek sayfa metinleri). Alan
    # yoksa korpus BİREBİR aynı kalır — mevcut guard davranışı değişmez.
    for src in (input_data.get("public_web_sources") or []):
        text = src.get("text") if isinstance(src, dict) else None
        if isinstance(text, str) and text.strip():
            source_texts.append(text[:20000])

    # [A-KAPANIŞ / A1] Hakem alıntıları meşru kaynak korpusudur. Ölçülen kusur:
    # DepthAnalyst, prompt'taki hakem `evidence_quote`'unu birebir alıntılayıp
    # çelişki üretiyordu; korpus yalnız profil metinlerinden oluştuğu için
    # QuoteGuard bu KANITLI çelişkiyi "uydurma alıntı" sayıp imha ediyordu
    # (dropped_fake_quote=1, contradictions=[]). Yalnız kesin statülü hakem
    # alıntıları eklenir (bkz. verification_quote_anchors); `verifications`
    # yoksa korpus BİREBİR aynı kalır.
    claim_index = verification_claim_index(input_data)
    anchors = verification_quote_anchors(claim_index)
    source_texts += [claim_index[cid]["evidence_quote"] for cid in anchors]

    corpus = _source_corpus(source_texts)
    stats = {
        "checked": 0,
        "dropped_no_quote": 0,
        "dropped_fake_quote": 0,
        "dropped_topics": [],
        "kept": 0,
        "verification_quote_sources": len(anchors),
        "linked_to_verification": 0,
        "rejected_claim_ids": 0,
    }
    linked: List[Dict[str, Any]] = []

    def clean(findings: List[Dict[str, Any]], section: str) -> List[Dict[str, Any]]:
        out = []
        for f in findings or []:
            stats["checked"] += 1
            quotes = (f or {}).get("evidence_quotes") or []
            if not quotes:
                stats["dropped_no_quote"] += 1
                stats["dropped_topics"].append((f or {}).get("topic", "?"))
                continue
            real = [q for q in quotes if quote_matches(q, corpus)]
            if not real:
                stats["dropped_fake_quote"] += 1
                stats["dropped_topics"].append((f or {}).get("topic", "?"))
                continue
            f["evidence_quotes"] = real
            claim_id = _link_finding_to_claim(f, real, claim_index, anchors, stats)
            if claim_id is not None:
                linked.append({
                    "section": section,
                    "topic": f.get("topic", "?"),
                    "source_claim_id": claim_id,
                    "verification_status": f["verification_status"],
                    "link_basis": f["verification_link_basis"],
                })
            out.append(f)
            stats["kept"] += 1
        return out

    if isinstance(report.get("reality_findings"), list):
        report["reality_findings"] = clean(report.get("reality_findings"), "reality_findings")
    if isinstance(report.get("contradictions"), list):
        report["contradictions"] = clean(report.get("contradictions"), "contradictions")

    rationale = report.get("reality_rationale") or ""
    rationale_quotes = re.findall(r'"([^"]{6,})"', rationale) if rationale else []
    if rationale and not any(quote_matches(q, corpus) for q in rationale_quotes):
        report["reality_rationale"] = rationale + " [not: gerekçede kaynak-alıntı doğrulanamadı]"
        stats["rationale_unverified"] = True

    # [A-KAPANIŞ / A4] Rapor düzeyi iz: WRITE (verifier) → READ (prompt) →
    # USE (alıntı/claim_id) → ALTER DECISION (hangi bulgu/çelişki) zinciri
    # deterministik olarak burada kapanır. LLM'in yazdığı hiçbir şey bu
    # nesneye doğrudan girmez; yalnız kodun doğruladığı bağlar girer.
    rationale_claim_ids = sorted(
        {cid for cid in _CLAIM_ID_RE.findall(rationale) if cid in claim_index}
    )
    report["verification_trace"] = {
        "claims_available": len(claim_index),
        "quote_anchors": len(anchors),
        "linked_findings": linked,
        "claim_ids_used": sorted({*(item["source_claim_id"] for item in linked), *rationale_claim_ids}),
        "rationale_claim_ids": rationale_claim_ids,
        "rationale_anchored_to_verification": bool(anchors) and any(
            quote_matches(q, list(anchors.values())) for q in rationale_quotes
        ),
        "rejected_claim_ids": stats["rejected_claim_ids"],
    }

    report["quote_guard"] = stats
    return report, stats
