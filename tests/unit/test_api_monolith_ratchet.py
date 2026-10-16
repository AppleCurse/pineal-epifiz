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

[API-BÖLME 2 · 2026-10-14] İkinci adım: `/api/language/*` üç ucu
`backend/routes/language.py` modülüne taşındı ve tavan DÜŞÜRÜLDÜ. Gerekçe:
`/api/language` bloğuna modül docstring'i yazılırken dosyanın tavanın TAM
ÜSTÜNDE (6.000 satır) durduğu görüldü — yani envanter/açıklama işi bile
gerçekten `api.py` içine satır ekleyemiyor. Kural işledi: satır eklemek yerine
düşük-bağımlılıklı modül çıkarıldı (§4/1. adım) ve uç sözleşmeleri değişmedi.

[API-BÖLME 3 · 2026-10-16] Üçüncü adım: P0 dürüstlük düzeltmeleri
(`/api/telemetry` yetenek tablosu + web dosyası kural kuralları) iki yeni
modül çıkardı — `backend/routes/telemetry.py` ve
`backend/services/web_dossier.py` — ve tavan 5.916 → 5.907 DÜŞÜRÜLDÜ.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
API = REPO_ROOT / "backend/api.py"
BODY_LIMIT_MODULE = REPO_ROOT / "backend/middleware/body_size_limit.py"
LANGUAGE_MODULE = REPO_ROOT / "backend/routes/language.py"
WEB_RESEARCH_MODULE = REPO_ROOT / "backend/services/web_research.py"

#: Denetim öncesi ÖLÇÜLEN değer: 6.034 satır.
#: İlk bölme (gövde tavanı middleware'i taşındı) sonrası: 5.937 satır.
#: İkinci bölme (`/api/language/*` → `backend/routes/language.py`) sonrası:
#: modül docstring'i dâhil 5.916 satır (ölçüldü 2026-10-14).
#: Üçüncü bölme (2026-10-16, API-BÖLME 3): P0 düzeltmeleri iki yeni modül
#: çıkardı — `backend/routes/telemetry.py` (`/api/telemetry`) ve
#: `backend/services/web_dossier.py` (web dosyası kuralları) — 5.907 satır.
MEASURED_AT_AUDIT = 6034
MEASURED_AFTER_FIRST_SPLIT = 5937
MEASURED_AFTER_SECOND_SPLIT = 5916
MEASURED_AFTER_THIRD_SPLIT = 5908
#: Dördüncü bölme (2026-10-16, API-BÖLME 4): public-web araştırma gövdesi
#: `backend/services/web_research.py` modülüne taşındı → 5.805 satır.
MEASURED_AFTER_FOURTH_SPLIT = 5805

#: Tavan. Yeni uç nokta eklemek yerine MODÜL ÇIKAR. Tavana dayanınca
#: `docs/reports/API_MONOLITH_SPLIT_PLAN.md` sırasındaki bir sonraki
#: düşük-bağımlılıklı alanı taşı ve bu sayıyı DÜŞÜR.
#: Üçüncü bölmeden sonra ölçülen değere indirildi (ratchet: geri çıkış yok).
#: [API-BÖLME 4] Dördüncü bölmeden sonra 5.805'e indirildi.
MAX_LINES = 5805


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


def test_language_split_module_exists_and_is_importable():
    """İkinci ayrıştırılan katman yerinde ve ``backend.api``'siz kullanılabilir."""
    assert LANGUAGE_MODULE.is_file(), (
        "ayrıştırılan dil hattı modülü bulunamadı: backend/routes/language.py"
    )
    from backend.routes.language import (
        LanguageDetectPayload,
        LanguageTranslatePayload,
        register_language_routes,
    )

    assert callable(register_language_routes)
    assert LanguageDetectPayload(text="merhaba").text == "merhaba"
    assert LanguageTranslatePayload(text="hi", target="tr").target == "tr"


def test_api_reexports_language_split_symbols():
    """Geriye dönük uyumluluk: `from backend.api import LanguageDetectPayload` çalışır."""
    import backend.api as api
    from backend.routes.language import LanguageDetectPayload as Canonical

    assert api.LanguageDetectPayload is Canonical
    assert api.LanguageTranslatePayload is not None
    assert api.register_language_routes is not None


def test_language_routes_are_registered_on_the_app():
    """Taşıma sırasında uç sözleşmesi bozulmadı: üç yol da app'te KAYITLI."""
    import backend.api as api

    paths = {getattr(route, "path", None) for route in api.app.routes}
    for path in ("/api/language/status", "/api/language/detect", "/api/language/translate"):
        assert path in paths, f"{path} kayıtlı değil — taşıma uç noktayı düşürdü"


def test_api_does_not_redefine_language_models():
    """Kopya bırakılmamalı: payload modelleri api.py içinde yeniden tanımlanamaz."""
    import ast

    tree = ast.parse(API.read_text(encoding="utf-8"))
    redefinitions = [
        node.name
        for node in tree.body
        if isinstance(node, ast.ClassDef)
        and node.name in {"LanguageDetectPayload", "LanguageTranslatePayload"}
    ]
    assert not redefinitions, (
        "dil hattı payload modelleri hem taşınmış hem api.py içinde yeniden "
        "tanımlanmış: iki kopya birbirinden sapar"
    )


def test_web_research_split_module_exists_and_is_importable():
    """[API-BÖLME 4] Public-web araştırma gövdesi ayrı modülde yaşar."""
    assert WEB_RESEARCH_MODULE.is_file(), (
        "ayrıştırılan public-web araştırma modülü bulunamadı: "
        "backend/services/web_research.py"
    )
    from backend.services.web_research import (
        extract_handle_from_url,
        run_public_web_research,
    )

    assert callable(extract_handle_from_url)
    assert callable(run_public_web_research)


def test_api_reexports_web_research_split_symbols():
    """[API-BÖLME 4] Geriye dönük uyumluluk: `from backend.api import ...` çalışır."""
    import backend.api as api
    from backend.services.web_research import (
        extract_handle_from_url as CanonicalExtract,
        run_public_web_research as CanonicalRun,
    )

    assert api._extract_handle_from_url is CanonicalExtract
    assert api._run_public_web_research is CanonicalRun


def test_api_does_not_redefine_web_research_body():
    """[API-BÖLME 4] Kopya bırakılmamalı: gövde api.py içinde yeniden yazılamaz."""
    import ast

    tree = ast.parse(API.read_text(encoding="utf-8"))
    definitions = [
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name in {"_run_public_web_research", "_extract_handle_from_url"}
    ]
    assert not definitions, (
        "public-web araştırma gövdesi hem taşınmış hem api.py içinde yeniden "
        "tanımlanmış: iki kopya birbirinden sapar"
    )


def test_api_shrank_after_fourth_split():
    """[API-BÖLME 4] Ölçülebilir ilerleme: tavan 5.805'e indi."""
    current = _line_count()
    assert current <= MEASURED_AFTER_FOURTH_SPLIT, (
        f"backend/api.py {current} satır — dördüncü bölme tavanı "
        f"{MEASURED_AFTER_FOURTH_SPLIT}"
    )


def test_size_ceiling_is_documented():
    """Tavan, plan belgesinde gerekçesiyle birlikte yazılı olmalı."""
    plan = REPO_ROOT / "docs/reports/API_MONOLITH_SPLIT_PLAN.md"
    assert plan.is_file(), "bölme planı belgesi yok"
    text = plan.read_text(encoding="utf-8")
    assert "Tavan" in text or "tavan" in text
    assert "uç nokta" in text.lower()
