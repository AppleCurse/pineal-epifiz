"""E7 · `asyncio.gather` SÖZLEŞMESİ — tek hata tüm turu düşürmez.

Planın E7 maddesi "8 korumasız `gather` noktası" diyordu; bu **grep sayımıydı**.
Bu dosya, sayımı anlamsal denetime çevirir ve kuralı makine bekçisine bağlar:

    Her `asyncio.gather(...)` çağrısı ya `return_exceptions=True` ile koşar
    ya da gerekçeli bir muafiyet taşır: `[E7-muaf]` yorumu, 3 satır içinde
    ve en az 30 karakterlik gerekçeyle.

Anlamsal denetimin sonucu (2026-10-07): 11 çağrının **3'ü** zaten
`return_exceptions=True` ile koşuyordu; **7'si** iç coroutine'i hatayı yakaladığı
için korumalıydı (düşen parça dürüst kayda dönüşüyor); **1'i** BİLİNÇLİ
all-or-nothing (`pillar_orchestrator`: 7-sütun politikası hatayı görmek
zorunda). Gerçekten korumasız kalan **1** nokta vardı
(`socid_enricher.enrich_urls`) — düzeltildi: beklenmedik istisna artık tüm
partiyi değil, yalnız o hedefin kaydını düşürür.

Muafiyet bir kaçış yolu DEĞİL: gerekçe yazmak zorunludur ve muafiyet listesi
(11 çağrı / 12 sayım) sabitlenir — yeni bir `gather` eklenip sessizce korumasız
bırakılamaz.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCAN_DIRS = ("agent_core", "backend")

#: Çağrı metnini çıkarırken dengeli parantez sayımı için üst sınır.
MAX_CALL_CHARS = 2_000

#: Bilinçli olarak korumasız bırakılan noktaların gerekçeleri (dosya → asgari
#: gerekçe uzunluğu denetimi ayrıca yapılır). Liste SABİTTİR: yeni bir muafiyet
#: eklemek bilinçli bir karar olmalı, sessiz bir kayma değil.
# NOT: `agent_core/capabilities/adapters_sensors.py` bu listede DEĞİL —
# oradaki `gather` twscrape'in KENDİ fonksiyonudur (asyncio değil) ve zaten
# try/except ile dürüst CapabilityResult'a bağlanmıştır. Tarama yalnız
# `asyncio.gather` çağrılarını görür; bu ayrım testin kendisiyle kanıtlandı.
EXPECTED_EXEMPT_FILES = {
    "agent_core/agents/human_behavior.py",
    "agent_core/engines/pillar_orchestrator.py",
    "agent_core/services/holehe_scanner.py",
    "agent_core/services/local_jury.py",
    "agent_core/services/routed_chat.py",
    "agent_core/services/vision_analyzer.py",
    "agent_core/task_executor.py",
}

MARKER = "[E7-muaf]"
MIN_RATIONALE_CHARS = 30


def _scan_files():
    for base in SCAN_DIRS:
        for path in sorted((ROOT / base).rglob("*.py")):
            yield path.relative_to(ROOT)


def _call_text(source: str, start: int) -> str:
    """`asyncio.gather(` çağrısının metnini dengeli parantezle çıkarır."""
    depth = 0
    for idx in range(start, min(len(source), start + MAX_CALL_CHARS)):
        char = source[idx]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return source[start : idx + 1]
    return source[start : start + MAX_CALL_CHARS]


def _gather_sites():
    """(dosya, satır_no, çağrı_metni, önceki_3_satır) demetleri."""
    sites = []
    for rel in _scan_files():
        source = (ROOT / rel).read_text(encoding="utf-8")
        for match in re.finditer(r"asyncio\.gather\s*\(", source):
            line_no = source[: match.start()].count("\n") + 1
            lines = source.splitlines()
            before = "\n".join(lines[max(0, line_no - 4) : line_no - 1])
            sites.append((str(rel), line_no, _call_text(source, match.start()), before))
    return sites


# ─────────────────────────────────────────────────────────────────────────────
# 1) YAPISAL BEKÇİ
# ─────────────────────────────────────────────────────────────────────────────


def test_scan_finds_the_gather_sites():
    """Denetim boş bir küme üzerinde koşup "yeşil" olmasın."""
    sites = _gather_sites()
    assert len(sites) >= 11, [(f, n) for f, n, _, _ in sites]


def test_every_gather_is_protected_or_explicitly_exempt():
    """Her `gather` ya `return_exceptions=True` ya gerekçeli `[E7-muaf]` taşır."""
    unprotected = []
    for rel, line_no, call, before in _gather_sites():
        if "return_exceptions=True" in call:
            continue
        if MARKER in before:
            continue
        unprotected.append(f"{rel}:{line_no}")
    assert not unprotected, (
        "Korumasız gather noktaları: "
        f"{unprotected} — `return_exceptions=True` ekleyin ya da iç coroutine'in "
        f"hatayı yakaladığını `{MARKER}` gerekçesiyle yazın."
    )


def test_exemptions_have_a_real_rationale():
    """Muafiyet gerekçesi cılız olamaz: `[E7-muaf]` + ≥30 karakter açıklama."""
    weak = []
    for rel, line_no, call, before in _gather_sites():
        if "return_exceptions=True" in call or MARKER not in before:
            continue
        # İşaretten sonraki satır(lar) gerekçeyi taşır (aynı yorum bloğu).
        rationale = before.split(MARKER, 1)[1].strip()
        if len(rationale) < MIN_RATIONALE_CHARS:
            weak.append(f"{rel}:{line_no} ({len(rationale)} karakter)")
    assert not weak, f"gerekçesi cılız muafiyetler: {weak}"


def test_exempt_file_set_is_the_declared_one():
    """Muafiyet kümesi SABİT: yeni bir muafiyet sessizce eklenemez."""
    exempt_files = {
        rel
        for rel, _, call, before in _gather_sites()
        if "return_exceptions=True" not in call and MARKER in before
    }
    assert exempt_files == EXPECTED_EXEMPT_FILES, (
        "Muafiyet kümesi değişti.\n"
        f"  Yeni eklenenler : {sorted(exempt_files - EXPECTED_EXEMPT_FILES)}\n"
        f"  Artık olmayanlar: {sorted(EXPECTED_EXEMPT_FILES - exempt_files)}\n"
        "Bu bilinçli bir kararsa EXPECTED_EXEMPT_FILES'i ve gerekçeyi güncelleyin."
    )


def test_protected_sites_use_return_exceptions():
    """`return_exceptions=True` ile koşan noktalar gerçekten var (bekçi canlı)."""
    protected = [
        (rel, line_no)
        for rel, line_no, call, _ in _gather_sites()
        if "return_exceptions=True" in call
    ]
    protected_files = {rel for rel, _ in protected}
    assert "agent_core/services/socid_enricher.py" in protected_files, (
        "E7 düzeltmesi kaybolmuş: socid_enricher yine korumasız"
    )
    assert len(protected) >= 4, protected


# ─────────────────────────────────────────────────────────────────────────────
# 2) DÜZELTİLEN NOKTA — socid_enricher kısmi sonuç koruması
# ─────────────────────────────────────────────────────────────────────────────


async def test_socid_enrich_survives_an_unexpected_error(monkeypatch):
    """Tek bozuk URL partiyi düşürmez: diğer kayıtlar yine döner.

    Eskiden `asyncio.gather` korumasızdı: beklenmedik bir istisna (ör.
    socid_extractor sürüm farkı) TÜM hedeflerin kaydını kaybettiriyordu.
    """
    from agent_core.services import socid_enricher

    async def _fake_extract(url, client=None):
        if "bozuk" in url:
            raise RuntimeError("socid_extractor_surumu_farkli")
        return socid_enricher.SocidRecord(
            source_url=url, available=True, fields={"email": "a@b.com"}
        )

    monkeypatch.setattr(socid_enricher, "extract_profile", _fake_extract)
    out = await socid_enricher.enrich_urls(
        ["https://a.test/bozuk", "https://a.test/saglam"], limit=2
    )
    assert [r.source_url for r in out] == ["https://a.test/saglam"], out
    assert out[0].available is True


async def test_socid_enrich_marks_unexpected_errors_as_scan_error(monkeypatch, caplog):
    """Düşen hedef SESSİZ kalmaz: uyarı logu + `scan_error` kaydı."""
    import logging

    from agent_core.services import socid_enricher

    async def _fake_extract(url, client=None):
        raise RuntimeError("patladi")

    monkeypatch.setattr(socid_enricher, "extract_profile", _fake_extract)
    with caplog.at_level(logging.WARNING):
        out = await socid_enricher.enrich_urls(["https://a.test/x"], limit=1)
    assert out == []  # sözleşme: yalnız `available=True` kayıtlar döner
    assert any("beklenmedik hata" in rec.message for rec in caplog.records), (
        "düşen hedef sessizce yutuldu"
    )


async def test_socid_enrich_contract_unchanged_for_normal_records(monkeypatch):
    """Sözleşme korunur: yalnız `available=True` kayıtlar döner."""
    from agent_core.services import socid_enricher

    async def _fake_extract(url, client=None):
        if "kapali" in url:
            return socid_enricher.SocidRecord(source_url=url, available=False, reason="no_record")
        return socid_enricher.SocidRecord(source_url=url, available=True, fields={"x": 1})

    monkeypatch.setattr(socid_enricher, "extract_profile", _fake_extract)
    out = await socid_enricher.enrich_urls(
        ["https://a.test/kapali", "https://a.test/acik"], limit=2
    )
    assert [r.source_url for r in out] == ["https://a.test/acik"]
