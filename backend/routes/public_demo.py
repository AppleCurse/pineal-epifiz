"""Herkese açık (token'sız) salt-okunur uçlar: 2 örnek analiz raporu + yasal uyarı.

Neden var (doğrulama 2026-11-23)
--------------------------------
Dış inceleme ve bağımsız doğrulama aynı sonucu verdi: site açılır açılmaz
kırmızı ``HTTP 401`` + ``KASA DURUMU BİLİNMİYOR`` görünüyordu, çünkü
``auth_middleware`` **tüm** ``/api/*`` yollarına uygulanıyordu ve hiçbir
herkese açık istisna yoktu. Ziyaretçi ürünün ne yaptığını göremeden
gidiyordu; telemetri 401'i ayrıca kasa göstergesini "bilinmiyor" yapıyordu.

Bu modül iki şey sağlar:

1. ``GET /api/public/demo-reports`` ve ``/api/public/demo-reports/{id}``
   → **2 statik örnek rapor**. Gerçek bir görev çalıştırılmaz, kişi verisi
   taşımaz, her alan "SENTEİTK" olarak etiketlidir.
2. ``GET /api/public/notice`` → ``agent_core/legal/notice.py``'deki
   sorumluluk reddi / kullanım koşulları. Arayüz aynı kaynaktan okur.

Bu uçlar ``backend/api.py`` içindeki ``_PUBLIC_GET_PATHS`` allowlist'ine
eklenir; oraya eklenmedikçe 401 almaya devam ederler (fail-closed).

Tasarım notu: raporlar dosyadan okunmaz, modül sabitidir. Böylece Docker
imajında/worker'da path sorunu çıkmaz ve CI'da deterministik test edilir.
Gerçek rapor üretimi için ``agent_core/services/report_factory.py`` vardır;
bu modül onun yerine geçmez, yalnızca **vitrin** taşır.
"""

from __future__ import annotations

from typing import Any

from fastapi.responses import JSONResponse

from agent_core.legal import public_notice

__all__ = ["DEMO_REPORTS", "PUBLIC_PATHS", "register_public_routes"]


#: Bu modülün sunduğu yollar. `auth_middleware` allowlist'iyle BİREBİR aynı
#: olmalı; iki liste ayrırsa ya gereksiz 401 ya gereksiz açık kapı doğar.
#: Bu yüzden `api.py` bu sabiti içe aktarır (tek kaynak).
PUBLIC_PATHS: tuple[str, ...] = (
    "/api/public/demo-reports",
    "/api/public/demo-reports/",
    "/api/public/notice",
)


def _evidence(engine: str, claim: str, quote: str, status: str = "DOĞRULANDI") -> dict[str, Any]:
    """Tek kanıt satırı — gerçek zincir şemasıyla aynı alan adları."""
    return {
        "agent": engine,
        "evidence_type": "open_source_observation",
        "result": {"claim": claim, "quote": quote, "verification": status},
        "epistemic_type": "direct_observation",
        "scope": {"source": engine, "retention": "kaynak silirse kaybolur"},
        "observed_at": "2026-11-20T09:00:00Z",
        "synthetic": True,
    }


