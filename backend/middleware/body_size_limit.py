"""İstek gövdesi tavanı (body size limit) middleware'i.

[AUDIT 2026-10-07 · P2] ``backend/api.py`` 6.000+ satırlık tek bir modül
hâline gelmişti. Bölme (decomposition) planının İLK ADIMI olarak, en iyi
test edilmiş ve en az bağımlılığı olan katman buraya taşındı: kendi
kendine yeten, saf bir ASGI middleware'i.

Geriye dönük uyumluluk: ``backend.api`` bu isimleri YENİDEN İHRAÇ eder,
yani mevcut ``from backend.api import BodySizeLimitMiddleware``
içe aktarımları DEĞİŞMEDEN çalışmaya devam eder.

Ayrıntılı bölme planı: ``docs/reports/API_MONOLITH_SPLIT_PLAN.md``.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

import json
import os
from typing import Optional


class BodySizeLimitExceeded(Exception):
    pass


class BodySizeLimitMiddleware:
    """[P0-BOOT-FIX] İstek gövdesi tavanı middleware'i.

    uvicorn 0.52.4'te --limit-max-request-size bayrağı bulunmadığından
    tavan uygulama katmanında enforced edilir.
    Varsayılan: 1048576 bayt (1 MiB), PINEAL_MAX_BODY_BYTES ile geçersiz kılınabilir.
    """

    def __init__(self, app, max_bytes: Optional[int] = None):
        self.app = app
        if max_bytes is not None:
            self.max_bytes = max_bytes
        else:
            try:
                self.max_bytes = int(os.getenv("PINEAL_MAX_BODY_BYTES", "1048576"))
            except ValueError:
                self.max_bytes = 1048576

    def _get_max_bytes(self) -> int:
        try:
            return int(os.getenv("PINEAL_MAX_BODY_BYTES", str(self.max_bytes)))
        except ValueError:
            return self.max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        max_bytes = self._get_max_bytes()

        # 1. Content-Length başlığı kontrolü (erken ret)
        for name, value in scope.get("headers", []):
            if name.lower() == b"content-length":
                try:
                    content_length = int(value.decode("latin-1"))
                    if content_length > max_bytes:
                        await self._send_413(send, max_bytes)
                        return
                except (ValueError, UnicodeDecodeError) as exc:
                    logger.warning(
                        "[__call__] beklenmeyen hata (ValueError,UnicodeDecodeError) yutulmadı — iz bırakıldı: %s", exc, exc_info=True
                    )
                break

        # 2. Akış / Parçalı (chunked) gövde kontrolü
        total_received = 0
        body_size_exceeded = False

        async def limited_receive():
            nonlocal total_received, body_size_exceeded
            message = await receive()
            if message["type"] == "http.request":
                chunk = message.get("body", b"")
                total_received += len(chunk)
                if total_received > max_bytes:
                    body_size_exceeded = True
                    raise BodySizeLimitExceeded()
            return message

        async def tracked_send(message):
            if body_size_exceeded:
                return
            await send(message)

        try:
            await self.app(scope, limited_receive, tracked_send)
        except BodySizeLimitExceeded:
            # [AUDIT 2026-10-07 P0] YALNIZCA kendi gövde-tavanı sinyalimiz
            # yutulur; 413 cevabı aşağıda yazılır.
            #
            # ESKİ DAVRANIŞ (kusur): `except Exception: pass` — uygulamanın
            # fırlattığı HER istisnayı yutuyordu. Sonuç: gerçek bir 500'lük
            # hata istemciye hiç ulaşmıyor, cevap gövdesi yarım/boş kalıyor
            # ve hata Starlette'in ServerErrorMiddleware'ine hiç görünmüyordu.
            # Bu middleware bir hata izolasyon katmanı DEĞİLDİR; tek işi
            # gövde tavanıdır. Alakasız istisnalar hata katmanına bırakılır.
            #
            # [AUDIT 2026-10-08] Kasıtlı sinyal: bu bir HATA değil, istemci
            # kaynaklı reddir — traceback'siz tek satırlık info izi bırakılır.
            logger.info("BODY_TOO_LARGE: gövde tavanı aşıldı, 413 döndürülüyor")

        if body_size_exceeded:
            await self._send_413(send, max_bytes)

    async def _send_413(self, send, max_bytes: int):
        body = json.dumps({
            "code": "BODY_TOO_LARGE",
            "error": {
                "code": "BODY_TOO_LARGE",
                "message": f"Request body exceeds maximum allowed size of {max_bytes} bytes",
                "max_bytes": max_bytes,
            },
            "max_bytes": max_bytes,
        }).encode("utf-8")
        await send({
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("latin-1")),
            ],
        })
        await send({
            "type": "http.response.body",
            "body": body,
        })
