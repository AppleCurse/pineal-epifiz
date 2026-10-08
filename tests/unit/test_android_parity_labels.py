"""Android ↔ Python eşdeğerlik (parity) DÜRÜSTLÜK sözleşmesi.

[AUDIT 2026-10-07 · Madde 4] Denetim maddesi şunu istiyordu:

    "Android tarafında ya çok-ajanlı / kanıt / doğrulayıcı yolu UYGULA,
     ya da tek-geçişli (single-shot) Gemini çıkarımı olduğunu AÇIKÇA ETİKETLE."

Seçilen yol: **açıkça etiketle.** Gerekçe: gerçek eşdeğerlik, Android'e
tam bir ajan yürütücüsü + kanıt doğrulama katmanı taşımak demektir; bu bir
mimari ürün kararıdır ve bir denetim düzeltmesiyle (sessizce, testler
olmadan) yapılamaz. Ölçülen gerçek durum:

    PinealAnalyzerEngine.executeAnalysisPipeline()
        -> TEK Gemini çağrısı (generateContentPro)
        -> bağımsız doğrulayıcı YOK (agent_core/agents/autonomous_verifier)
        -> jüri paneli YOK        (3-jüri sözleşmesi)
        -> entailment kapısı YOK
        -> kanıt-URL denetimi YOK
        -> SHA-256 mühür YOK

Dolayısıyla ekranda "9 ajanlı yürütme hattı", "doğrulanmış bulgular",
"sıfır halüsinasyon" gibi iddialar YANLIŞTIR. Bu dosya o iddiaların
hiçbir yerel ayarda (locale) geri dönmesini engeller.

NOT: Bu test JVM/Gradle gerektirmez — Kotlin kaynağını statik olarak
okur. Böylece Android derlemesi koşmayan ortamlarda (bu CI dâhil) da
çalışır. Gradle koşan ortamlar ayrıca `gradle testDebugUnitTest` ile
gerçek birim testlerini koşturur.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
I18N = REPO_ROOT / "android/app/src/main/java/com/example/pineal/i18n/I18n.kt"
ENGINE = REPO_ROOT / "android/app/src/main/java/com/example/pineal/engine/PinealAnalyzerEngine.kt"


def _strip_kotlin_comments(text: str) -> str:
    """Satır/blok yorumlarını ayıklar.

    Zorunlu: hem bu deponun düzeltme yorumları eski etiketleri ibret olsun
    diye ALINTILIYOR, hem de motor kaynağı Python tarafındaki
    `autonomous_verifier` dosyasına yorum içinde atıf yapıyor. Ham metin
    taranırsa test kendi açıklamasını kusur sayar.

    Yalnızca SATIR BAŞINDA `//` ile başlayan yorumlar ayıklanır; `https://`
    gibi dize içi çift eğik çizgiye DOKUNULMAZ.
    """
    without_blocks = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return "\n".join(
        line for line in without_blocks.splitlines() if not line.lstrip().startswith("//")
    )


def _i18n() -> str:
    return _strip_kotlin_comments(I18N.read_text(encoding="utf-8"))


def _engine() -> str:
    return _strip_kotlin_comments(ENGINE.read_text(encoding="utf-8"))


def _function_source(source: str, name: str) -> str:
    """Kotlin üye fonksiyonunun gövdesini döndürür (girintiyle sınırlar).

    Ayraç (brace) sayımı yerine girinti kullanılır: motorun prompt dizeleri
    JSON ayraçları içerdiği için sayım güvenilmezdir.
    """
    lines = source.splitlines()
    start = next(i for i, line in enumerate(lines) if f"fun {name}(" in line)
    indent = len(lines[start]) - len(lines[start].lstrip())
    end = len(lines)
    for index in range(start + 1, len(lines)):
        line = lines[index]
        if line.strip().startswith("fun ") and (len(line) - len(line.lstrip())) == indent:
            end = index
            break
    body = "\n".join(lines[start:end])
    assert name in body, f"{name} gövdesi çıkarılamadı"
    return body


def _locales() -> dict[str, str]:
    """Kaynak dosyadaki yerel ayar bloklarını (tr/en) ayırır.

    Kotlin ``val tr = StringsDict(...)`` / ``val en = StringsDict(...)``
    bloklarını kaba biçimde böler; amaç iki yerel ayarın İKİSİNİN de
    dürüst olduğunu ayrı ayrı kanıtlamaktır (EN bloğu bir önceki
    denetimde bayat kalmıştı).
    """
    text = _i18n()
    blocks: dict[str, str] = {}
    for name in ("tr", "en"):
        match = re.search(rf"val {name} = StringsDict\(", text)
        assert match, f"{name} yerel ayar bloğu bulunamadı"
        start = match.end()
        # Aynı girintiyle kapanan paranteze kadar al.
        depth = 1
        index = start
        while index < len(text) and depth > 0:
            if text[index] == "(":
                depth += 1
            elif text[index] == ")":
                depth -= 1
            index += 1
        blocks[name] = text[start:index]
    return blocks


# ─────────────────────────────────────────────────────────────────────────
# 1) Yasaklı iddialar
# ─────────────────────────────────────────────────────────────────────────

#: (yerel ayar, yasaklı kalıp, gerekçe) — her biri ölçülmemiş bir iddia.
FORBIDDEN_CLAIMS = [
    (r"9-AGENT", "Android'de 9 ajan yok: tek Gemini çağrısı var"),
    (r"360°", "Android tam kapsamlı backend eşdeğerliği değil; tek-geçişli model çıkarımıdır"),
    (r"EXECUTION PIPELINE", "çok adımlı ajan hattı iddiası (tek geçişli çıkarım)"),
    (r"ZERO HALLUCINATION", "hiçbir LLM için verilemeyecek mutlak iddia"),
    (r"SIFIR HALÜSİNASYON", "hiçbir LLM için verilemeyecek mutlak iddia"),
    (r"MULTIMODAL VISION AI", "analiz hattı görsel/multimodal değil (tek metin çağrısı)"),
    (r"ÇOKLU MODLU GÖRSEL ZEKA", "analiz hattı görsel/multimodal değil (tek metin çağrısı)"),
    (r"Verified Reality", "doğrulama katmanı yok: bağımsız doğrulayıcı uygulanmıyor"),
    (r"Doğrulanmış Gerçeklik", "doğrulama katmanı yok: bağımsız doğrulayıcı uygulanmıyor"),
    (r"Fake Quotes Filtered", "alıntı süzgeci (quote guard) YOK: sayılar modelin kendi beyanı"),
    (r"Sahte Alıntı Elendi", "alıntı süzgeci (quote guard) YOK: sayılar modelin kendi beyanı"),
]


@pytest.mark.parametrize(("pattern", "reason"), FORBIDDEN_CLAIMS)
def test_no_locale_makes_an_unsupported_claim(pattern: str, reason: str):
    """Hiçbir yerel ayarda ölçülmemiş/yanlış iddia kalmamalı.

    [AUDIT] EN bloğu bir önceki denetimde gözden kaçmıştı: TR etiketi
    düzeltilirken EN etiketi "9-AGENT EXECUTION PIPELINE" olarak kaldı.
    Bu yüzden test TÜM yerel ayarları tarar.
    """
    offenders = [
        f"{name}: {line.strip()}"
        for name, block in _locales().items()
        for line in block.splitlines()
        if re.search(pattern, line, flags=re.I)
    ]
    assert not offenders, f"yanlış iddia ({reason}):\n" + "\n".join(offenders)


# ─────────────────────────────────────────────────────────────────────────
# 2) Olumlu yükümlülük: hat AÇIKÇA "tek geçişli" diye etiketlenmeli
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("locale", "required_marker"),
    [
        ("tr", "TEK GEÇİŞLİ"),
        ("en", "SINGLE-SHOT"),
    ],
)
def test_pipeline_is_labelled_as_single_shot(locale: str, required_marker: str):
    """Denetim maddesinin ikinci şıkkı: 'açıkça etiketle'."""
    block = _locales()[locale]
    match = re.search(r"agentChainTitle = \"([^\"]+)\"", block)
    assert match, f"{locale}: agentChainTitle bulunamadı"
    assert required_marker in match.group(1), (
        f"{locale}: ajan hattı etiketi tek-geçişli çıkarımı AÇIKÇA söylemiyor: "
        f"{match.group(1)!r} (beklenen işaret: {required_marker})"
    )


@pytest.mark.parametrize("locale", ["tr", "en"])
def test_confidence_is_labelled_as_unverified_model_claim(locale: str):
    """Güven skoru modelin kendi beyanı: 'sistem güveni' iddiası olamaz."""
    block = _locales()[locale]
    match = re.search(r"overallConfidence = \"([^\"]+)\"", block)
    assert match, f"{locale}: overallConfidence bulunamadı"
    lowered = match.group(1).upper()
    assert "DOĞRULANMADI" in lowered or "UNVERIFIED" in lowered, (
        f"{locale}: güven etiketi doğrulanmamış olduğunu söylemiyor: {match.group(1)!r}"
    )


# ─────────────────────────────────────────────────────────────────────────
# 3) Kod ile etiket TUTARLI olmalı
# ─────────────────────────────────────────────────────────────────────────


def test_engine_really_makes_a_single_llm_call():
    """Etiketin iddiası kodla kanıtlanmalı: tam BİR model çağrısı.

    Bu test aynı zamanda "eşdeğerlik UYGULANDI" gününün kilididir: hat
    gerçekten çok-ajanlı hâle gelirse etiket de değişmeli ve bu test
    güncellenmeli — yani etiket ile kod arasındaki bağ koparılamaz.
    """
    # YALNIZCA analiz hattı: `evolveProfile` ikinci bir (ayrı) çağrıdır.
    source = _function_source(_engine(), "executeAnalysisPipeline")
    calls = re.findall(r"RetrofitClient\.service\.(\w+)\(", source)

    # Analiz hattı içinde tam olarak bir üretici (generate*) çağrısı olmalı.
    generate_calls = [name for name in calls if name.startswith("generate")]
    assert len(generate_calls) == 1, (
        f"analiz hattında {len(generate_calls)} üretici çağrı var: {generate_calls}. "
        "Etiket 'SINGLE-SHOT' diyor; kod bunu doğrulamıyorsa ETİKETİ güncelle."
    )


def test_engine_has_no_verifier_jury_or_seal():
    """Eşdeğerlik yoksa, onu UYGULAYAN bir kod da olmamalı.

    Bilinçli olarak SÖZCÜK değil, GERÇEKLEME aranır: motor, kullanıcıya
    verdiği dürüstlük uyarısında "mühür (SHA-256) YOK" diye yazar; yani
    'SHA-256' sözcüğü kaynakta GEÇER. Aranan şey hashing/doğrulama
    çağrısıdır.
    """
    source = _engine()

    # 1) Gerçekleme izi: özet (digest) hesabı yok.
    for forbidden in ("MessageDigest", "digest(", "sha256(", "sha-256("):
        assert forbidden.lower() not in source.lower(), (
            f"motor kaynağında '{forbidden}' çağrısı var: mühür gerçekten "
            "uygulanmışsa etiketler güncellenmeli"
        )

    # 2) Python tarafındaki doğrulayıcı içe AKTARILMAMIŞ olmalı (yalnızca
    #    yorum içinde atıf yapılabilir).
    imports = [line for line in source.splitlines() if line.strip().startswith("import")]
    assert not [line for line in imports if "verifier" in line.lower()], (
        "motor Python doğrulayıcısını içe aktarıyor: eşdeğerlik iddiası "
        "etiketlerle uyumlu değil"
    )

    # 3) Jüri/entailment gerçeklemesi yok (yalnızca "yok" diyen uyarı olabilir).
    for forbidden in ("juryPanel", "entailmentGate", "verifyClaim("):
        assert forbidden.lower() not in source.lower(), (
            f"'{forbidden}' gerçeklemesi bulundu: etiketleri güncelle"
        )


def test_engine_declares_the_parity_gap_in_its_output():
    """Kullanıcı, KOŞU İÇİNDE de eşdeğerlik boşluğunu görmeli (log satırı)."""
    source = _engine()
    assert "TEK LLM ÇIKARIMI" in source, (
        "analiz sonunda kullanıcıya 'tek LLM çıkarımı, bağımsız doğrulama ve "
        "mühür yok' bilgisi veren log/uyarı bulunamadı"
    )



def test_android_is_explicitly_a_standalone_single_shot_client():
    """Visible product labels must not imply full Python/backend feature parity."""
    locales = _locales()
    for locale, standalone, single_shot in (
        ("tr", "BAĞIMSIZ ANDROID İSTEMCİSİ", "TEK GEÇİŞLİ GEMINI ÇIKARIMI"),
        ("en", "STANDALONE ANDROID CLIENT", "SINGLE-SHOT GEMINI INFERENCE"),
    ):
        block = locales[locale]
        assert standalone in block
        assert single_shot in block

    activity = (REPO_ROOT / "android/app/src/main/java/com/example/pineal/MainActivity.kt").read_text(encoding="utf-8")
    assert 'to "🧠 360° Harita"' not in activity
    assert "doğrulanmamış model profili" in activity.lower()