#: İki örnek rapor. İçerik tamamen kurgusal; gerçek kişi/kurum taşımaz.
DEMO_REPORTS: dict[str, dict[str, Any]] = {
    "demo-01-acik-kaynak-tutarlilik": {
        "id": "demo-01-acik-kaynak-tutarlilik",
        "title": "Açık Kaynak Profil Tutarlılık Analizi",
        "subtitle": "Kamu profili iddialarının açık kaynak verisiyle karşılaştırılması",
        "scenario": "Bireysel profil — açık kaynak OSINT",
        "subject_label": "@ornek-kullanici (SENTEİTK)",
        "generated_at": "2026-11-20T09:00:00Z",
        "duration_seconds": 412,
        "engine": "7 sütun / 14 ajan",
        "synthetic": True,
        "notice": (
            "Bu rapor SENTEİTİK bir örnektir. Gerçek bir kişi analiz edilmemiştir; "
            "alanlar ürünün çıktı biçimini göstermek için üretilmiştir."
        ),
        "confidence": {
            "label": "Kapsam: 5/6 motor",
            "value": 83,
            "semantics": "kapsam_orani",
            "caveat": (
                "Bu sayı kalibre edilmiş bir olasılık DEĞİLDİR; kaç motorun "
                "veri üretebildiğini gösterir."
            ),
        },
        "pillars": [
            {"id": "follower", "label": "TAKİPÇİ", "status": "OBSERVED",
             "summary": "Takipçi/takip oranı kamu API'sinden okundu.", "items": 3},
            {"id": "timing", "label": "ZAMAN", "status": "OBSERVED",
             "summary": "Paylaşım saat dağılımı FFT ile ölçüldü.", "items": 2},
            {"id": "depth", "label": "DERİNLİK", "status": "PARTIAL",
             "summary": "Gerçeklik endeksi 0.62 — 2 bulgu alıntıyla doğrulandı.", "items": 2},
            {"id": "visual", "label": "GÖRSEL", "status": "NO_DATA",
             "summary": "Görsel kanıt yok — sensör kapalı.", "items": 0},
            {"id": "shadow", "label": "GÖLGE", "status": "NO_DATA",
             "summary": "Bağlantı ağı verisi yok.", "items": 0},
            {"id": "osint", "label": "OSINT", "status": "OBSERVED",
             "summary": "3 platformda aynı kullanıcı adı görüldü (doğrulanmamış).", "items": 3},
            {"id": "resonance", "label": "REZONANS", "status": "NO_DATA",
             "summary": "Kullanıcı bağlamı verilmediği için hesaplanmadı.", "items": 0},
        ],
        "findings": [
            {
                "id": "F-1",
                "severity": "MEDIUM",
                "title": "Biyografi iddiası görsel zaman çizelgesiyle çelişiyor",
                "evidence": ["E-1", "E-2"],
                "confidence": "destekli",
                "quote": "Biyografide '2019'dan beri İstanbul'da' yazarken, 2021 tarihli "
                          "paylaşımlar farklı bir şehirde çekilmiş.",
            },
            {
                "id": "F-2",
                "severity": "LOW",
                "title": "Paylaşım saatleri tek bir zaman dilimine yoğunlaşıyor",
                "evidence": ["E-3"],
                "confidence": "kısmi",
                "quote": "Gönderilerin %78'i 09:00–11:00 (UTC+3) arasında.",
            },
        ],
        "evidence_chain": [
            _evidence("osint_investigator", "Aynı kullanıcı adı 3 platformda mevcut",
                      "'ornek-kullanici' → 3 eşleşme (doğrulanmamış)", "BİLİNMİYOR"),
            _evidence("timing_forensics", "Paylaşım saatleri tek dilime yoğun",
                      "09:00–11:00 bandı: %78"),
            _evidence("depth_analyst", "Biyografi iddiası çelişkili",
                      "2019'dan beri İstanbul'da ↔ 2021'de farklı şehir"),
        ],
        "limitations": [
            "Görsel ve bağlantı ağı sensörleri kapalıydı; bu sütunlar veri üretmedi.",
            "OSINT eşleşmeleri doğrulanmamıştır; aynı kullanıcı adı farklı kişiye ait olabilir.",
            "Gerçeklik endeksi LLM özetidir; kalibre edilmiş bir ölçüm değildir.",
        ],
    },
    "demo-02-kurumsal-ayak-izi": {
        "id": "demo-02-kurumsal-ayak-izi",
        "title": "Kurumsal Dijital Ayak İzi Envanteri",
        "subtitle": "Bir alan adının açık kaynak varlık ve tutarlılık taraması",
        "scenario": "Kurumsal — marka itibarı / due diligence",
        "subject_label": "ornek-sirket.com.tr (SENTEİTK)",
        "generated_at": "2026-11-20T10:30:00Z",
        "duration_seconds": 268,
        "engine": "7 sütun / 9 ajan",
        "synthetic": True,
        "notice": (
            "Bu rapor SENTEİTİK bir örnektir. Gerçek bir kurum taranmamıştır; "
            "alanlar kurumsal kullanım senaryosunu göstermek için üretilmiştir."
        ),
        "confidence": {
            "label": "Kapsam: 4/6 motor",
            "value": 67,
            "semantics": "kapsam_orani",
            "caveat": "Kalibre edilmiş olasılık değildir; motor kapsamını gösterir.",
        },
        "pillars": [
            {"id": "follower", "label": "TAKİPÇİ", "status": "NO_DATA",
             "summary": "Bireysel profil sütunu — kurumsal hedef için uygulanmaz.", "items": 0},
            {"id": "timing", "label": "ZAMAN", "status": "OBSERVED",
             "summary": "İçerik yayın ritmi aylık bazda ölçüldü.", "items": 2},
            {"id": "depth", "label": "DERİNLİK", "status": "OBSERVED",
             "summary": "Kurum kimlik iddiaları 2 bulguyla çaprazlandı.", "items": 2},
            {"id": "visual", "label": "GÖRSEL", "status": "NO_DATA",
             "summary": "Görsel adli hattı kapalı.", "items": 0},
            {"id": "shadow", "label": "GÖLGE", "status": "OBSERVED",
             "summary": "3 bağlı alan adı tespit edildi.", "items": 3},
            {"id": "osint", "label": "OSINT", "status": "OBSERVED",
             "summary": "Sertifika şeffağı kayıtları + 2 teknoloji imzası.", "items": 2},
            {"id": "resonance", "label": "REZONANS", "status": "NO_DATA",
             "summary": "Karşılaştırma hedefi verilmedi.", "items": 0},
        ],
        "findings": [
            {
                "id": "F-1",
                "severity": "HIGH",
                "title": "Üç bağlı alan adı aynı sertifikayı paylaşıyor",
                "evidence": ["E-1"],
                "confidence": "destekli",
                "quote": "ornek-sirket.com.tr, blog.ornek-sirket.com.tr ve "
                          "uygulama.ornek-sirket.com.tr → tek sertifika parmakizi.",
            },
            {
                "id": "F-2",
                "severity": "LOW",
                "title": "İçerik yayın ritmi düzensiz",
                "evidence": ["E-2"],
                "confidence": "kısmi",
                "quote": "Son 12 ayda 4 yayın; 6 aylık boşluk var.",
            },
        ],
        "evidence_chain": [
            _evidence("shadow_executor", "Bağlı alan adları tek sertifikada toplanıyor",
                      "3 alt alan → aynı sertifika parmak izi"),
            _evidence("osint_investigator", "Sertifika şeffağı kaydı mevcut",
                      "crt.sh: 2026-08-14 tarihli kayıt"),
            _evidence("timing_forensics", "Yayın ritmi düzensiz",
                      "12 ayda 4 yayın, 6 aylık boşluk"),
        ],
        "limitations": [
            "Kurumsal hedefte 'kişisel veri' sütunları bilinçli olarak boş bırakıldı.",
            "Alan adı sahipliği doğrulanmadı; yalnızca teknik bağlantılar ölçüldü.",
            "Teknoloji imzaları pasif taramadadır; aktif sızma testi yapılmadı.",
        ],
    },
}


