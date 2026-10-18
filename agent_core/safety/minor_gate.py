"""ÇOCUK KIRMIZI ÇİZGİSİ — 18 yaş altı için küresel kilit (Faz 0).

Ürün sahibinin kuralı (2026-10-05), değiştirilemez:

    18 yaşından küçük her birey BİZİM İÇİN ÇOCUKTUR.
    Normal koşulda HİÇBİR ÇOCUK, HİÇBİR SEBEPLE ARAŞTIRILAMAZ.

    TEK İSTİSNA — kayıp / başına bir şey gelmiş olması (Allah korusun):
    Bu durumda çocuğun KENDİSİ, sosyal medyası ve arkadaşları araştırılabilir,
    ama ancak ve ancak şu dört şartın TAMAMI sağlanmışsa:
      1. AİLENİN BİLGİSİ VAR              (aile haberdar edilmiş)
      2. SEBEP NET YAZILMIŞ               (araştırma gerekçesi açıkça girilmiş)
      3. DOĞRULANMIŞ                      (vakanın gerçekliği teyit edilmiş)
      4. KONSORSİYUM ONAYI                (konsey onayı — asgari 2 onay)

Bu dört şarttan BİRİ bile eksikse sistem durur. "Emin olunmadan" hiçbir çocuk
araştırması başlamaz.

Bu kilit:
  - **Küreseldir:** yeteneğin kendi kapıları ne olursa olsun, koşucu (runner)
    politika kapılarından ÖNCE bu kilidi uygular.
  - **İstisnasızdır:** kasa açık olsun olmasın, env bayrağı açık olsun olmasın,
    hiçbir yetenek bu kilidi atlayamaz.
  - **Kayıt altındadır:** onaylanan ve REDDEDİLEN her deneme, hedef kimliği
    saklanmadan (hash) `memory/ledger/minor-cases.jsonl` dosyasına yazılır.

Yetişkin (18+) için: bu modül HİÇBİR ENGEL oluşturmaz. Sistemin tek kırmızı
çizgisi çocuktur; onun dışında karar mercii operatördür.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

import hashlib
import json
import os
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = [
    "MINOR_AGE_LIMIT",
    "MIN_COUNCIL_APPROVALS",
    "MIN_REASON_CHARS",
    "ALLOWED_MINOR_CASE_TYPES",
    "MinorCaseContext",
    "MinorDecision",
    "MinorGate",
    "MinorCaseLedger",
    "coerce_minor_case",
]

#: 18 yaşından küçük her birey çocuktur (ürün kuralı — tartışmaya kapalı).
MINOR_AGE_LIMIT = 18

#: Konsorsiyum/konsey onayı için asgari farklı onaylayıcı sayısı.
MIN_COUNCIL_APPROVALS = 2

#: "Sebep net bir şekilde girilmeden" → asgari gerekçe uzunluğu.
MIN_REASON_CHARS = 25

#: Çocuk vakalarında izin verilen TEK vaka tipi.
ALLOWED_MINOR_CASE_TYPES = frozenset({"missing_or_harm"})


@dataclass(frozen=True)
class MinorCaseContext:
    """Operatörün açtığı vaka bağlamı (çocuk vakalarında zorunludur)."""

    subject_is_minor: bool
    case_type: str = ""                      # "missing_or_harm" → tek izinli tip
    family_notified: bool = False            # 1) ailenin bilgisi var mı
    reason: str = ""                         # 2) araştırma sebebi (net, uzun)
    verified: bool = False                   # 3) vaka doğrulandı mı
    council_approvals: tuple[str, ...] = ()  # 4) konsorsiyum onaylayıcıları
    case_id: str = ""


def _strict_bool(value: Any) -> bool:
    """Yalnız GERÇEK ``True`` sayılır — ``"true"`` · ``1`` · ``"evet"`` DEĞİL.

    DÖRT ŞART için geçerlidir (aile bilgisi, doğrulama): şartlardan biri
    metinle "doğru gibi görünerek" GEÇEMEZ. JSON'dan gelen gerçek boolean tek
    kabul edilen biçimdir.
    """
    return value is True


def _declared_minor(value: Any) -> bool:
    """BEYANIN KENDİSİ — burada fail-closed yön TERSİNE çalışır.

    ``_strict_bool`` beyan alanına uygulansaydı ``{"subject_is_minor": "true"}``
    gönderen bir istemci "çocuk değil" hükmü almış olurdu: yani beyanı
    yorumlayamamak onu YOK SAYMAK hâline gelirdi — kilidi delmenin en sessiz
    biçimi. Bu yüzden yalnız AÇIKÇA ``False`` (+ eşanlamlıları) "yetişkin"
    sayılır; alanın yokluğu ve okunamayan her değer beyan SAYILIR.
    """
    if value is None:
        return True  # alan yok: nesnenin kendisi zaten beyandır
    if value is False:
        return False
    if isinstance(value, str) and value.strip().lower() in {
        "false", "0", "no", "hayir", "hayır",
    }:
        return False
    return True


def _coerce_approvals(value: Any) -> tuple[str, ...]:
    """Onay listesini metin demetine çevirir (tek metin de kabul edilir)."""
    if value is None:
        return ()
    if isinstance(value, str):
        return tuple(part.strip() for part in value.split(",") if part.strip())
    if isinstance(value, (list, tuple, set, frozenset)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return ()


def coerce_minor_case(value: Any) -> "MinorCaseContext | None":
    """Ham beyanı ``MinorCaseContext``e çevirir — BEYAN ASLA SESSİZCE DÜŞMEZ.

    API ve görev katmanları ham JSON taşır; kilidin tek sahibi burasıdır.

    - ``None`` → beyan yok (``None``): yetişkin yolu, karar mercii operatördür.
    - ``MinorCaseContext`` → aynen döner (oda zaten nesne tutuyorsa).
    - ``Mapping`` → bilinen alanlar okunur. **Dört şart** eksik/bozuk ise
      güvenli varsayılana düşer (``False`` / ``""``) ve ``MinorGate`` bunları
      REDDEDER; yani yarım beyan "dur" demektir, "geç" değil. Beyanın kendisi
      (``subject_is_minor``) ise TERS yönde fail-closed'dır: yalnız açıkça
      ``False`` yetişkin sayılır (bkz. ``_declared_minor``).
    - Tanınmayan tip → ``subject_is_minor=True`` + boş vaka: **fail-closed**.
      Operatörün çocuk beyanını yorumlayamadı diye yok saymak, kilidi delmek
      olurdu.
    """
    if value is None:
        return None
    if isinstance(value, MinorCaseContext):
        return value
    if isinstance(value, Mapping):
        return MinorCaseContext(
            subject_is_minor=_declared_minor(value.get("subject_is_minor")),
            case_type=str(value.get("case_type") or ""),
            family_notified=_strict_bool(value.get("family_notified")),
            reason=str(value.get("reason") or ""),
            verified=_strict_bool(value.get("verified")),
            council_approvals=_coerce_approvals(value.get("council_approvals")),
            case_id=str(value.get("case_id") or ""),
        )
    return MinorCaseContext(subject_is_minor=True)


@dataclass(frozen=True)
class MinorDecision:
    allowed: bool
    reason_code: str = ""     # makine-okunur: "council_approval_missing" vb.
    detail: str = ""          # operatöre gösterilecek kısa, net Türkçe mesaj

    @classmethod
    def allow(cls, code: str = "approved", detail: str = "") -> "MinorDecision":
        return cls(allowed=True, reason_code=code, detail=detail)

    @classmethod
    def deny(cls, code: str, detail: str) -> "MinorDecision":
        return cls(allowed=False, reason_code=code, detail=detail)


class MinorGate:
    """Çocuk kilidini değerlendirir (durumsuz, deterministik, yan etkisiz)."""

    def evaluate(self, case: MinorCaseContext | None) -> MinorDecision:
        if case is None or not case.subject_is_minor:
            return MinorDecision.allow("not_minor")

        if case.case_type not in ALLOWED_MINOR_CASE_TYPES:
            return MinorDecision.deny(
                "case_type_not_allowed",
                "Çocuk vakası yalnızca KAYIP / YARALANMA (missing_or_harm) "
                "sebebiyle açılabilir. Bu vaka tipi izinli değil.",
            )
        if not case.family_notified:
            return MinorDecision.deny(
                "family_not_notified",
                "Ailenin bilgisi olmadan çocuk araştırması açılamaz.",
            )
        if len((case.reason or "").strip()) < MIN_REASON_CHARS:
            return MinorDecision.deny(
                "reason_missing",
                f"Araştırma sebebi net yazılmadan çocuk vakası açılamaz "
                f"(en az {MIN_REASON_CHARS} karakter).",
            )
        if not case.verified:
            return MinorDecision.deny(
                "not_verified",
                "Vaka doğrulanmadan (emin olunmadan) çocuk araştırması başlayamaz.",
            )
        unique_approvals = {a.strip() for a in case.council_approvals if str(a).strip()}
        if len(unique_approvals) < MIN_COUNCIL_APPROVALS:
            return MinorDecision.deny(
                "council_approval_missing",
                f"Konsorsiyum onayı olmadan çocuk araştırması açılamaz "
                f"(en az {MIN_COUNCIL_APPROVALS} farklı onay gerekir; "
                f"şu an {len(unique_approvals)}).",
            )
        return MinorDecision.allow(
            "approved",
            "Kayıp/yaralanma vakası: 4 şart tamam — aile bilgili, sebep net, "
            "doğrulandı, konsorsiyum onayladı.",
        )


class MinorCaseLedger:
    """Çocuk vakası kararlarının kalıcı kaydı (hedef kimliği YAZILMAZ).

    Kayıt, operatörü korumak ve denetimi mümkün kılmak içindir: kim, ne zaman,
    hangi gerekçeyle, hangi onaylarla açtı — veya neden reddedildi.
    Hedefin kimliği dosyaya **hash** olarak girer; ham kimlik saklanmaz.
    """

    DEFAULT_PATH = Path("memory") / "ledger" / "minor-cases.jsonl"

    def __init__(self, path: str | Path | None = None) -> None:
        env_path = os.getenv("PINEAL_MINOR_LEDGER_PATH", "").strip()
        self.path = Path(path or env_path or self.DEFAULT_PATH)

    @staticmethod
    def _subject_ref(subject: str) -> str:
        if not subject:
            return ""
        return "sha256:" + hashlib.sha256(subject.strip().lower().encode("utf-8")).hexdigest()[:32]

    def record(
        self,
        case: MinorCaseContext | None,
        decision: MinorDecision,
        *,
        capability_id: str = "",
        subject: str = "",
    ) -> dict[str, Any]:
        """Kararı JSONL olarak ekler; yazma hatası koşuyu DURDURMAZ (best-effort)."""
        entry = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "capability_id": capability_id,
            "subject_ref": self._subject_ref(subject),
            "allowed": decision.allowed,
            "reason_code": decision.reason_code,
            "case_id": getattr(case, "case_id", "") or "",
            "case_type": getattr(case, "case_type", "") or "",
            "family_notified": bool(getattr(case, "family_notified", False)),
            "verified": bool(getattr(case, "verified", False)),
            "approvals": sorted({str(a) for a in getattr(case, "council_approvals", ()) or ()}),
            "reason_len": len((getattr(case, "reason", "") or "").strip()),
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError as exc:
            # Kayıt yazılamadı diye kilit gevşetilmez; ama koşu da patlamaz.
            logger.warning(
                "[record] beklenmeyen hata (OSError) yutulmadı — iz bırakıldı: %s", exc, exc_info=True
            )
        return entry
