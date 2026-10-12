"""`backend/api.py` tek-modül TAVANI (ratchet).

[AUDIT 2026-10-07 · P2] Denetim, `backend/api.py`'nin 6.034 satırlık tek bir
modül olduğunu tespit etti. 6.000 satırlık bir dosyada kusur gözden kaçar
(nitekim bu denetimde de kaçmıştı: gövde tavanı middleware'i tüm istisnaları
yutuyordu) ve her değişiklik aynı dosyaya bindiği için gözden geçirme zorlaşır.

Tam bir bölme (decomposition) tek seferde, testler yeşil kalarak yapılamaz;
bu yüzden iki mekanizma birlikte uygulanır:

1. **Tavan (ratchet):** dosya KÜÇÜLEBİLİR ama tavanı AŞAMAZ. Yeni uç nokta
   eklemek yerine modül çıkarmaya zorlar. Tavanı yükseltmek, gerekçeyi
   `docs/reports/API_MONOLITH_SPLIT_PLAN.md` içine yazmayı gerektirir;
   yani şişkinlik ancak BİLİNÇLİ bir kararla büyüyebilir.
2. **Ölçülebilir ilerleme:** bu test aynı zamanda "en az bir katman
   ayrıştırıldı" gerçeğini de kilitler (bkz. test_api_reexports_split_module).

Bölme planı (uç nokta envanteri ve sıra): `docs/reports/API_MONOLITH_SPLIT_PLAN.md`.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
API = REPO_ROOT / "backend/api.py"
BODY_LIMIT_MODULE = REPO_ROOT / "backend/middleware/body_size_limit.py"

#: Denetim öncesi ÖLÇÜLEN değer: 6.034 satır.
#: İlk bölme (gövde tavanı middleware'i taşındı) sonrası: 5.937 satır.
MEASURED_AT_AUDIT = 6034
MEASURED_AFTER_FIRST_SPLIT = 5937

#: Tavan. Yeni uç nokta eklemek yerine MODÜL ÇIKAR. Tavana dayanınca
#: `docs/reports/API_MONOLITH_SPLIT_PLAN.md` sırasındaki bir sonraki
#: düşük-bağımlılıklı alanı taşı ve bu sayıyı DÜŞÜR.
MAX_LINES = 6000


def _line_count() -> int:
    return len(API.read_text(encoding="utf-8").splitlines())


def test_api_module_is_within_the_size_ceiling():
    """api.py tavanı aşamaz — büyümek istiyorsan BÖL."""
    current = _line_count()
    assert current <= MAX_LINES, (
        f"backend/api.py {current} satır (tavan {MAX_LINES}). "
        "Yeni uç nokta eklemek yerine bir modül çıkar: "
        "docs/reports/API_MONOLITH_SPLIT_PLAN.md (bölüm 4: uygulama sırası). "
        "Tavanı yükseltmek istiyorsan gerekçeyi o belgeye yaz."
    )


def test_monolith_shrank_relative_to_the_audit_baseline():
    """Somut ilerleme kanıtı: denetim ölçümünün ALTINA inmiş olmalıyız."""
    current = _line_count()
    assert current < MEASURED_AT_AUDIT, (
        f"backend/api.py denetim ölçümünden ({MEASURED_AT_AUDIT} satır) küçülmedi: "
        f"{current} satır"
    )


def test_split_module_exists_and_is_importable():
    """İlk ayrıştırılan katman yerinde ve kendi başına içe aktarılabilir."""
    assert BODY_LIMIT_MODULE.is_file(), (
        "ayrıştırılan gövde-tavanı modülü bulunamadı: "
        "backend/middleware/body_size_limit.py"
    )
    from backend.middleware.body_size_limit import (
        BodySizeLimitExceeded,
        BodySizeLimitMiddleware,
    )

    assert issubclass(BodySizeLimitExceeded, Exception)
    assert hasattr(BodySizeLimitMiddleware, "_send_413")


def test_api_reexports_split_module_symbols():
    """Geriye dönük uyumluluk: mevcut içe aktarımlar BOZULMAMALI.

    `from backend.api import BodySizeLimitMiddleware` yazan her yer
    (testler dâhil) değişiklik gerektirmeden çalışmaya devam etmeli.
    """
    import backend.api as api

    assert hasattr(api, "BodySizeLimitMiddleware"), (
        "backend.api gövde-tavanı middleware'ini yeniden ihraç etmiyor: "
        "dış sözleşme bozulmuş"
    )
    assert hasattr(api, "BodySizeLimitExceeded")

    from backend.middleware.body_size_limit import (
        BodySizeLimitMiddleware as Canonical,
    )

    assert api.BodySizeLimitMiddleware is Canonical, (
        "backend.api.BodySizeLimitMiddleware, taşınan sınıfın AYNISI değil"
    )


def test_api_does_not_redefine_the_middleware():
    """Kopya bırakılmamalı: sınıf gövdesi api.py içinde yeniden yazılmış olamaz."""
    import ast

    tree = ast.parse(API.read_text(encoding="utf-8"))
    redefinitions = [
        node.name
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "BodySizeLimitMiddleware"
    ]
    assert not redefinitions, (
        "gövde-tavanı middleware'i hem taşınmış hem api.py içinde yeniden "
        "tanımlanmış: iki kopya birbirinden sapar"
    )


def test_size_ceiling_is_documented():
    """Tavan, plan belgesinde gerekçesiyle birlikte yazılı olmalı."""
    plan = REPO_ROOT / "docs/reports/API_MONOLITH_SPLIT_PLAN.md"
    assert plan.is_file(), "bölme planı belgesi yok"
    text = plan.read_text(encoding="utf-8")
    assert "Tavan" in text or "tavan" in text
    assert "uç nokta" in text.lower()