def register_public_routes(app) -> None:
    """``/api/public/*`` uçlarını kaydeder.

    Bu uçlar ``auth_middleware`` allowlist'indedir; yani token İSTEMEZ.
    Yalnızca GET/HEAD'e izin verilir (bkz. ``api.py`` allowlist kontrolü).
    Hiçbir oda/kasa/durum mutasyonu yapılmaz; dönen payload sabittir.
    """

    @app.get("/api/public/demo-reports")
    async def api_public_demo_reports():
        """İki örnek raporun **özet** listesi (gövde yok, hızlı)."""
        return {
            "synthetic": True,
            "notice": "Bu raporlar SENTEİTİKTİR; gerçek kişi/kurum verisi taşımaz.",
            "count": len(DEMO_REPORTS),
            "reports": [
                {
                    "id": r["id"],
                    "title": r["title"],
                    "subtitle": r["subtitle"],
                    "scenario": r["scenario"],
                    "subject_label": r["subject_label"],
                    "generated_at": r["generated_at"],
                    "duration_seconds": r["duration_seconds"],
                    "engine": r["engine"],
                    "synthetic": r["synthetic"],
                    "confidence": r["confidence"],
                    "finding_count": len(r["findings"]),
                    "evidence_count": len(r["evidence_chain"]),
                }
                for r in DEMO_REPORTS.values()
            ],
        }

    @app.get("/api/public/demo-reports/{report_id}")
    async def api_public_demo_report(report_id: str):
        """Tek örnek raporun tam gövdesi. Bilinmeyen id → 404 (liste sızdırmaz)."""
        report = DEMO_REPORTS.get(report_id)
        if report is None:
            return JSONResponse(
                {"error": {"code": "DEMO_REPORT_NOT_FOUND", "message": "Örnek rapor bulunamadı."}},
                status_code=404,
            )
        return report

    @app.get("/api/public/notice")
    async def api_public_notice():
        """Sorumluluk reddi + kullanım koşulları (arayüzle aynı kaynak)."""
        return public_notice()
