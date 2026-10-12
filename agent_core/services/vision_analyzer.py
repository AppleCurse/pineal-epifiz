import logging
import base64
import hashlib
import asyncio
import httpx
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, ConfigDict
from agent_core.services.llm_gateway import LLMGateway

logger = logging.getLogger(__name__)

# [013] fix: human_behavior.MAX_IMAGE_BYTES ile aynı sınır; doğrulamalı indirme
# bu limiti aşan gövdeyi reddeder.
MAX_IMAGE_BYTES = 10 * 1024 * 1024


def _sniff_image_mime(data: bytes) -> Optional[str]:
    """Magic-byte imzasından gerçek MIME türü (HTTP başlığı yalan söyleyebilir)."""
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith(b"BM"):
        return "image/bmp"
    return None


class VisualEvidence(BaseModel):
    """Görsellerden çıkarılan somut nesne, mekan ve estetik kanıtlar."""
    detected_objects: List[str] = []         # Kitaplar, fotoğraf makinesi, plak, bitkiler vb.
    environment_and_places: List[str] = []   # Loş oda, atölye, sahil, sergi salonu vb.
    aesthetic_style: str = ""                # Analog gren, monokrom, minimal, karanlık/loş vb.
    activity_signals: List[str] = []         # Gece çalışması, yalnız yürüyüş, müzik kaydı vb.
    visual_evidence_summary: str = ""        # 2-3 cümlelik somut görsel özet
    # [011] fix: fail-closed defaults. Model doğrudan kurulursa (hiç analiz
    # yapılmadan) 'tam güvenilir' sayılmaz; confidence/data_confidence yalnızca
    # gerçek üretim yolunda yerel olarak türetilir ([015]).
    confidence: float = 0.0
    data_confidence: bool = False
    fallback_reason: str = "not_analyzed"
    # [014] fix: her görsel için indirme provenance'ı (URL başarı/durum/sha/mime).
    image_provenance: List[Dict[str, Any]] = []

    model_config = ConfigDict(extra="allow")


