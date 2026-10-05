"""FAZ A · A8 — maigret site listesini WhatsMyName/sherlock verisiyle tazeleme.

maigret paketi, paketlenmiş bir site anlık görüntüsüyle gelir ve hiç
güncellenmez. Bu modül, aynı işi yapan iki açık kaynağın (WhatsMyName,
sherlock) verisini **maigret şemasına** birleştirir; üretilen dosya
``PINEAL_MAIGRET_DB`` ile tarayıcıya verilir.

Dürüstlük sözleşmesi (üç kural, tartışmasız):
    1. UYDURMA YOK — kaynakta olmayan alan üretilmez. Ör: sherlock kaydında
       ``username_claimed`` yoksa maigret'in ``usernameClaimed`` alanı
       İCAT EDİLMEZ; alan hiç yazılmaz.
    2. KÜRASYON EZİLMEZ — maigret'in elle kürate edilmiş kaydı asla
       üzerine yazılmaz; yalnız EKSİK alanlar doldurulur.
    3. DESTEKLENMEYEN KİP ATLANIR — ör. sherlock'un ``response_url`` kipi
       maigret şemasında karşılığı olmadığı için yanlış dönüştürülmez;
       kayıt ATLANIR ve sebebi SAYILIR (sessiz kayıp yok).

Modül saf ve deterministiktir: aynı girdi → aynı çıktı (testler buna bağlı).
Ağ erişimi yalnız operatörün açıkça ``--fetch`` demesiyle denenir; kapalı
ortamlarda çekirdek dosyalarla çalışır.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

__all__ = [
    "MergeStats",
    "RefreshReport",
    "load_base_sites",
    "merge_sherlock",
    "merge_wmn",
    "refresh",
    "write_refreshed_db",
    "main",
]

#: maigret şemasının tanıdığı site alanları (bunun dışındaki alan kopyalanmaz:
#: kaynakta olup maigret'te karşılığı olmayan veri yanlış şema ile SIZMAZ).
MAIGRET_SITE_FIELDS = frozenset(
    {
        "url",
        "urlMain",
        "urlProbe",
        "urlSubpath",
        "regexCheck",
        "usernameClaimed",
        "usernameUnclaimed",
        "checkType",
        "absenceStrs",
        "presenseStrs",
        "errors",
        "headers",
        "requestMethod",
        "tags",
        "alexaRank",
        "engine",
        "type",
        "source",
        "protection",
        "disabled",
    }
)

#: sherlock'un maigret'te karşılığı OLMAYAN kipi: yanlış dönüştürülmez, atlanır.
SHERLOCK_UNSUPPORTED_MODES = frozenset({"response_url"})

_NAME_CLEAN_RE = re.compile(r"[\[\]\{\}()]")


class MergeStats(BaseModel):
    """Bir kaynağın birleştirme ölçümü (uydurma yok: sayılanlar gerçek)."""

    source: str
    candidates: int = 0          # kaynakta görülen kayıt sayısı
    added: int = 0               # maigret'te hiç yoktu, eklendi
    filled: int = 0              # maigret'te vardı, yalnız eksik alan doldu
    unchanged: int = 0           # maigret'te vardı, eklenecek hiçbir şey yoktu
    skipped: int = 0             # desteklenmeyen kip / boş veri → atlandı
    skip_reasons: Dict[str, int] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")

    def _skip(self, reason: str) -> None:
        self.skipped += 1
        self.skip_reasons[reason] = self.skip_reasons.get(reason, 0) + 1


class RefreshReport(BaseModel):
    """Tüm tazelemenin dürüst raporu (CLI bunu basar; tarayıcı özetini taşır)."""

    base_source: str = ""        # "bundled:<path>" veya operatör dosyası
    base_shape: str = ""         # "flat" (<=0.6.5) | "nested" (0.6.6+)
    base_sites: int = 0
    final_sites: int = 0
    sherlock: Optional[MergeStats] = None
    wmn: Optional[MergeStats] = None
    missing_sources: List[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# TABAN DB YÜKLEME — maigret'in iki paketlenmiş biçimi de desteklenir:
#   flat   : {"SiteAdı": {...}, ...}                    (maigret <= 0.6.5)
#   nested : {"sites": {...}, "engines": {...}, ...}    (maigret >= 0.6.6)
# ---------------------------------------------------------------------------


def _parse_db_payload(payload: Any) -> Tuple[Dict[str, Dict[str, Any]], str]:
    """JSON gövdesinden site sözlüğünü çıkarır: (sites, shape)."""
    if not isinstance(payload, dict):
        raise ValueError("maigret db kökü dict olmalı")
    if isinstance(payload.get("sites"), dict):
        sites = payload["sites"]
        shape = "nested"
    else:
        sites = payload
        shape = "flat"
    clean: Dict[str, Dict[str, Any]] = {}
    for name, entry in sites.items():
        if not isinstance(entry, dict):
            continue  # bozuk kayıt sessizce şema dışına atılır
        clean[str(name)] = dict(entry)
    return clean, shape


def load_base_sites(path: Optional[str] = None) -> Tuple[Dict[str, Dict[str, Any]], str, str]:
    """Taban maigret DB'sini yükler.

    Dönüş: ``(sites, shape, source)``. ``path=None`` ise kurulu maigret
    paketinin paketlenmiş ``data.json`` dosyası okunur. Dosya yoksa/bozuksa
    istisna fırlatılır — sessizce boş DB ile devam EDİLMEZ.
    """
    if path:
        base_path = Path(path)
        source = f"file:{base_path}"
    else:
        import maigret

        base_path = Path(maigret.__file__).parent / "resources" / "data.json"
        source = f"bundled:{base_path}"
    payload = json.loads(base_path.read_text(encoding="utf-8"))
    sites, shape = _parse_db_payload(payload)
    if not sites:
        raise ValueError(f"maigret db boş: {base_path}")
    return sites, shape, source


def _norm_name(name: str) -> str:
    """Site adı normalizasyonu: 'GitHub' ile 'github' aynı sitedir."""
    return _NAME_CLEAN_RE.sub("", str(name or "").strip().replace(" ", "").lower())


def _fill_missing(target: Dict[str, Any], patch: Dict[str, Any]) -> int:
    """Kural 2: yalnız EKSİK alanları doldurur; mevcut değere DOKUNMAZ.

    Dönüş: doldurulan alan sayısı (0 = kayıt zaten tam).
    """
    filled = 0
    for key, value in patch.items():
        if key not in MAIGRET_SITE_FIELDS:
            continue  # maigret şemasında yok → sızdırılmaz
        if key in target and target[key] not in (None, "", [], {}):
            continue  # elle kürate değer ezilmez
        target[key] = value
        filled += 1
    return filled


def _maigret_url(template: str) -> str:
    """sherlock/WMN yer tutucusu ({account}, {}, {username?}) → {username}."""
    url = re.sub(r"\{[^{}]*\}", "{username}", str(template or "").strip())
    return url


# ---------------------------------------------------------------------------
# SHERLOCK BİRLEŞTİRMESİ
# ---------------------------------------------------------------------------


def merge_sherlock(
    sites: Dict[str, Dict[str, Any]], sherlock_data: Dict[str, Any]
) -> MergeStats:
    """sherlock ``data.json`` kaydını maigret şemasına çevirip birleştirir.

    Alan eşleme (yalnız kaynakta OLAN taşınır — Kural 1):
        url/urlProbe ({} → {username}) · urlMain · regexCheck · headers
        username_claimed → usernameClaimed   (yoksa İCAT EDİLMEZ)
        errorType=status_code → checkType=status_code
        errorType=message     → checkType=message + errorMsg → absenceStrs
        errorType=response_url → DESTEKLENMİYOR → atla+say (Kural 3)
    """
    stats = MergeStats(source="sherlock")
    if not isinstance(sherlock_data, dict):
        return stats
    index = {_norm_name(k): k for k in sites}

    for raw_name, entry in sherlock_data.items():
        if str(raw_name).startswith("$") or str(raw_name).startswith("__"):
            continue  # şema/yorum anahtarları veri değildir
        if not isinstance(entry, dict):
            continue
        stats.candidates += 1

        mode = str(entry.get("errorType") or "").strip()
        if mode in SHERLOCK_UNSUPPORTED_MODES:
            stats._skip("unsupported_mode")
            continue
        url = _maigret_url(entry.get("url") or entry.get("urlProbe") or "")
        if not url.startswith(("http://", "https://")) or "{username}" not in url:
            stats._skip("empty_url")
            continue

        patch: Dict[str, Any] = {"url": url}
        url_main = str(entry.get("urlMain") or "").strip()
        if url_main.startswith(("http://", "https://")):
            patch["urlMain"] = url_main
        url_probe = _maigret_url(entry.get("urlProbe") or "")
        if url_probe.startswith(("http://", "https://")):
            patch["urlProbe"] = url_probe
        regex = entry.get("regexCheck")
        if isinstance(regex, str) and regex.strip():
            patch["regexCheck"] = regex
        headers = entry.get("headers")
        if isinstance(headers, dict) and headers:
            patch["headers"] = dict(headers)
        claimed = entry.get("username_claimed")
        if isinstance(claimed, str) and claimed.strip():
            patch["usernameClaimed"] = claimed.strip()  # kaynakta var → taşınır

        if mode == "status_code":
            patch["checkType"] = "status_code"
        elif mode == "message":
            patch["checkType"] = "message"
            msgs = entry.get("errorMsg")
            if isinstance(msgs, str) and msgs.strip():
                patch["absenceStrs"] = [msgs]
            elif isinstance(msgs, list) and msgs:
                patch["absenceStrs"] = [str(m) for m in msgs if str(m).strip()]
        # errorType yok/boş: checkType İCAT EDİLMEZ (Kural 1).

        name = str(raw_name).strip()
        existing = sites.get(name) or (sites.get(index[_norm_name(name)]) if _norm_name(name) in index else None)
        if existing is not None:
            if _fill_missing(existing, patch):
                stats.filled += 1
            else:
                stats.unchanged += 1
        else:
            sites[name] = patch
            index[_norm_name(name)] = name
            stats.added += 1
    return stats


# ---------------------------------------------------------------------------
# WHATSMYNAME BİRLEŞTİRMESİ
# ---------------------------------------------------------------------------


def merge_wmn(sites: Dict[str, Dict[str, Any]], wmn_data: Dict[str, Any]) -> MergeStats:
    """WhatsMyName ``wmn_data.json`` kaydını maigret şemasına çevirir.

    WMN alanları: ``name`` · ``uri_check`` ({account} yer tutuculu) ·
    ``uri_pretty`` · ``e_code``/``m_code`` (durum kodu kipi) veya
    ``e_string``/``m_string`` (mesaj kipi) · ``known_accounts`` · ``cat``.

    Kural 1: ``known_accounts`` boşsa ``usernameClaimed`` ÜRETİLMEZ.
    Kural 3: ne kod ne mesaj sinyali varsa kontrol kipi kurulamaz → atla+say.
    """
    stats = MergeStats(source="wmn")
    entries: List[Any]
    if isinstance(wmn_data, dict) and isinstance(wmn_data.get("sites"), list):
        entries = wmn_data["sites"]
    elif isinstance(wmn_data, list):
        entries = wmn_data
    else:
        return stats
    index = {_norm_name(k): k for k in sites}

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        stats.candidates += 1
        name = str(entry.get("name") or "").strip()
        if not name:
            stats._skip("no_site_name")
            continue
        url = _maigret_url(entry.get("uri_check") or "")
        if not url.startswith(("http://", "https://")) or "{username}" not in url:
            stats._skip("empty_url")
            continue

        e_string = str(entry.get("e_string") or "").strip()
        m_string = str(entry.get("m_string") or "").strip()
        e_code = entry.get("e_code")
        m_code = entry.get("m_code")

        patch: Dict[str, Any] = {"url": url}
        pretty = str(entry.get("uri_pretty") or "").strip()
        if pretty.startswith(("http://", "https://")):
            patch["urlMain"] = _maigret_url(pretty) or pretty
        if e_string or m_string:
            patch["checkType"] = "message"
            if e_string:
                patch["absenceStrs"] = [e_string]
            if m_string:
                patch["presenseStrs"] = [m_string]
        elif isinstance(e_code, int) and isinstance(m_code, int):
            patch["checkType"] = "status_code"
        else:
            # Kontrol kipi kurulamıyor: yanlış alan icat etmek yerine atla+say.
            stats._skip("unsupported_mode")
            continue

        known = entry.get("known_accounts")
        if isinstance(known, list) and known:
            first = next(
                (a.get("username") for a in known if isinstance(a, dict) and str(a.get("username") or "").strip()),
                None,
            )
            if first:
                patch["usernameClaimed"] = str(first).strip()
        # known_accounts yok/boş → usernameClaimed YOK (Kural 1).

        cat = str(entry.get("cat") or "").strip()
        if cat:
            patch["tags"] = [cat]

        existing = sites.get(name) or (sites.get(index[_norm_name(name)]) if _norm_name(name) in index else None)
        if existing is not None:
            if _fill_missing(existing, patch):
                stats.filled += 1
            else:
                stats.unchanged += 1
        else:
            sites[name] = patch
            index[_norm_name(name)] = name
            stats.added += 1
    return stats


# ---------------------------------------------------------------------------
# TAZELEME + YAZIM + CLI
# ---------------------------------------------------------------------------


def refresh(
    base_path: Optional[str] = None,
    wmn_path: Optional[str] = None,
    sherlock_path: Optional[str] = None,
) -> Tuple[Dict[str, Dict[str, Any]], RefreshReport]:
    """Taban DB'yi yükler, bulunan kaynakları birleştirir; (sites, rapor) döner.

    Verilmeyen kaynak dosyası hata DEĞİLDİR: rapora ``missing_sources``
    olarak yazılır (operatör hangi kaynağın kullanılmadığını görür).
    """
    sites, shape, source = load_base_sites(base_path)
    report = RefreshReport(
        base_source=source, base_shape=shape, base_sites=len(sites), final_sites=len(sites)
    )

    if sherlock_path:
        sherlock_data = json.loads(Path(sherlock_path).read_text(encoding="utf-8"))
        report.sherlock = merge_sherlock(sites, sherlock_data)
    else:
        report.missing_sources.append("sherlock")

    if wmn_path:
        wmn_data = json.loads(Path(wmn_path).read_text(encoding="utf-8"))
        report.wmn = merge_wmn(sites, wmn_data)
    else:
        report.missing_sources.append("wmn")

    report.final_sites = len(sites)
    return sites, report


def write_refreshed_db(
    sites: Dict[str, Dict[str, Any]], shape: str, base_payload: Any = None
) -> Dict[str, Any]:
    """Tazelenmiş site sözlüğünden maigret'in yükleyebileceği JSON gövdesi kurar.

    Taban ``nested`` biçimindeyse (0.6.6+) ``engines``/``tags`` gibi diğer
    bölümler KORUNUR; yalnız ``sites`` tazelenmiş sözlükle değiştirilir.
    """
    if shape == "nested" and isinstance(base_payload, dict):
        payload = dict(base_payload)
        payload["sites"] = sites
        return payload
    return dict(sites)


def _default_output_path() -> Path:
    return Path("memory") / "maigret_db_refreshed.json"


def main(argv: Optional[List[str]] = None) -> int:
    """CLI: ``python -m agent_core.services.maigret_db_refresh ...``"""
    parser = argparse.ArgumentParser(
        prog="maigret_db_refresh",
        description="maigret site DB'sini WhatsMyName/sherlock verisiyle tazeler (A8).",
    )
    parser.add_argument("--base", help="Taban maigret data.json (varsayılan: paketlenmiş DB)")
    parser.add_argument("--wmn", help="WhatsMyName wmn_data.json dosyası")
    parser.add_argument("--sherlock", help="sherlock data.json dosyası")
    parser.add_argument("--out", help="Çıktı dosyası (varsayılan: memory/maigret_db_refreshed.json)")
    args = parser.parse_args(argv)

    if not args.wmn and not args.sherlock:
        print(
            json.dumps(
                {"error": "no_source", "note": "en az bir kaynak gerekir: --wmn ve/veya --sherlock"},
                ensure_ascii=False,
            )
        )
        return 2

    try:
        sites, report = refresh(base_path=args.base, wmn_path=args.wmn, sherlock_path=args.sherlock)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": type(exc).__name__, "detail": str(exc)[:200]}, ensure_ascii=False))
        return 1

    base_payload: Any = None
    if report.base_shape == "nested":
        base_file = args.base
        if base_file:
            base_payload = json.loads(Path(base_file).read_text(encoding="utf-8"))
        else:  # paketlenmiş nested DB'nin kendisi
            import maigret

            base_payload = json.loads(
                (Path(maigret.__file__).parent / "resources" / "data.json").read_text(encoding="utf-8")
            )
    payload = write_refreshed_db(sites, report.base_shape, base_payload)

    out_path = Path(args.out) if args.out else _default_output_path()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp_path.replace(out_path)  # atomik: yarım dosya asla kalmasın

    print(report.model_dump_json(indent=1))
    print(f"YAZILDI: {out_path} ({report.final_sites} site) — kullan: PINEAL_MAIGRET_DB={out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI girişi
    raise SystemExit(main())
