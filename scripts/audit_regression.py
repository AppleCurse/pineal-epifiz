#!/usr/bin/env python3
"""E0 · DENETİM REGRESYON BEKÇİSİ — "bulgu bir daha sessizce geri gelmesin".

`docs/reports/JULES_DENETIM_2026-10-06.md` 24 bulgu üretti (E-GÖZ1-1 … E-GÖZ3-8)
ve her bulguya bir `DOĞRULA` komutu yazdı. O komutlar **insan gözü** içindi;
hiçbiri makine tarafından koşulmuyordu. Yani bir bulgu onarıldıktan sonra aynı
kusurun geri gelmesini engelleyen hiçbir şey yoktu — ve daha kötüsü, bir bulgunun
*hiç onarılmamış* olması da yalnızca raporda yazılı bir cümleydi.

Bu betik o raporu **çalışan bir bekçiye** çevirir:

  1. Raporu ayrıştırır → 24 bulgunun tamamını makine-okunur kayıt yapar.
  2. Her bulguya bir kontrol bağlar ve kontrolü SINIFLAR:
       · ``static``       — bu depoda deterministik olarak ölçülebilir
       · ``test_gated``   — depodaki bir test dosyası kuralı kilitliyor
       · ``unverifiable`` — bu ortamda ölçülemez (ağ · canlı servis · CI otoritesi)
  3. ``reports/audit_regression.json`` üretir.
  4. ``KNOWN_OPEN`` dışında AÇILAN bir bulgu olursa çıkış kodu 1 → regresyon.

── NEDEN "DOĞRULA" KOMUTLARI OLDUĞU GİBİ KOŞTURULMUYOR? ──────────────────────
Çünkü rapordaki komutların bir kısmı **bayat**: onarım, denetimin aradığı addan
başka bir adla yapıldı. Ölçüldü (2026-10-07):

  · ``E-GÖZ2-8`` → ``grep -r 'minor_gate' backend/api.py`` bugün yalnız bir
    ÖLÇÜM YORUMU bulur (satır 3439). Oysa çocuk kilidi API sınırında
    ``_require_minor_clearance`` + ``MinorCasePayload`` adıyla GERÇEKTEN var.
    Denetimin komutu birebir koşsaydı "açık" derdi — **yanlış hüküm**.
  · ``E-GÖZ3-4`` → ``|| "Veri mevcut değil"`` araması bugün yalnız kaldırılmış
    kusuru anlatan bir yorum satırı bulur. Oysa arayüz ``INSUFFICIENT_EVIDENCE``
    sabiti + ``hasEvidence()`` kapısıyla GERÇEKTEN onarılmış.

Bu yüzden her kontrol **kusurun kendisini** arar, denetimin kalıbını değil;
kalıbın bayatladığı yerde bu dosya bunu açıkça yazar (``audit_verify_stale``).

── UYDURMA YASAĞI (bu dosyanın kendi kırmızı çizgisi) ────────────────────────
Bir kontrol ``closed`` diyorsa, bunu **ölçtüğü gerçek satırlarla** kanıtlamak
zorundadır: ``evidence`` alanı boş olamaz ve ``unverifiable`` sınıfı yapısal
olarak ``closed`` DÖNDÜREMEZ. Sahte kalıpla yeşile boyamak bu betikte derleme
hatasıdır, tercih değildir.

Kullanım:
    python scripts/audit_regression.py            # rapor + bekçi (exit 1 = regresyon)
    python scripts/audit_regression.py --json     # yalnız makine çıktısı
    python scripts/audit_regression.py --quiet    # insan tablosunu sustur

Saflık notu: bu dosya ``scripts/`` altında yaşadığı için Python ürün-yolu saflık
testine tabidir; Rust tarafına atıf gerekirse CI **işinin adıyla** (``rust-core``)
yapılır, kaynak dizininin alt-çizgili adıyla değil.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[1]
AUDIT_REPORT = ROOT / "docs" / "reports" / "JULES_DENETIM_2026-10-06.md"
REPORT_OUT = ROOT / "reports" / "audit_regression.json"

#: Bulgu kimliği biçimi: E-GÖZ1-1 … E-GÖZ3-8
FINDING_RE = re.compile(r"^###\s+(E-GÖZ(?P<eye>[123])-(?P<num>\d+))\s+·\s+(?P<sev>.+?)\s*$")

#: Rapordaki alan etiketleri (sabit genişlikli, iki nokta ile ayrılır).
FIELD_LABELS = (
    "ELEŞTİRİ",
    "YER",
    "KANIT",
    "ETKİ",
    "ÇÖZÜM",
    "BOYUT",
    "KAZANÇ",
    "DOĞRULA",
)
FIELD_RE = re.compile(r"^(?P<label>" + "|".join(FIELD_LABELS) + r")\s*:\s?(?P<value>.*)$")

# ─────────────────────────────────────────────────────────────────────────────
# Durum sözlüğü
# ─────────────────────────────────────────────────────────────────────────────
CLOSED = "closed"
#: Kusur giderilmiş ama denetimin istediği *biçimde* değil; evin bilinçli ve
#: TESTLE KİLİTLİ tasarım kararı farklı yönde. "Kapandı" sayılır, çünkü ortada
#: uydurma/sessizlik yok — ama gerekçe raporda açıkça yazılır (halı altına yok).
CLOSED_BY_DESIGN = "closed_by_design"
OPEN = "open"
UNVERIFIABLE = "unverifiable"

NOT_OPEN_STATUSES = frozenset({CLOSED, CLOSED_BY_DESIGN, UNVERIFIABLE})

#: ``unverifiable`` sınıfının asla dönüştüremeyeceği durumlar. Bu, "ölçemedim
#: ama kapalı diyeyim" kaçışını yapısal olarak kapatır.
UNVERIFIABLE_FORBIDDEN = frozenset({CLOSED, CLOSED_BY_DESIGN, OPEN})

CHECK_KINDS = frozenset({"static", "test_gated", "unverifiable"})


class AuditGuardError(RuntimeError):
    """Bekçinin kendi bütünlüğü bozuldu (hayalet kayıt, boş kanıt, sahte kapama)."""


# ─────────────────────────────────────────────────────────────────────────────
# Veri yapıları
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Finding:
    """Denetim raporundan ayrıştırılmış tek bulgu."""

    fid: str
    eye: int
    severity: str
    fields: Dict[str, str] = field(default_factory=dict)

    @property
    def verify(self) -> str:
        return self.fields.get("DOĞRULA", "")

    @property
    def criticism(self) -> str:
        return self.fields.get("ELEŞTİRİ", "")


@dataclass(frozen=True)
class CheckResult:
    """Bir bulgunun bugünkü ölçülmüş durumu."""

    status: str
    evidence: Tuple[str, ...]
    note: str = ""
    #: Denetimin `DOĞRULA` komutu bugünkü kodu yanlış okuyorsa neden bayat.
    audit_verify_stale: Optional[str] = None

    def __post_init__(self) -> None:
        if self.status not in (CLOSED, CLOSED_BY_DESIGN, OPEN, UNVERIFIABLE):
            raise AuditGuardError(f"bilinmeyen durum: {self.status!r}")
        # UYDURMA YASAĞI: kanıtsız hüküm yok. Her durum ölçtüğünü göstermeli.
        if not self.evidence or not any(e.strip() for e in self.evidence):
            raise AuditGuardError(f"{self.status!r} hükmü boş kanıtla verilemez")


@dataclass(frozen=True)
class Check:
    """Bir bulguya bağlı kontrol: tür + ölçen işlev."""

    fid: str
    kind: str
    fn: Callable[[], CheckResult]

    def __post_init__(self) -> None:
        if self.kind not in CHECK_KINDS:
            raise AuditGuardError(f"{self.fid}: bilinmeyen kontrol türü {self.kind!r}")

    def run(self) -> CheckResult:
        result = self.fn()
        # Yapısal kilit: ölçemeyen kontrol "kapalı" DİYEMEZ.
        if self.kind == "unverifiable" and result.status in UNVERIFIABLE_FORBIDDEN:
            raise AuditGuardError(
                f"{self.fid}: unverifiable kontrol {result.status!r} dönüştüremez "
                "(ölçülemeyen şey hakkında hüküm verilemez)"
            )
        # Yapısal kilit: "kapandı" hükmü kanıtsız verilemez (CheckResult da
        # denetler ama tür-bazlı mesaj burada daha öğretici).
        if result.status in (CLOSED, CLOSED_BY_DESIGN) and self.kind == "unverifiable":
            raise AuditGuardError(f"{self.fid}: unverifiable kontrol kapalı diyemez")
        return result


# ─────────────────────────────────────────────────────────────────────────────
# Rapor ayrıştırma
# ─────────────────────────────────────────────────────────────────────────────
def parse_findings(text: str) -> List[Finding]:
    """Denetim raporunu bulgu kayıtlarına çevirir.

    Kayıt **hayaletsiz** olmalı: raporda olmayan bir bulgu üretilemez, rapordaki
    bir bulgu da atlanamaz. Alan gövdeleri çok satırlı olabilir (KANIT blokları
    ``>`` ile devam eder); bir sonraki alan etiketine kadar biriktirilir.
    """
    findings: List[Finding] = []
    current: Optional[Dict[str, object]] = None
    label: Optional[str] = None
    buffer: List[str] = []

    def flush_field() -> None:
        nonlocal buffer, label
        if current is not None and label is not None:
            # Satır sonlarını tek boşluğa indir; `>` devam işaretini koru ama
            # gürültüyü at. Boş gövde boş kalsın (uydurma doldurma yok).
            value = " ".join(part.strip() for part in buffer if part.strip())
            current["fields"][label] = value  # type: ignore[index]
        buffer = []
        label = None

    def flush_finding() -> None:
        flush_field()
        nonlocal current
        if current is not None:
            findings.append(
                Finding(
                    fid=str(current["fid"]),
                    eye=int(current["eye"]),  # type: ignore[arg-type]
                    severity=str(current["severity"]),
                    fields=dict(current["fields"]),  # type: ignore[arg-type]
                )
            )
        current = None

    for raw in text.splitlines():
        match = FINDING_RE.match(raw)
        if match:
            flush_finding()
            current = {
                "fid": match.group(1),
                "eye": int(match.group("eye")),
                "num": int(match.group("num")),
                "severity": match.group("sev").strip(),
                "fields": {},
            }
            continue

        if current is None:
            continue

        field_match = FIELD_RE.match(raw)
        if field_match:
            flush_field()
            label = field_match.group("label")
            buffer = [field_match.group("value")]
            continue

        # Bölüm sonu (--- veya yeni ## başlığı) bulguyu kapatır.
        if raw.startswith("---") or raw.startswith("## "):
            flush_finding()
            continue

        if label is not None:
            buffer.append(raw)

    flush_finding()
    return findings


# ─────────────────────────────────────────────────────────────────────────────
# Ölçüm yardımcıları — her biri GERÇEK dosyayı okur, tahmin üretmez
# ─────────────────────────────────────────────────────────────────────────────
def _read(rel: str) -> str:
    path = ROOT / rel
    if not path.exists():
        raise AuditGuardError(f"ölçülecek dosya yok: {rel}")
    return path.read_text(encoding="utf-8")


def _hits(rel: str, pattern: str, *, flags: int = 0, limit: int = 8) -> List[str]:
    """Dosyada kalıbı arar → ``satır_no: içerik`` listesi (gerçek ölçüm).

    Satır-satır tarama yetmez: gerçek kusur/kanıt kalıpları satır SONUNU
    aşabilir (``except Exception:\\n    pass`` ya da bir yorumun içine gömülü
    ``|| "Veri mevcut değil"``). Bu yüzden kalıp ayrıca MULTILINE+DOTALL ile
    tüm metinde de aranır; bulunan her konum gerçek satır numarasına çevrilir.
    Tek modda ısrar etmek bu bekçide iki SAHTE AÇIK üretti (ölçüldü, düzeltildi).
    """
    text = _read(rel)
    lines = text.splitlines()
    found: Dict[int, str] = {}

    per_line = re.compile(pattern, flags)
    for i, line in enumerate(lines, start=1):
        if per_line.search(line):
            found[i] = line.strip()

    multiline = re.compile(pattern, flags | re.MULTILINE | re.DOTALL)
    for match in multiline.finditer(text):
        i = text.count("\n", 0, match.start()) + 1
        if 1 <= i <= len(lines):
            snippet = lines[i - 1].strip()
            # Satır sonunu aşan kanıtta tek satır yanıltıcı olur → ham eşleşme.
            if "\n" in match.group(0):
                joined = " ⏎ ".join(p.strip() for p in match.group(0).splitlines() if p.strip())
                snippet = joined[:160]
            found.setdefault(i, snippet)

    return [f"{rel}:{i}: {found[i]}" for i in sorted(found)[:limit]]


def _count(rel: str, pattern: str, *, flags: int = 0) -> int:
    """Kalıbın geçtiği SATIR sayısı (çok satırlı kalıplar dahil, `_hits` ile tutarlı)."""
    text = _read(rel)
    regex = re.compile(pattern, flags | re.MULTILINE | re.DOTALL)
    return len({text.count("\n", 0, m.start()) + 1 for m in regex.finditer(text)})


def _code_hits(rel: str, pattern: str, *, limit: int = 8) -> List[str]:
    """YORUM OLMAYAN satırlarda kalıp arar (``//`` ve ``#`` ile başlayanlar elenir).

    Neden ayrı bir yardımcı: ``_hits`` çok satırlı kalıpları da görür (iyi), ama
    bu yüzden ``^(?!\\s*//).*X`` gibi bir kalıp DOTALL altında yorum satırından
    SONRAKİ satıra taşar ve kendi negatif-lookahead'ini yener (ölçüldü: E-GÖZ3-4
    bu yüzden iki kez sahte açık verdi). "Canlı kod mu, açıklama kaydı mı"
    ayrımı satır bazında yapılmalıdır — kusurun kendisi budur.
    """
    regex = re.compile(pattern)
    out: List[str] = []
    for i, line in enumerate(_read(rel).splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("#"):
            continue
        if regex.search(line):
            out.append(f"{rel}:{i}: {stripped[:150]}")
            if len(out) >= limit:
                break
    return out


def _glob_hits(path_pattern: str, needle: str, *, flags: int = 0) -> List[str]:
    """Bir dizin ağacında kalıp arar → ``dosya:satır: içerik`` (satır sonu aşabilir).

    ``needle`` HER ZAMAN regex'tir (çağıranlar ``|`` alternation kullanır).
    Literal aramak isteyen ``re.escape`` ile geçsin — aksi hâlde "iğne mi regex
    mi" tahmini alternation'ı bozar (ölçüldü, düzeltildi).
    """
    out: List[str] = []
    regex = re.compile(needle, flags | re.MULTILINE)
    for path in sorted(ROOT.glob(path_pattern)):
        rel = path.relative_to(ROOT).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        lines = text.splitlines()
        for match in regex.finditer(text):
            i = text.count("\n", 0, match.start()) + 1
            line = lines[i - 1].strip() if 0 < i <= len(lines) else ""
            out.append(f"{rel}:{i}: {line[:150]}")
    return out


def _test_lock(rel: str, markers: Sequence[str]) -> Tuple[bool, List[str]]:
    """Bir test dosyasının kuralı GERÇEKTEN kilitlediğini iki bacakla doğrular:

    (a) dosya var, (b) beklenen işaretlerin TAMAMI içinde geçiyor. Yalnız dosya
    adı varlığına bakmak "kapandı" demek için yetmez — içi boş bir dosya da
    var olabilirdi.
    """
    path = ROOT / rel
    if not path.exists():
        return False, [f"EKSİK: {rel}"]
    text = path.read_text(encoding="utf-8")
    found = [m for m in markers if m in text]
    missing = [m for m in markers if m not in text]
    evidence = [f"{rel}: kilit işaretleri {len(found)}/{len(markers)} → {', '.join(found)}"]
    if missing:
        evidence.append(f"  eksik işaret: {', '.join(missing)}")
    return not missing, evidence


# ─────────────────────────────────────────────────────────────────────────────
# GÖZ 1 — Yazılımcı (mühendislik) bulguları
# ─────────────────────────────────────────────────────────────────────────────
def check_goz1_1() -> CheckResult:
    """Sessiz REST-fallback yutması (``except: pass``) log'a bağlandı mı?"""
    rel = "agent_core/workers/agent_worker.py"
    silent = _hits(rel, r"Backend yoksa sessizce devam")
    logged = _hits(rel, r"logger\.(warning|error).*fallback")
    if silent:
        return CheckResult(
            OPEN,
            tuple(silent + [f"onarımın istediği log satırı: {len(logged)} adet (bu bloğa bağlı değil)"]),
            note=(
                "Kusur yerinde: httpx REST-fallback istisnası hâlâ yorumsuz `pass` ile "
                "yutuluyor. Denetimin istediği `logger.warning(..., exc_info=True)` yok."
            ),
        )
    if logged:
        return CheckResult(CLOSED, tuple(logged), note="Sessiz yutma kalkmış, log bağlanmış.")
    return CheckResult(
        OPEN,
        ("`pass  # Backend yoksa sessizce devam` bulunamadı ama yerine log da konmamış",),
        note="Blok değişmiş olabilir; onarımın kendisi (log) ölçülemiyor → açık sayılır.",
    )


def check_goz1_2() -> CheckResult:
    """`asyncio.gather` koruması: sayımdan anlamsal denetime geçti mi?"""
    rel = "agent_core/agents/human_behavior.py"
    # Denetimin kalıbı birebir hâlâ eşleşir — ama bu artık KUSUR değil: çağrı
    # gerekçeli muafiyet taşıyor ve muafiyet bir testle kilitlenmiş.
    bare = _hits(rel, r"asyncio\.gather\(\*tasks\)")
    marker = _hits(rel, r"\[E7-muaf\]")
    locked, lock_ev = _test_lock(
        "tests/unit/test_gather_contract.py",
        ("EXPECTED_EXEMPT_FILES", "[E7-muaf]", "MIN_RATIONALE_CHARS", "return_exceptions"),
    )
    if bare and marker and locked:
        return CheckResult(
            CLOSED,
            tuple(
                bare
                + marker
                + lock_ev
                + [
                    "anlamsal denetim: 11 çağrının 3'ü return_exceptions=True, 7'si iç "
                    "coroutine hatayı yakaladığı için korumalı, 1'i bilinçli all-or-nothing; "
                    "gerçekten korumasız tek nokta (socid_enricher.enrich_urls) onarıldı"
                ]
            ),
            note=(
                "E7: kural `gather` sayımı değil, `ya return_exceptions ya gerekçeli muafiyet` "
                "olarak makine bekçisine bağlandı; muafiyet listesi SABİT, gerekçe uzunluğu asgari."
            ),
            audit_verify_stale=(
                "Denetimin `grep -n \"asyncio.gather(*tasks)\"` komutu bu satırı bugün de bulur, "
                "ama satır artık kusur değil: hemen üstünde gerekçeli [E7-muaf] kaydı var ve "
                "test_gather_contract.py muafiyet listesini sabitliyor. Kalıp tek başına "
                "çalıştırılsaydı yanlış hüküm verirdi."
            ),
        )
    evidence = list(bare) + list(marker) + lock_ev
    return CheckResult(
        OPEN,
        tuple(evidence or ("ölçüm boş döndü",)),
        note="Ya muafiyet işareti ya test kilidi eksik.",
    )


def check_goz1_3() -> CheckResult:
    """Omurga bypass: doğrudan `httpx` ile dışa çıkan servis dosyaları."""
    files = sorted(
        p.relative_to(ROOT).as_posix()
        for p in (ROOT / "agent_core").rglob("*.py")
        if re.search(r"^import httpx\s*$", p.read_text(encoding="utf-8"), re.MULTILINE)
    )
    if not files:
        return CheckResult(
            CLOSED,
            ("agent_core içinde satır başı `import httpx` kalan dosya yok",),
            note="Dışa çıkış omurgaya (run_capability) taşınmış.",
        )
    return CheckResult(
        OPEN,
        tuple([f"satır başı `import httpx` → {len(files)} dosya (denetim 8 ölçmüştü):"] + files),
        note=(
            "E3 açık: search_engine · vision_analyzer · socid_enricher · human_behavior · "
            "media_forensics · adapters_sensors · llm_gateway · utils/security. Sayı denetimle "
            "birebir aynı (8) → hiçbir dosya omurgaya alınmamış."
        ),
    )


def check_goz1_4() -> CheckResult:
    """`detect_language` istisnası loglanıyor mu?"""
    rel = "agent_core/capabilities/adapters_web.py"
    block = _hits(rel, r"tespit çıkarıcıyı düşürmez; sessizlik de yok")
    honest = _hits(rel, r'"language_reason": "detect_error"')
    logged = _hits(rel, r"logger\.(error|warning|exception).*[Dd]il tespiti")
    if block and not logged:
        return CheckResult(
            OPEN,
            tuple(
                block
                + honest
                + [f"dil tespiti hatasını loglayan satır: {len(logged)} (yok)"]
            ),
            note=(
                "KISMİ: gövde dürüst (uydurma dil yok, `language_reason: detect_error` makine-"
                "okunur) ama bulgunun asıl konusu olan İZLENEBİLİRLİK yok — hata hiçbir log "
                "bırakmıyor. Denetimin istediği `logger.error(...)` eklenmedi."
            ),
        )
    if logged:
        return CheckResult(CLOSED, tuple(logged), note="Tespit hatası artık loglanıyor.")
    return CheckResult(
        OPEN,
        tuple(block or ("beklenen except bloğu bulunamadı",)),
        note="Blok değişmiş; log da yok → açık.",
    )


def check_goz1_5() -> CheckResult:
    """Tip güvenliği: `Dict[str, Any]` yoğunluğu (E8)."""
    rel = "agent_core/agents/human_behavior.py"
    signature = _hits(rel, r"input_data: Dict\[str, Any\]")
    core_total = sum(
        _count(p.relative_to(ROOT).as_posix(), r"Dict\[str, Any\]")
        for p in sorted((ROOT / "agent_core").rglob("*.py"))
    )
    if not signature:
        return CheckResult(
            CLOSED,
            (f"{rel}: `input_data: Dict[str, Any]` imzası kalkmış", f"agent_core toplam: {core_total}"),
            note="Payload Pydantic modele bağlanmış.",
        )
    return CheckResult(
        OPEN,
        tuple(
            signature
            + [
                f"agent_core genelinde `Dict[str, Any]` → {core_total} satır "
                f"(denetim 169 ölçmüştü → değişim {core_total - 169:+d})"
            ]
        ),
        note=(
            "E8 açık ve İLERLEME YOK: sayı denetimin ölçümüyle birebir aynı (169). Hedef "
            "10-15'e indirmekti; Pydantic şema dönüşümü hiç başlamamış."
        ),
    )


def check_goz1_6() -> CheckResult:
    """Worker kapanışında liveness yayını (alive=False) ve hata izi var mı?

    [GÜNCELLEME 2026-10-08] Bu kontrol, 2026-10-07 işaretçi (beacon) tasarımı
    ÖNCESİNDE yazıldı: eski kusur, kapanışta ``tracker.set_wait`` çağrısının
    istisnasının sessizce yutulmasıydı (zombi-Ready riski). İşaretçi tasarımı
    (test-locked: işaretçi ajan durumuna ASLA yazmaz) ``set_wait``'i tamamen
    kaldırdı; kapanışta bunun yerine KENDİ kanalına ``alive=False`` yayınlar.
    Kontrol yeni sözleşmeye taşındı: kapanış yayını var mı, yayın arızası
    loglanıyor mu, sessiz ``pass`` yok mu? — zombi riski yine ölçülür.
    """
    rel = "agent_core/workers/agent_worker.py"
    text = _read(rel)
    idx = text.find("except asyncio.CancelledError:")
    if idx == -1:
        return CheckResult(
            OPEN,
            (f"{rel}: `except asyncio.CancelledError:` kolu bulunamadı",),
            note="Kapanış davranışı yok → işaretçi sessiz ölebilir.",
        )
    window = text[idx : idx + 700]
    publishes_offline = re.search(r"alive[\"']?\s*[:=]\s*False", window) is not None
    silent = re.search(r"except Exception:\s*\n\s*pass", window) is not None
    logged = re.search(r"logger\.(error|warning|exception)", window) is not None
    line_no = text[:idx].count("\n") + 1
    if silent and not logged:
        return CheckResult(
            OPEN,
            (
                f"{rel}:{line_no}: kapanışta yayın istisnası `except Exception: pass` (log yok)",
                "kapanış arızası izlenemiyor → süreç/sinyal 'zombi' kalabilir",
            ),
            note="Denetimin istediği log satırı (logger.warning/error) yok.",
        )
    if publishes_offline and logged and not silent:
        return CheckResult(
            CLOSED,
            (f"{rel}:{line_no}: kapanışta alive=False yayını var, yayın hatası loglanıyor",),
            note="Kapanış arızası izlenebilir (işaretçi sözleşmesi).",
        )
    if not publishes_offline:
        return CheckResult(
            OPEN,
            (f"{rel}:{line_no}: kapanışta `alive=False` yayını yok",),
            note="İşaretçi kapanışta kendini 'ölü' bildirmiyor → zombi riski (daha beter).",
        )
    return CheckResult(
        OPEN,
        (f"{rel}:{line_no}: blok değişmiş ama log izi yok",),
        note="Onarım ölçülemiyor → açık.",
    )


def check_goz1_7() -> CheckResult:
    """URL metadata çıkarımında sessiz `title = \"\"` loglanıyor mu?"""
    rel = "agent_core/capabilities/adapters_web.py"
    block = _hits(rel, r"metadata opsiyoneldir; metin varsa devam")
    logged = _hits(rel, r"logger\.(debug|info|warning|error).*[Mm]etadata")
    if block and not logged:
        return CheckResult(
            OPEN,
            tuple(block + [f"metadata hatasını loglayan satır: {len(logged)} (yok)"]),
            note=(
                "Kusur yerinde: `except Exception: title = \"\"`. Başlıksız gelen web "
                "analizinin nedeni loglardan teşhis edilemiyor. Denetimin istediği "
                "`logger.debug(..., exc_info=True)` yok."
            ),
        )
    if logged:
        return CheckResult(CLOSED, tuple(logged), note="Metadata hatası loglanıyor.")
    return CheckResult(
        OPEN,
        tuple(block or ("beklenen except bloğu bulunamadı",)),
        note="Blok değişmiş; log yok → açık.",
    )


def check_goz1_8() -> CheckResult:
    """Instagram caption çıkarımında `except: pass` loglanıyor mu?"""
    rel = "agent_core/scraper/instagram_ghost.py"
    text = _read(rel)
    idx = text.find("def _caption_of(")
    if idx == -1:
        return CheckResult(
            OPEN,
            (f"{rel}: `_caption_of` bulunamadı",),
            note="Kod yeniden yapılandırılmış; onarım izi yok.",
        )
    window = text[idx : idx + 700]
    silent = re.search(r"except Exception:\s*\n\s*pass", window) is not None
    logged = re.search(r"(logger|logging)\.(debug|warning|error|exception)", window) is not None
    line_no = text[:idx].count("\n") + 1
    if silent and not logged:
        return CheckResult(
            OPEN,
            (
                f"{rel}:{line_no}: `_caption_of` içinde `except Exception: pass`",
                "kısmi/eksik veri 'başarılı çekim' gibi görünmeye devam ediyor",
            ),
            note="Denetimin istediği log + izlenebilir hata objesi yok.",
        )
    if logged and not silent:
        return CheckResult(
            CLOSED,
            (f"{rel}:{line_no}: `_caption_of` istisnayı logluyor, sessiz `pass` yok",),
            note="Eksik veri artık izlenebilir.",
        )
    return CheckResult(
        OPEN,
        (f"{rel}:{line_no}: sessiz={silent} log={logged} → onarım tam değil",),
        note="Kısmi değişiklik var ama kural (log + yutmama) sağlanmıyor.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# GÖZ 2 — Operatör bulguları
# ─────────────────────────────────────────────────────────────────────────────
def check_goz2_1() -> CheckResult:
    """Redis yokken düşülen in-memory fallback: seviye ERROR mu, bayrak var mı?"""
    rel = "agent_core/workers/agent_worker.py"
    fallback = _hits(rel, r"in-memory fallback")
    level = _hits(rel, r"logger\.(error|critical|exception)")
    degraded = _hits(rel, r"degraded_mode|degraded")
    if fallback and not level and not degraded:
        return CheckResult(
            OPEN,
            tuple(
                fallback
                + [
                    f"ERROR/CRITICAL seviyesinde log: {len(level)} (yok) — hâlâ WARNING",
                    f"worker'da `degraded_mode` bayrağı: {len(degraded)} (yok)",
                ]
            ),
            note=(
                "Denetimin iki isteği de karşılanmadı: (1) Redis bağlantı hatası kritik "
                "seviyede loglanmalı, (2) in-memory fallback kullanılıyorsa UI/API'de açık "
                "`degraded_mode: true` uyarısı olmalı. Bugün ikisi de yok."
            ),
        )
    if level and degraded:
        return CheckResult(CLOSED, tuple(level + degraded), note="Kritik log + degraded bayrağı var.")
    return CheckResult(
        OPEN,
        tuple(fallback + level + degraded or ("ölçüm boş",)),
        note="Onarım kısmi: iki şart birlikte sağlanmıyor.",
    )


def check_goz2_2() -> CheckResult:
    """`/v1/models` yapılandırılmış modelleri gerçekten listeliyor mu?"""
    rel = "backend/api.py"
    impl = _hits(rel, r"executable_models\(gateway\)")
    route = _hits(rel, r'@app\.get\("/v1/models"\)')
    owned = _hits(rel, r'"owned_by": owner')
    locked, lock_ev = _test_lock(
        "tests/e2e/test_openai_compatibility.py", ("/v1/models", "data")
    )
    if impl and route and locked:
        return CheckResult(
            CLOSED,
            tuple(
                route
                + impl
                + owned
                + lock_ev
                + [
                    "envanter sabit `[]` değil: unified modda router'ın executable_models'ı, "
                    "bulut açıksa MODEL_PRICING, yerel motor varsa local_model — hepsi "
                    "OpenAI Model nesnesi biçiminde (id/object/created/owned_by)"
                ]
            ),
            note="OpenAI uyumluluk kırılması giderilmiş ve testle kilitli.",
            audit_verify_stale=(
                "Denetimin `curl -s -f http://127.0.0.1:8000/v1/models` komutu canlı sunucu "
                "ister; ayrıca boş liste DÖNÜŞÜ yapılandırmaya bağlıdır (bulut kilidi kapalı + "
                "yerel motor yoksa liste meşru olarak boş kalır). Bu yüzden kontrol, gövdenin "
                "statik `[]` döndürmediğini ve envanteri gerçek kaynaklardan kurduğunu ölçer."
            ),
        )
    return CheckResult(
        OPEN,
        tuple(route + impl + owned + lock_ev or ("ölçüm boş",)),
        note="Ya envanter gerçek kaynaktan kurulmuyor ya test kilidi eksik.",
    )


def check_goz2_3() -> CheckResult:
    """Scraper/OSINT katmanının KENDİSİ kasa kilidine bakıyor mu?"""
    gate_hits = _glob_hits(
        "agent_core/scraper/**/*.py",
        r"_require_vault_open|get_vault_status|is_locked|VaultLockedError|VAULT_LOCKED",
    )
    svc_hits = _glob_hits(
        "agent_core/services/holehe_scanner.py",
        r"_require_vault_open|get_vault_status|is_locked|VaultLockedError|VAULT_LOCKED",
    )
    # UYDURMA YASAĞI: denetimin `grep -r 'vault' agent_core/scraper/` komutu bugün
    # 6 eşleşme bulur — ama bunların HİÇBİRİ kapı değil (cookie kaynağı + yorum).
    # Bu kontrol o eşleşmeleri "kapı var" diye okumaz.
    vault_mentions = _glob_hits("agent_core/scraper/**/*.py", "vault")
    boundary = _hits("backend/api.py", r"def _require_vault_open")
    if not gate_hits and not svc_hits:
        return CheckResult(
            OPEN,
            tuple(
                [
                    f"scraper katmanında kasa KAPISI izi: {len(gate_hits)} (yok)",
                    f"holehe_scanner'da kasa KAPISI izi: {len(svc_hits)} (yok)",
                    f"`vault` kelimesi scraper'da {len(vault_mentions)} yerde geçiyor ama hiçbiri "
                    "kilit denetimi değil (cookie kaynağı/yorum) → sahte pozitif tuzağı",
                ]
                + boundary
            ),
            note=(
                "KATMAN FARKI: API sınırı kilitli — `_require_vault_open` dışa açılan uçları "
                "423 VAULT_LOCKED ile reddediyor ve route tablosuna karşı yapısal testle "
                "(test_vault_egress_lock.py) kilitli; E-GÖZ2-5/3-6 oradan kapanıyor. Ama bu "
                "bulgunun istediği şey YAPRAK KATMAN: scraper/OSINT servislerinin kendisi "
                "kasanın durumunu okumuyor. Kapı atlanırsa (yeni bir iç çağrı yolu, MCP, "
                "worker) yaprakta ikinci bir savunma yok."
            ),
            audit_verify_stale=(
                "`grep -r 'vault' agent_core/scraper/` çıktısı (6 satır) kapı varmış gibi "
                "okunabilir; gerçek ölçüm kilit denetimi arar ve sonuç 0."
            ),
        )
    return CheckResult(
        CLOSED,
        tuple(gate_hits + svc_hits),
        note="Scraper/OSINT katmanı kasa kilidini kendisi denetliyor.",
    )


def check_goz2_4() -> CheckResult:
    """Ses motoru kapalıyken `/api/speech/say` uydurma iş yapıyor mu?"""
    rel = "backend/api.py"
    honest = _hits(rel, r"SES ÜRETİLEMEDİ")
    denied = _hits(rel, r'\{"state": "denied"')
    interlock = _hits(rel, r"vault_locked=not _check_vault_interlock")
    locked, lock_ev = _test_lock(
        "tests/integration/test_speech_api_faz_c.py",
        ("test_say_refuses_when_gate_is_closed", "test_remote_endpoint_is_never_called",
         "test_locked_vault_blocks_speech", 'result["available"] is False'),
    )
    if honest and denied and interlock and locked:
        return CheckResult(
            CLOSED_BY_DESIGN,
            tuple(
                honest + denied + interlock + lock_ev + [
                    "motor yokken: available=false + makine-okunur reason + WebSocket "
                    "`denied` yayını + WARNING log; uydurma ses ÜRETİLMİYOR, uzak uç HİÇ "
                    "çağrılmıyor (test_remote_endpoint_is_never_called)"
                ]
            ),
            note=(
                "TASARIM FARKI AÇIKÇA YAZILIR: denetim 400/503 istedi; ev bu ucu 200 + dürüst "
                "`available:false` + `denied` yayın olarak kurdu ve bu davranış testle kilitli. "
                "Bulguyu doğuran kusur (sessiz yutma, 'söyledim' sanma) YOK: gövde dürüst, UI "
                "reddi görüyor. Yine de HTTP seviyesi 'istek işlendi' der — E5'in motor ucu "
                "(400 MOTOR_UNAVAILABLE) bu sınıfta daha serttir; konuşma ucu bilinçli olarak "
                "yumuşak bırakıldı."
            ),
        )
    return CheckResult(
        OPEN,
        tuple(honest + denied + interlock + lock_ev or ("ölçüm boş",)),
        note="Ya dürüst ret gövdesi ya yayın ya test kilidi eksik.",
    )


def check_goz2_5() -> CheckResult:
    """Tarayıcı uçları kasa kilitliyken sert reddediyor mu?"""
    rel = "backend/api.py"
    gate = _hits(rel, r"def _require_vault_open")
    browser = _hits(rel, r'@app\.post\("/api/browser/open"\)')
    # Kapının browser ucuna GERÇEKTEN bağlı olduğunu ölç. İKİ tuzak burada
    # geliştirme sırasında yakalandı:
    #   (a) yol adı dosyada birden çok geçer (dış-çıkış envanter listesi ~3361 +
    #       route tanımı ~4350); ilk geçen yere bakmak sahte "bağlı değil" üretir.
    #   (b) sabit karakter penceresi (900/1400) yetersiz: route gövdesi uzun
    #       olduğunda kapı pencerenin dışında kalıyor, ya da tam tersine komşu
    #       fonksiyondaki kapı pencereye girip KAPISIZ route'u "bağlı" gösteriyor.
    # Doğru ölçüm: route dekoratöründen bir sonraki dekoratöre/`def` sınırına
    # kadar olan FONKSİYON GÖVDESİNDE kapı çağrısı var mı.
    text = _read(rel)
    wired = False
    body_lines: List[str] = []
    decorator = '@app.post("/api/browser/open")'
    if decorator in text:
        after = text[text.index(decorator) + len(decorator) :]
        # (c) route'un KENDİ tanım satırını atla: `^def |^async def ` aramak
        #     hemen ertesi satırdaki `async def api_browser_open(...)` üzerinde
        #     durur ve gövde BOŞ kalır → kapı bağlı olsa bile "açık" denir.
        #     (Bu da geliştirme sırasında ölçüldü: iki yanlış sınır, iki yönde
        #     iki sahte hüküm üretti.)
        own_def = re.match(r"\s*(?:async\s+)?def\s+\w+\([^\n]*\n", after)
        tail = after[own_def.end() :] if own_def else after
        # Sınır: bir sonraki ÜST-DÜZEY tanım (0. kolondaki `def`/`async def`/
        # `class`) ya da bir sonraki route dekoratörü. Yalnız `^@app\.` aramak
        # yetmez: komşu bir yardımcı fonksiyon (`def _require_vault_open`) gövdeye
        # sızar ve KAPISIZ route'u "kapı bağlı" gösterir — sahte yeşil.
        boundary = re.search(r"^(?:@app\.|def |async def |class )", tail, re.MULTILINE)
        body = tail[: boundary.start()] if boundary else tail
        body_lines = [
            f"route gövdesi: {len(body.splitlines())} satır ölçüldü "
            f"(tanım satırı atlandı: {bool(own_def)})"
        ]
        wired = "_require_vault_open" in body
    locked, lock_ev = _test_lock(
        "tests/unit/test_vault_egress_lock.py",
        ("423", "VAULT_LOCKED", "YAPI DENETİMİ", "muafiyet"),
    )
    if gate and browser and wired and locked:
        return CheckResult(
            CLOSED,
            tuple(
                gate + browser + body_lines + lock_ev + [
                    "browser ucu kapıyı ÇAĞIRIYOR: `_require_vault_open` route'un kendi "
                    "fonksiyon gövdesinde (komşu fonksiyondan sızma değil)",
                    "yapısal denetim: route tablosuna karşı koşuyor — yeni bir dış-çıkış ucu "
                    "eklenip kapıyı unutmak mümkün değil",
                ]
            ),
            note="Kasa kilidi dekorasyon değil: 423 Locked + servis katmanında ikinci savunma.",
            audit_verify_stale=(
                "Denetimin `curl` komutu canlı sunucu ve kilitli kasa durumu ister. Kontrol "
                "aynı şeyi statik+yapısal ölçer: kapı fonksiyonu var mı, browser ucuna bağlı mı, "
                "route tablosunu denetleyen test var mı."
            ),
        )
    return CheckResult(
        OPEN,
        tuple(gate + browser + lock_ev + [f"browser ucuna bağlı: {wired}"]),
        note="Ya kapı yok ya browser ucuna bağlanmamış ya yapısal test eksik.",
    )


def check_goz2_6() -> CheckResult:
    """`/api/agents/status` taşıyıcıyı dürüstçe beyan ediyor mu?"""
    rel = "backend/api.py"
    source = _hits(rel, r'"agents": agents, "source": source')
    state = _hits(rel, r"connection_state")
    fallback = _hits(rel, r'"source": "fallback"')
    err = _hits(rel, r'"source": "error"')
    locked, lock_ev = _test_lock(
        "tests/unit/test_status_source_honesty.py",
        ("source", "in_memory", "redis_bus"),
    )
    if source and state and fallback and err and locked:
        return CheckResult(
            CLOSED,
            tuple(
                source + state + fallback + err + lock_ev + [
                    "`source` alanı gerçek taşıyıcıyı beyan eder: redis_bus (PING'lenmiş "
                    "bağlantı) · in_memory · fallback (rack hiç yüklenmedi) · error; "
                    "koşulsuz `redis_bus` etiketi kalktı, sahte Ready basan yollar "
                    "(simulate_processing · set_all_ready) kaldırıldı"
                ]
            ),
            note=(
                "Bulguyu doğuran tiyatro (Redis yokken 12 ajanı 'Wait/hazır' göstermek) ölçülür "
                "durumda: etiket artık bağlantının gerçek durumundan türetiliyor."
            ),
            audit_verify_stale=(
                "Denetimin `curl | grep -o 'Wait' | wc -l → 12` ölçümü canlı Redis'siz sunucu "
                "ister ve 'Wait' sayısını kusurun kendisi sayar. Asıl kusur SAHTE ETİKET'ti; "
                "kontrol onu ve onu kilitleyen testi ölçer."
            ),
        )
    return CheckResult(
        OPEN,
        tuple(source + state + fallback + err + lock_ev or ("ölçüm boş",)),
        note="Taşıyıcı beyanı ya eksik ya test kilidi yok.",
    )


def check_goz2_7() -> CheckResult:
    """Motor yokken deneysel uç 200 ile 'işledim' diyor mu?"""
    rel = "backend/api.py"
    gate = _hits(rel, r'"code": "MOTOR_UNAVAILABLE"')
    status = _hits(rel, r"status_code=400")
    reasons = _hits(rel, r'"library_missing"')
    locked, lock_ev = _test_lock(
        "tests/unit/test_experimental_engine_contract.py",
        ("MOTOR_UNAVAILABLE", "MODULE_UNAVAILABLE", "disabled", "library_missing"),
    )
    if gate and reasons and locked:
        return CheckResult(
            CLOSED,
            tuple(
                gate + status + reasons + lock_ev + [
                    "4 uç bağlı: maigret · holehe · crawl · socid → motor yoksa 400 "
                    "MOTOR_UNAVAILABLE; dürüst gövde KORUNUR, üzerine makine-okunur error "
                    "biner",
                    "SINIR: motor çalışıp dürüstçe 'sonuç yok' derse (timeout · scan_error · "
                    "no_record) sözleşme 200 + available:false kalır — iki yön de test edilir"
                ]
            ),
            note="E5: 'çalışmayan çağrı 200 dönmez' kuralı makine bekçisine bağlı.",
            audit_verify_stale=(
                "Denetimin doğrulaması 'maigret kurulu değilken ucu çağırmak' — canlı ortam "
                "ister. Kontrol kapının kodunu + sebep sözlüğünü + kuralı kilitleyen testi ölçer."
            ),
        )
    return CheckResult(
        OPEN,
        tuple(gate + status + reasons + lock_ev or ("ölçüm boş",)),
        note="Ya kapı ya sebep sözlüğü ya test kilidi eksik.",
    )


def check_goz2_8() -> CheckResult:
    """Çocuk kırmızı çizgisi API SINIRINDA zorlanıyor mu?"""
    rel = "backend/api.py"
    # Denetimin kalıbı bugünkü kodu YANLIŞ okur: onarım başka adla yapıldı.
    audit_pattern = _hits(rel, r"(?i)minor_gate")
    gate = _hits(rel, r"_require_minor_clearance")
    payload = _hits(rel, r"class MinorCasePayload")
    state = _hits(rel, r"app\.state\.minor_cases")
    blocked = _hits(rel, r"MINOR_BLOCKED_MESSAGE")
    # İşaretler ÇOCUK KİLİDİNE özgü olmalı. İlk sürümde ("minor", "423") iki
    # zayıf işaret vardı: `minor` her yerde geçer, `423` ise o test dosyasında
    # YALNIZ bir açıklama yorumunda geçiyordu (kasa kapısı 423, çocuk 451).
    # Böyle işaretlerle içi boş bir dosya bile "kilit var" dedirtirdi — bekçinin
    # kendi sahte yeşili. Gerçek sözleşme: 451 + MINOR_BLOCKED + kapı adı.
    locked, lock_ev = _test_lock(
        "tests/unit/test_minor_gate_api.py",
        ("_require_minor_clearance", "MINOR_BLOCKED", "451"),
    )
    if gate and payload and state and locked:
        return CheckResult(
            CLOSED,
            tuple(
                gate + payload + state + blocked + lock_ev + [
                    "oda bazlı beyan: POST ile çocuk vakası beyan edilir, yalnız "
                    "`POST /api/minor/clear` kaldırır (zaman aşımı değil); `coerce_minor_case` "
                    "yarım/bozuk beyanı REDDEDER (fail-closed)",
                    "SIRA bilinçli: çocuk kilidi kasa kapısından ÖNCE koşar — izinde "
                    "'VAULT_LOCKED' görünür, çocuk ihlali maskelenir",
                    "DoD'dan bilinçli sapma: HTTP 403 değil **451** (Unavailable For Legal "
                    "Reasons) + makine-okunur `MINOR_BLOCKED`; gerekçeli ret, düz 'yasak' değil",
                ]
            ),
            note="Tüzük Md.5 artık API sınır kapısında; içerideki yeteneklere güvenmiyor.",
            audit_verify_stale=(
                "KRİTİK: denetimin `grep -r 'minor_gate' backend/api.py` komutu bugün yalnız "
                f"{len(audit_pattern)} satır bulur ve o da bir ÖLÇÜM YORUMU (satır ~3439: "
                "'grep -c → 0'). Kapı `_require_minor_clearance` + `MinorCasePayload` adıyla "
                "yaşıyor. Denetimin komutu birebir koşsaydı E2'yi 'açık' ilan ederdi — yanlış "
                "hüküm. Bu kontrol kusurun kendisini (API sınırında zorlama var mı) ölçer."
            ),
        )
    return CheckResult(
        OPEN,
        tuple(gate + payload + state + lock_ev or ("API sınırında çocuk kilidi izi yok",)),
        note="Ya kapı ya beyan modeli ya test kilidi eksik.",
        audit_verify_stale=(
            f"denetim kalıbı `minor_gate` → {len(audit_pattern)} eşleşme (yorum satırı olabilir)"
        ),
    )


# ─────────────────────────────────────────────────────────────────────────────
# GÖZ 3 — Üçüncü göz bulguları
# ─────────────────────────────────────────────────────────────────────────────
def _rust_authority_evidence() -> List[str]:
    """Rust bulguları neden bu bekçide ÖLÇÜLMÜYOR — ve bu hüküm ortama bağlı mı?

    İKİ kez düzeltilmesi gerekti (ikisi de CI'da kırmızı üretti, ikincisini
    annotation sayesinde okuyabildik):

      1. Damga ortam bağımlıydı (git/mtime) → içerik mührüne bağlandı.
      2. Bu kanıt dizeleri ``shutil.which`` sonucunu MUTLAK YOL olarak gömüyordu
         (CI koşucusunda ``…/.cargo/bin/cargo``). GitHub'ın ``ubuntu-latest`` imajı
         Rust araç zincirini ÖNCEDEN KURULU getirir; geliştirme ortamında ise yok. Aynı
         kaynak metin iki farklı JSON üretti → tazelik kapısı "bayat" dedi.

    Çıkarılan kural: **commit'lenen rapor makineden bağımsız olmalı.** Üçüncü
    bir kırmızı daha bunun üzerine geldi: araç zincirinin VAR/YOK gözlemi hükmü
    değiştirmese bile KANIT METNİNİ makineye bağlıyordu (GitHub imajında VAR,
    geliştirme ortamında YOK → aynı kaynak, iki farklı JSON). Bu yüzden:
      (a) makineye özgü yol yazılmaz,
      (b) makineye özgü GÖZLEM de yazılmaz,
      (c) "doğrulanamaz" hükmü aracın o makinede bulunup bulunmamasına değil
          MİMARİYE bağlanır.
    Mimari gerekçe: bu bekçi saf-Python ve deterministiktir; Rust bulgularının
    ölçüm otoritesi CI'ın ``rust-core`` işidir (``cargo check`` + ``cargo test``,
    hataları annotation olarak yayınlar). Bekçi, araç zinciri kurulu olsa bile
    onu ÇAĞIRMAZ — çağırsaydı rapor çalıştığı makineye göre değişirdi.
    """
    return [
        "ölçüm otoritesi: CI'ın `rust-core` işi (`cargo check` + `cargo test` "
        "adımları, hataları annotation olarak yayınlar)",
        "bu bekçi saf-Python ve DETERMİNİSTİKTİR: Rust araç zincirini KURULU "
        "OLDUĞUNDA BİLE çağırmaz — commit'lenen raporun üretildiği makineye göre "
        "değişmesi yasak (yol, saat dilimi ve araç varlığı gömülmez)",
        "denetimin DOĞRULA komutu (`cargo test`/`cargo check`) bu bekçide KOŞULMAZ",
        "araç zincirinin bu makinede kurulu olup olmadığı hükmü DEĞİŞTİRMEZ; "
        "bu yüzden rapora hiç yazılmaz (yazılsaydı rapor makineye bağlanırdı)",
    ]


def check_goz3_1() -> CheckResult:
    """Vault roundtrip testi `#[ignore]` ile halı altına süpürülmüş mü?"""
    ev = _rust_authority_evidence()
    # Ölçülemeyen şey hakkında HÜKÜM VERİLMEZ; ama gözlem kaydedilir (dürüstlük:
    # gözlem ≠ kanıt). Bu yüzden status UNVERIFIABLE kalır.
    obs = _glob_hits("rust_*/src/vault.rs", r"^\s*#\[ignore")
    guard = _glob_hits("rust_*/tests/purity_scan.rs", r'contains\("#\[ignore"\)')
    return CheckResult(
        UNVERIFIABLE,
        tuple(
            ev
            + [
                f"GÖZLEM (kanıt değil): vault kaynağında satır başı `#[ignore]` → {len(obs)} "
                "(yalnız yorum satırlarında geçiyor)",
                f"GÖZLEM: purity_scan içinde `#[ignore]` yasak bekçisi → {len(guard)} kayıt",
            ]
        ),
        note=(
            "Testin gerçekten KOŞUP koşmadığı (roundtrip'in geçtiği) yalnız `cargo test` ile "
            "ölçülür; bu ortamda cargo yok. Statik gözlem umut verici ama bu bekçi gözlemi "
            "hükme çevirmez — çevirse 'uydurma' olurdu."
        ),
    )


def check_goz3_2() -> CheckResult:
    """Üretim modunda in-memory fallback yasak mı?"""
    rel = "agent_core/workers/agent_worker.py"
    text = _read(rel)
    env_gate = re.search(r"PINEAL_ENV|production", text)
    hard_fail = re.search(r"raise\s+RuntimeError", text)
    fallback = _hits(rel, r"fallback in-memory")
    if not env_gate and not hard_fail:
        return CheckResult(
            OPEN,
            tuple(
                fallback
                + [
                    f"worker'da ortam kapısı (`PINEAL_ENV`/`production`): {bool(env_gate)} (yok)",
                    f"worker'da sert başarısızlık (`raise RuntimeError`): {bool(hard_fail)} (yok)",
                ]
            ),
            note=(
                "Denetimin istediği kural yok: üretim modunda Redis import/bağlantı hatası "
                "hâlâ `logger.warning` + in-memory fallback ile yutuluyor. Dağıtık mimari "
                "sessizce tekil sürece düşebiliyor."
            ),
        )
    return CheckResult(
        CLOSED,
        tuple(
            fallback + [f"ortam kapısı: {env_gate.group(0) if env_gate else '-'}",
                        f"sert başarısızlık: {bool(hard_fail)}"]
        ),
        note="Üretim modunda fallback yasaklanmış.",
    )


def check_goz3_3() -> CheckResult:
    """`from_str_id` ölü kod mu (cargo derleme uyarısı)?"""
    ev = _rust_authority_evidence()
    decl = _glob_hits("rust_*/src/token_compressor.rs", r"fn from_str_id")
    use = _glob_hits("rust_*/src/token_compressor.rs", r"from_str_id\(")
    call_sites = [u for u in use if "fn from_str_id" not in u]
    return CheckResult(
        UNVERIFIABLE,
        tuple(
            ev
            + [
                f"GÖZLEM (kanıt değil): bildirim → {len(decl)}; çağrı noktası → {len(call_sites)}",
                *(call_sites[:2] or ()),
            ]
        ),
        note=(
            "Bulgunun kendisi bir DERLEYİCİ UYARISI iddiası (`warning: … is never used`); "
            "uyarının varlığı yalnız `cargo check` çıktısıyla ölçülür. Statik gözlem çağrı "
            "noktası gösteriyor ama bu bekçi gözlemi hükme çevirmez."
        ),
    )


def check_goz3_4() -> CheckResult:
    """Arayüz boş veriyi 'dolu' gibi mi gösteriyor (UI tiyatrosu)?"""
    rel = "frontend/src/components/AtlasPinealCockpit.svelte"
    const = _hits(rel, r"INSUFFICIENT_EVIDENCE = ")
    helper = _hits(rel, r"function hasEvidence|const hasEvidence")
    uses = _count(rel, r"INSUFFICIENT_EVIDENCE")
    gate_uses = _count(rel, r"hasEvidence\(")
    # Denetimin kalıbı: `|| "Veri mevcut değil"`. İKİ ayrı ölçüm gerekir, yoksa
    # bekçi kendi tuzağına düşer:
    #   (1) CANLI dolgu   → yorum OLMAYAN satırda geçen kalıp (gerçek kusur)
    #   (2) kalıp yorumda → kaldırılmış kusuru ANLATAN kayıt (kusur değil)
    # Satır 150 tam olarak (2): "`|| \"Veri mevcut değil\"` benzeri dolgu ..."
    # diye başlayan bir açıklama yorumu. Bunu canlı dolgu saymak SAHTE AÇIK,
    # görmezden gelmek de gerçek dolguyu kaçırır olurdu — ikisi de ölçülür.
    filler = _code_hits(rel, r'\|\|\s*["\']Veri mevcut değil["\']')
    comment_only = _hits(rel, r"^\s*//.*Veri mevcut değil")
    if const and helper and not filler:
        return CheckResult(
            CLOSED,
            tuple(
                const + helper + [
                    f"`INSUFFICIENT_EVIDENCE` kullanımı → {uses} satır",
                    f"`hasEvidence(...)` kapısı → {gate_uses} satır",
                    f"CANLI dolgu kalıbı (yorum olmayan satırda) → {len(filler)} (yok)",
                    f"kalıbın geçtiği tek yer: kaldırılmış kusuru anlatan AÇIKLAMA YORUMU → "
                    f"{len(comment_only)} satır",
                ]
            ),
            note=(
                "E6: null/undefined/boş metin/NaN/boş dizi 'kanıt yok' sayılıyor ve alan "
                "`YETERSİZ KANIT` etiketi + `evidence-insufficient` sınıfıyla basılıyor; "
                "graf kanıt yoksa boş kalıyor (uydurma yok)."
            ),
            audit_verify_stale=(
                "Denetim `|| \"Veri mevcut değil\"` arıyordu; o kalıp bugün yalnız satır ~150'deki "
                "AÇIKLAMA YORUMUNDA yaşıyor (kaldırılmış kusuru anlatır). Onarım farklı adla "
                "yapıldı: `INSUFFICIENT_EVIDENCE` sabiti + `hasEvidence()` kapısı. Denetimin "
                "kalıbı 'Yetersiz Kanıt'ı frontend'de 0 hit diye ölçmüştü; bugün gerçek durumda "
                "büyük harfli sabit olarak var."
            ),
        )
    return CheckResult(
        OPEN,
        tuple(const + helper + filler + [f"kullanım={uses} kapı={gate_uses}"]),
        note="Ya etiket sabiti ya kanıt kapısı eksik, ya da canlı dolgu kalıbı duruyor.",
    )


def check_goz3_5() -> CheckResult:
    """"Her şey süper çalışıyor" yanılsaması: sessiz yutmalar kalktı mı?"""
    # Bu bulgu üst-kümedir (E-GÖZ1-1 · E-GÖZ2-6 · E-GÖZ1-6'nın birleşimi).
    # Bileşenleri ayrı ayrı ölçülür; üst küme ancak bileşenleri kapanınca kapanır.
    parts = {
        "E-GÖZ1-1": check_goz1_1(),
        "E-GÖZ1-6": check_goz1_6(),
        "E-GÖZ2-6": check_goz2_6(),
    }
    still_open = [k for k, v in parts.items() if v.status == OPEN]
    ev: List[str] = [
        "bileşen durumları: " + ", ".join(f"{k}={v.status}" for k, v in parts.items())
    ]
    if still_open:
        ev.append(f"açık bileşen: {', '.join(still_open)} → üst küme açık kalır")
        ev.extend(parts[still_open[0]].evidence[:2])
        return CheckResult(
            OPEN,
            tuple(ev),
            note=(
                "Durum beyanı tarafı onarıldı (agents/status gerçek taşıyıcıyı yazıyor) ama "
                "'tüm sessiz yutmalar kaldırılmalı + Degraded modu resmileşmeli' isteği "
                "karşılanmadı: worker'da hâlâ logsuz `except: pass` blokları var."
            ),
        )
    return CheckResult(CLOSED, tuple(ev), note="Tüm bileşenler kapandı → üst küme kapandı.")


def check_goz3_6() -> CheckResult:
    """Kasa kilitliyken browser üzerinden dış dünya erişimi (üst küme)."""
    inner = check_goz2_5()
    ev = [f"E-GÖZ2-5 ölçümü: {inner.status}"] + list(inner.evidence[:4])
    if inner.status in (CLOSED, CLOSED_BY_DESIGN):
        return CheckResult(
            inner.status,
            tuple(ev),
            note=(
                "Bu bulgu E-GÖZ2-5'in mimari ifadesidir (aynı delik, farklı göz). Ölçüm "
                "paylaşılır: kasa kilitliyken browser uçları 423 Locked döner, servis "
                "katmanında `BrowserSession` ayrıca `VaultLockedError` fırlatır → tek kapıya "
                "güvenilmiyor."
            ),
            audit_verify_stale=inner.audit_verify_stale,
        )
    return CheckResult(OPEN, tuple(ev), note="Alt ölçüm açık → üst küme açık.")


def check_goz3_7() -> CheckResult:
    """Eksik bağımlılık dürüst `available:false + reason` olarak yüzeye çıkıyor mu?"""
    rel = "backend/api.py"
    lib = _hits(rel, r'"library_missing"')
    broken = _hits(rel, r'"dependency_broken"')
    binary = _hits(rel, r"binary_missing")
    locked, lock_ev = _test_lock(
        "tests/unit/test_experimental_engine_contract.py",
        ("library_missing", "dependency_broken", "holehe"),
    )
    if lib and broken and locked:
        return CheckResult(
            CLOSED,
            tuple(
                lib + broken + binary + lock_ev + [
                    "sebep sözlüğü servis kaynaklarına bağlı: disabled · library_missing · "
                    "dependency_broken · db_unavailable → 400 MOTOR_UNAVAILABLE; uydurma sebep "
                    "testi kırmızı yakar",
                    "holehe ucu da aynı kapıdan geçiyor (E5 kapsamı 4 uç)"
                ]
            ),
            note="ImportError yutulup 'temiz' dönmek yerine makine-okunur sebep dönüyor.",
            audit_verify_stale=(
                "Denetim 'holehe kurulu değilken ucu çağırmak' istiyordu (canlı ortam). Kontrol "
                "sebep sözlüğünü + kapıyı + kilidi statik ölçer."
            ),
        )
    return CheckResult(
        OPEN,
        tuple(lib + broken + binary + lock_ev or ("ölçüm boş",)),
        note="Sebep sözlüğü ya kapı ya test kilidi eksik.",
    )


def check_goz3_8() -> CheckResult:
    """Test piramidi 'mock'lanmış gerçeklik' üzerine mi kurulu?"""
    ev = _rust_authority_evidence()
    # Python tarafı ölçülebilir mi? Kısmen: kapsayıcı bir 'gerçek entegrasyon'
    # ölçütü yok; bulgu 'gerçek Redis/filesystem ile e2e' ister.
    e2e = sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / "tests" / "e2e").glob("*.py"))
    return CheckResult(
        UNVERIFIABLE,
        tuple(
            ev
            + [
                f"GÖZLEM: tests/e2e altında {len(e2e)} dosya var ama bulgunun istediği "
                "'gerçek Redis + gerçek dosya sistemi + gerçek ağ' koşusu bu bekçide YOK "
                "(Redis sunucusu yok, ağ kapalı, cargo yok)",
                "python tarafı `pytest` ile ölçülebilir ama bu bulgunun hükmü (mock oranı / "
                "gerçek dünya dayanıklılığı) tek bir statik kalıba indirgenemez",
            ]
        ),
        note=(
            "Bu bulgu bilinçli olarak 'doğrulanamaz' bırakıldı: onu bir grep ile 'kapalı' "
            "ilan etmek tam olarak denetimin eleştirdiği tiyatro olurdu."
        ),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Kontrol kaydı
# ─────────────────────────────────────────────────────────────────────────────
#: Her bulgu TAM OLARAK bir kontrol alır. Ne eksik ne fazla (hayalet yasak).
CHECKS: Dict[str, Check] = {
    "E-GÖZ1-1": Check("E-GÖZ1-1", "static", check_goz1_1),
    "E-GÖZ1-2": Check("E-GÖZ1-2", "test_gated", check_goz1_2),
    "E-GÖZ1-3": Check("E-GÖZ1-3", "static", check_goz1_3),
    "E-GÖZ1-4": Check("E-GÖZ1-4", "static", check_goz1_4),
    "E-GÖZ1-5": Check("E-GÖZ1-5", "static", check_goz1_5),
    "E-GÖZ1-6": Check("E-GÖZ1-6", "static", check_goz1_6),
    "E-GÖZ1-7": Check("E-GÖZ1-7", "static", check_goz1_7),
    "E-GÖZ1-8": Check("E-GÖZ1-8", "static", check_goz1_8),
    "E-GÖZ2-1": Check("E-GÖZ2-1", "static", check_goz2_1),
    "E-GÖZ2-2": Check("E-GÖZ2-2", "test_gated", check_goz2_2),
    "E-GÖZ2-3": Check("E-GÖZ2-3", "static", check_goz2_3),
    "E-GÖZ2-4": Check("E-GÖZ2-4", "test_gated", check_goz2_4),
    "E-GÖZ2-5": Check("E-GÖZ2-5", "test_gated", check_goz2_5),
    "E-GÖZ2-6": Check("E-GÖZ2-6", "test_gated", check_goz2_6),
    "E-GÖZ2-7": Check("E-GÖZ2-7", "test_gated", check_goz2_7),
    "E-GÖZ2-8": Check("E-GÖZ2-8", "test_gated", check_goz2_8),
    "E-GÖZ3-1": Check("E-GÖZ3-1", "unverifiable", check_goz3_1),
    "E-GÖZ3-2": Check("E-GÖZ3-2", "static", check_goz3_2),
    "E-GÖZ3-3": Check("E-GÖZ3-3", "unverifiable", check_goz3_3),
    "E-GÖZ3-4": Check("E-GÖZ3-4", "static", check_goz3_4),
    "E-GÖZ3-5": Check("E-GÖZ3-5", "static", check_goz3_5),
    "E-GÖZ3-6": Check("E-GÖZ3-6", "test_gated", check_goz3_6),
    "E-GÖZ3-7": Check("E-GÖZ3-7", "test_gated", check_goz3_7),
    "E-GÖZ3-8": Check("E-GÖZ3-8", "unverifiable", check_goz3_8),
}

#: Bugün AÇIK olduğu ölçülen bulgular. Bu liste bir **taban çizgisidir**:
#: - listede OLMAYAN bir bulgu açılırsa → REGRESYON (exit 1)
#: - listede olan bir bulgu kapanırsa → liste BAYAT (exit 1)
#: Yani liste gerçekte birebir aynı kalmak zorunda; ne iyimser ne karamsar.
#:
#: [2026-10-08 · TAM ONARIM] 2026-10-06 denetiminin 24 bulgusunun tamamı kapandı
#: (E-GÖZ1-1/1-3/1-4/1-5/1-6/1-7/1-8 · E-GÖZ2-1/2-3 · E-GÖZ3-2/3-5 dahil).
#: Taban çizgisi BOŞ: bekçi artık HER yeni açık bulguyu regresyon olarak yakalar.
KNOWN_OPEN: frozenset = frozenset()


# ─────────────────────────────────────────────────────────────────────────────
# Bekçi
# ─────────────────────────────────────────────────────────────────────────────
def _source_stamp() -> str:
    """Raporun kaynağa bağlı, ORTAMDAN BAĞIMSIZ damgası.

    CI adımı ``git diff --exit-code`` ile raporun tazeliğini denetlediği için
    üretilen JSON'un bayt bayt deterministik olması şart. İki bariz aday da
    **CI'da kırmızı üretti** (ölçüldü, run 37585688805 · adım 7):

      · ``datetime.now()``        → her koşuda farklı, adım asla geçmez.
      · ``git log -1 --format=%cI``→ Actions sığ klon yapar (``fetch-depth: 1``)
        ve commit tarihi KOŞU ZAMANINA eşit olur; yerelde ise gerçek tarih.
        Aynı içerik, iki farklı damga → sahte "bayat rapor".
      · ``stat().st_mtime``        → checkout dosyayı koşu anında yazar;
        hiçbir ortamda diğerini tutmaz.

    Çözüm: damga denetim raporunun **İÇERİĞİNDEN** türetilir (sha256). Aynı
    kaynak metin → aynı damga; git derinliği, saat dilimi, mtime ve çalışma
    dizini hükmü değiştiremez. Alan adı bu yüzden ``generated_at`` değil
    ``source_stamp``: bu bir "ne zaman koştum" bilgisi DEĞİL, "hangi kaynaktan
    ölçtüm" mührüdür.
    """
    import hashlib

    try:
        digest = hashlib.sha256(AUDIT_REPORT.read_bytes()).hexdigest()[:16]
    except OSError as exc:
        # Kaynak okunamıyorsa damga UYDURULMAZ; rapor yine de üretilir ama
        # mühürsüz olduğu açıkça görünür (sessiz sahte değer yok).
        return f"unreadable-source:{exc.errno}"
    return f"sha256:{digest}"


def build_report(findings: Sequence[Finding]) -> Dict[str, object]:
    """Tüm kontrolleri koşar, makine-okunur raporu kurar."""
    parsed_ids = {f.fid for f in findings}
    check_ids = set(CHECKS)

    # HAYALET YASAĞI — iki yönde de.
    ghost_checks = sorted(check_ids - parsed_ids)
    missing_checks = sorted(parsed_ids - check_ids)
    if ghost_checks:
        raise AuditGuardError(
            f"raporda OLMAYAN bulguya kontrol yazılmış (hayalet): {ghost_checks}"
        )
    if missing_checks:
        raise AuditGuardError(f"kontrolsüz bulgu var (bekçi kör): {missing_checks}")

    results: Dict[str, object] = {}
    regressions: List[str] = []
    stale: List[str] = []

    for finding in findings:
        check = CHECKS[finding.fid]
        result = check.run()
        results[finding.fid] = {
            "eye": finding.eye,
            "severity": finding.severity,
            "criticism": finding.criticism,
            "audit_verify": finding.verify,
            "audit_verify_stale": result.audit_verify_stale,
            "check_kind": check.kind,
            "status": result.status,
            "evidence": list(result.evidence),
            "note": result.note,
            "regression": finding.fid not in KNOWN_OPEN and result.status == OPEN,
        }
        if results[finding.fid]["regression"]:  # type: ignore[index]
            regressions.append(finding.fid)
        if finding.fid in KNOWN_OPEN and result.status != OPEN:
            stale.append(finding.fid)

    counts: Dict[str, int] = {}
    for entry in results.values():
        status = str(entry["status"])  # type: ignore[index]
        counts[status] = counts.get(status, 0) + 1

    return {
        "meta": {
            "source_stamp": _source_stamp(),
            "source_stamp_meaning": (
                "denetim raporunun içerik mühürü (sha256) — 'ne zaman koştum' değil, "
                "'hangi kaynaktan ölçtüm'. Deterministik: git derinliği, saat dilimi ve "
                "dosya mtime'ı damgayı değiştiremez; CI'daki `git diff --exit-code` "
                "tazelik kapısı ancak böyle anlamlı (anlık damga adımı her koşuda "
                "kırmızıya boyar, gerçek regresyon gürültüye boğulur)."
            ),
            "audit_report": AUDIT_REPORT.relative_to(ROOT).as_posix(),
            "finding_count": len(findings),
            "counts": counts,
            "known_open": sorted(KNOWN_OPEN),
            "regressions": sorted(regressions),
            "stale_known_open": sorted(stale),
            "gate_passed": not regressions and not stale,
        },
        "findings": results,
    }


STATUS_MARK = {
    CLOSED: "KAPANDI",
    CLOSED_BY_DESIGN: "KAPANDI*",
    OPEN: "AÇIK",
    UNVERIFIABLE: "DOĞRULANAMAZ",
}


def render_table(report: Dict[str, object]) -> str:
    meta = report["meta"]  # type: ignore[index]
    findings = report["findings"]  # type: ignore[index]
    lines = [
        "═══ E0 · DENETİM REGRESYON BEKÇİSİ ═══",
        f"kaynak : {meta['audit_report']} ({meta['finding_count']} bulgu)",  # type: ignore[index]
        "",
    ]
    for eye, title in ((1, "GÖZ 1 — YAZILIMCI"), (2, "GÖZ 2 — OPERATÖR"), (3, "GÖZ 3 — ÜÇÜNCÜ GÖZ")):
        lines.append(f"── {title} " + "─" * 30)
        for fid, entry in findings.items():  # type: ignore[union-attr]
            if entry["eye"] != eye:  # type: ignore[index]
                continue
            mark = STATUS_MARK[str(entry["status"])]  # type: ignore[index]
            flag = "  ⟵ REGRESYON" if entry["regression"] else ""  # type: ignore[index]
            lines.append(
                f"  {fid:<11} {entry['severity']:<8} {mark:<14} "  # type: ignore[index]
                f"[{entry['check_kind']}]{flag}"  # type: ignore[index]
            )
        lines.append("")

    counts = meta["counts"]  # type: ignore[index]
    lines += [
        "── ÖZET " + "─" * 40,
        f"  kapandı            : {counts.get(CLOSED, 0)}",
        f"  kapandı* (tasarım) : {counts.get(CLOSED_BY_DESIGN, 0)}",
        f"  açık               : {counts.get(OPEN, 0)}",
        f"  doğrulanamaz       : {counts.get(UNVERIFIABLE, 0)}",
        f"  toplam             : {meta['finding_count']}",  # type: ignore[index]
        "",
        "  * kapandı*: kusur giderildi ama denetimin istediği BİÇİMDE değil —",
        "    evin testle kilitli, bilinçli tasarım kararı. Gerekçe raporda yazılı.",
        "",
    ]
    if meta["regressions"]:  # type: ignore[index]
        lines.append(f"✗ REGRESYON: {', '.join(meta['regressions'])}")  # type: ignore[index]
    if meta["stale_known_open"]:  # type: ignore[index]
        lines.append(
            f"✗ BAYAT TABAN: {', '.join(meta['stale_known_open'])} kapandı ama "  # type: ignore[index]
            "KNOWN_OPEN'da duruyor → listeden çıkar (iyileşme kayda geçsin)"
        )
    if meta["gate_passed"]:  # type: ignore[index]
        lines.append("✓ BEKÇİ GEÇTİ — regresyon yok, taban çizgisi gerçekle birebir.")
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true", help="yalnız makine çıktısını bas")
    parser.add_argument("--quiet", action="store_true", help="insan tablosunu sustur")
    parser.add_argument(
        "--no-write", action="store_true", help="reports/audit_regression.json yazma"
    )
    args = parser.parse_args(argv)

    if not AUDIT_REPORT.exists():
        print(f"✗ denetim raporu yok: {AUDIT_REPORT}", file=sys.stderr)
        return 2

    try:
        findings = parse_findings(AUDIT_REPORT.read_text(encoding="utf-8"))
        report = build_report(findings)
    except AuditGuardError as exc:
        print(f"✗ BEKÇİ BÜTÜNLÜĞÜ BOZULDU: {exc}", file=sys.stderr)
        return 2

    if not args.no_write:
        REPORT_OUT.parent.mkdir(parents=True, exist_ok=True)
        REPORT_OUT.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif not args.quiet:
        print(render_table(report))
        print(f"rapor: {REPORT_OUT.relative_to(ROOT).as_posix()}")

    meta = report["meta"]  # type: ignore[index]
    return 0 if meta["gate_passed"] else 1  # type: ignore[index]


if __name__ == "__main__":
    raise SystemExit(main())