class VisionAnalyzer:
    """
    Instagram ve sosyal medya görsellerini çoklu modlu (Multimodal Vision)
    yapay zeka ile inceleyip somut nesne ve mekan kanıtları çıkaran servis.
    """

    def __init__(self, llm_gateway: Optional[LLMGateway] = None):
        self.llm_gateway = llm_gateway or LLMGateway()

    async def _download_image_record(
        self, image_url: str, client: Optional[httpx.AsyncClient] = None
    ) -> Dict[str, Any]:
        """[013]/[014] fix: doğrulamalı indirme + kayıt bazlı provenance.

        Zincir: URL geçerli -> SSRF güvenli -> HTTP 200 -> Content-Type image/*
        -> boyut <= MAX_IMAGE_BYTES -> magic bytes gerçek imza -> base64.
        Her red sebebi kayda geçer; başarısızlık sessizce yutulmaz.
        """
        record: Dict[str, Any] = {
            "source_url": image_url,
            "status": "failed",
            "reason": "",
            "sha256": None,
            "mime": None,
            "bytes": 0,
        }
        if not image_url or not image_url.startswith("http"):
            record["reason"] = "invalid_url"
            return record

        from agent_core.utils.security import UnsafeURLError, safe_get

        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            if client:
                resp = await safe_get(client, image_url, headers=headers)
            else:
                async with httpx.AsyncClient(timeout=15.0, follow_redirects=False) as new_client:
                    resp = await safe_get(new_client, image_url, headers=headers)

            if resp.status_code != 200:
                record["reason"] = f"http_{resp.status_code}"
                return record

            content_type = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
            if content_type and not content_type.startswith("image/"):
                # Örn. text/html: login duvarı/404 sayfası base64'e çevrilmez.
                record["reason"] = f"content_type_{content_type}"
                return record

            if len(resp.content) > MAX_IMAGE_BYTES:
                record["reason"] = "too_large"
                return record

            mime = _sniff_image_mime(resp.content)
            if mime is None:
                record["reason"] = "not_an_image"
                return record

            record.update(
                status="downloaded",
                sha256=hashlib.sha256(resp.content).hexdigest()[:16],
                mime=mime,
                bytes=len(resp.content),
                b64=base64.b64encode(resp.content).decode("utf-8"),
            )
            return record
        except UnsafeURLError:
            record["reason"] = "ssrf_blocked"
            logger.warning("SSRF protection blocked an image URL")
            return record
        except Exception as e:
            record["reason"] = "network_error"
            logger.warning("Görsel indirilemedi: %s", type(e).__name__)
            return record

    async def _download_and_encode_image(
        self, image_url: str, client: Optional[httpx.AsyncClient] = None
    ) -> Optional[str]:
        """Geriye uyumlu sarmalayıcı: doğrulamalı indirme -> base64 (veya None)."""
        record = await self._download_image_record(image_url, client=client)
        return record.get("b64")

    @staticmethod
    def _derive_confidence(records: List[Dict[str, Any]], result: "VisualEvidence") -> float:
        """[012]/[015] fix: confidence PROMPT'TAN ve provider'dan DEĞİL,
        gözlemlenebilir teminattan türetilir.

        - download_coverage: başarılı doğrulamalı indirme oranı
        - evidence_richness: dolu kanıt alanları oranı (5 alan)
        """
        downloaded = sum(1 for r in records if r.get("status") == "downloaded")
        download_coverage = (downloaded / len(records)) if records else 0.0

        evidence_fields = (
            result.detected_objects,
            result.environment_and_places,
            result.activity_signals,
            result.visual_evidence_summary,
            result.aesthetic_style,
        )

        def _bears(field: Any) -> bool:
            if isinstance(field, str):
                return bool(field.strip())
            if isinstance(field, list):
                return any(isinstance(i, str) and i.strip() for i in field)
            return bool(field)

        rich = sum(1 for f in evidence_fields if _bears(f)) / len(evidence_fields)
        return round(0.5 * download_coverage + 0.5 * rich, 3)

    async def analyze_images(self, image_urls: List[str], target_context: str = "") -> VisualEvidence:
        """
        Fotoğraf URL'lerini indirir ve Multimodal Vision modeliyle inceler.
        """
        valid_urls = [u for u in image_urls if isinstance(u, str) and u.startswith("http")][:4]
        if not valid_urls:
            return VisualEvidence(
                detected_objects=[],
                environment_and_places=[],
                aesthetic_style="Görsel bulunamadı",
                activity_signals=[],
                visual_evidence_summary="İncelenecek fotoğraf verisi yok.",
                confidence=0.0,
                data_confidence=False,
                fallback_reason="no_urls"
            )

        # Parallel image download with shared client for connection pooling
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=False) as client:
            tasks = [self._download_image_record(url, client=client) for url in valid_urls]
            records = await asyncio.gather(*tasks)

        # [014] provenance: hangi URL analiz edildi, hangisi neden düşürüldü.
        provenance = [
            {k: r.get(k) for k in ("source_url", "status", "reason", "sha256", "mime", "bytes")}
            for r in records
        ]
        ok_records = [r for r in records if r.get("status") == "downloaded" and r.get("b64")]
        encoded_images = [r["b64"] for r in ok_records]

        if not encoded_images:
            return VisualEvidence(
                detected_objects=[],
                environment_and_places=[],
                aesthetic_style="Görseller indirilemedi",
                activity_signals=[],
                visual_evidence_summary="Fotoğraflar erişim kısıtlaması nedeniyle indirilemedi.",
                confidence=0.0,
                data_confidence=False,
                fallback_reason="download_failed",
                image_provenance=provenance,
            )

        # Multimodal Vision Prompt
        # [012] fix: prompt'ta örnek/önerilen numeric confidence YOK. Modelden
        # confidence üretmesi istenmez; güven yerel olarak türetilir ([015]).
        prompt = f"""
Aşağıda hedefin Instagram profilinden çekilen {len(encoded_images)} adet fotoğrafın verisi sunulmaktadır.
Görevin, bu fotoğraflardaki SOMUT kanıtları, nesneleri, mekanları ve görsel atmosferi tespit etmektir.
Asla basmakalıp psikoloji uydurma. Sadece fotoğraflarda fiilen görünen nesneleri ve detayları yaz.

Hedef Bağlamı: "{target_context}"

Aşağıdaki JSON şemasına tam uygun yanıt ver. "confidence" gibi bir ölçüm ÜRETME;
yalnızca gözlem alanlarını doldur:
{{
  "detected_objects": ["Fotoğraflarda fiilen görünen somut nesneler (ör: analog kamera, kitap, plak, seramik, kahve fincanı, mikrofon vb.)"],
  "environment_and_places": ["Fotoğrafların çekildiği mekanlar (ör: karanlık oda, stüdyo, orman, sahil, loş kafe vb.)"],
  "aesthetic_style": "Görsel tarz (ör: 35mm analog gren, desatüre monokrom, loş ışık, canlı minimal)",
  "activity_signals": ["Fotoğraflarda yapılan eylemler (ör: film banyosu, gece yürüyüşü, çizim, kayıt vb.)"],
  "visual_evidence_summary": "Fotoğraflardan çıkan somut ve net 2 cümlelik görsel kanıt özeti"
}}
"""
        try:
            image_uris = [f"data:image/jpeg;base64,{b64}" for b64 in encoded_images]
            result = await self.llm_gateway.query_json_chain(
                prompt=prompt,
                schema=VisualEvidence,
                task="vision",
                temperature=0.2,
                images=image_uris,
                agent_name="vision_analyzer",
            )
            # [015] fix: provider'ın bildirdiği confidence/data_confidence
            # KANIT OLARAK KABUL EDİLMEZ; forensik güven yerel teminattan türetilir.
            result.confidence = self._derive_confidence(records, result)
            has_evidence = result.confidence > 0.5
            result.data_confidence = bool(ok_records) and has_evidence
            result.fallback_reason = None if result.data_confidence else "empty_vision_output"
            result.image_provenance = provenance
            return result
        except Exception as e:
            logger.warning(f"Vision analizi çalışırken hata: {e}")

        return VisualEvidence(
            detected_objects=[],
            environment_and_places=[],
            aesthetic_style="UNAVAILABLE",
            activity_signals=[],
            visual_evidence_summary="NO_EVIDENCE",
            confidence=0.0,
            data_confidence=False,
            fallback_reason="llm_unavailable",
            image_provenance=provenance,
        )
