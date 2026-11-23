"""Yasal uyarı ve kullanım koşulları — TEK KAYNAK.

Neden var (doğrulama 2026-11-23)
--------------------------------
Depoda KVKK / aydınlatma / açık rıza / kullanım koşulları metni **hiç** yoktu
(kapsamlı grep: 0 hit). Yalnızca bir "18+ REŞİT" beyan kutusu vardı.
`agent_core/capabilities/policy.py` ise açıkça "hedef rızası diye bir kapı
YOKTUR" diyordu. Bu üçü birlikte ürünü 6698 sayılı KVKK açısından
satılamaz/kurumsal kullanılamaz hâle getiriyordu.

Bu modül hukuki danışmanlık DEĞİLDİR. Amacı:

1. Arayüzde ve API'de **aynı** metni göstermek (iki farklı gerçeklik olmasın).
2. Operatörün yasal sorumluluğunu **yazılı** hâle getirmek.
3. `PolicyState.subject_consent` beyanının ne anlama geldiğini tanımlamak.

Metinler kısa tutuldu: bir "sözleşme" değil, bir **uyarı + beyan**.
Kurumsal satış öncesi mutlaka hukuki gözden geçirilmelidir.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "DISCLAIMER_TR",
    "CONSENT_DECLARATION_TR",
    "USAGE_TERMS_TR",
    "public_notice",
]

#: Kısa sorumluluk reddi. Arayüzde kalıcı olarak görünür.
DISCLAIMER_TR = (
    "Pineal Epifiz; yalnızca erişilebilir açık kaynak (OSINT) verilerini "
    "toplamayı ve raporlamayı amaçlayan bir araştırma aracıdır. Ürün; klinik "
    "tanı, psikolojik değerlendirme, hukuki mütalaat ya da istihdam/kredi "
    "kararı verme amacıyla kullanılamaz. Motorların ürettiği skorlar kalibre "
    "edilmiş olasılık DEĞİLDİR; yorum değil, ham kanıt zincirinin özetidir. "
    "Yanlış pozitif ve yanlış negatif sonuçlar oluşabilir."
)

#: Operatörün `subject_consent=True` göndererek neyi kabul ettiği.
CONSENT_DECLARATION_TR = (
    "Bir hedef hakkında kişisel veri işleyen bir analiz başlattığımda, hedef "
    "kişinin 6698 sayılı Kişisel Verilerin Korunması Kanunu'nun 4. ve 6. "
    "maddeleri uyarınca AÇIK RIZASININ alındığını, alınamadığı durumlarda "
    "kanunun 5. maddesindeki işleme koşullarından birinin mevcut olduğunu "
    "beyan ederim. Bu beyanın doğruluğundan ve sonuçlarından sorumluyum. "
    "18 yaşından küçük bir hedefe ilişkin analiz, rıza beyanından bağımsız "
    "olarak her koşulda engellenir."
)

#: Kısa kullanım koşulları. Uyarı bandında özet, API'de tam metin.
USAGE_TERMS_TR: tuple[str, ...] = (
    "Yalnızca hukuka uygun ve meşru amaçla kullanın.",
    "Hedef kişinin açık rızası olmadan kişisel veri işlemeyin.",
    "18 yaş altı hedeflerin analizi her koşulda engellidir.",
    "Ürün çıktısını tek başına karar dayanağı yapmayın; kanıt zincirini doğrulayın.",
    "Üçüncü taraf platformların kullanım koşullarına ve yerel hukuka uyun.",
    "Veri saklama ve silme yükümlülüğü kullanıcıya aittir (KVKK md.7).",
)

#: Uyarı bandında gösterilen kısa özet (tek satır).
NOTICE_HEADLINE_TR = (
    "Araştırma aracıdır — klinik tanı, psikolojik değerlendirme ya da "
    "istihdam/kredi kararı için kullanılamaz. Skorlar kalibre olasılık değildir."
)


def public_notice() -> dict[str, Any]:
    """Arayüzün ve ``GET /api/public/notice`` ucunun ortakpayload'u.

    Aynı sözlük hem backend'de serialize edilir hem testlerde doğrulanır;
    böylece "arayüzde başka, API'de başka metin" ikiliği oluşmaz.
    """
    return {
        "language": "tr",
        "jurisdiction": "TR",
        "headline": NOTICE_HEADLINE_TR,
        "disclaimer": DISCLAIMER_TR,
        "consent_declaration": CONSENT_DECLARATION_TR,
        "usage_terms": list(USAGE_TERMS_TR),
        "minor_protection": "18 yaş altı hedeflerin analizi her koşulda engellidir.",
        "not_legal_advice": (
            "Bu metin hukuki danışmanlık değildir; kurumsal kullanımdan önce "
            "mutlaka hukuki gözden geçirilmelidir."
        ),
    }
