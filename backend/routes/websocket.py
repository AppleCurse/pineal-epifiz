"""`/ws/{client_id}` — canlı telemetri soketi OTURUM MANTIĞI.

[PROD AUDIT 2026-10-11] ``docs/reports/API_MONOLITH_SPLIT_PLAN.md`` §3 (satır
66) ``/ws`` ucu için ``backend/routes/websocket.py`` modülünü öngörür; bu
dosya o planın UYGULANMIŞ adımıdır. ``backend/api.py`` içinde yalnız ince rota
sarmalayıcısı kalır (monolit tavanı ratchet'ı: ``api.py`` küçülmelidir).

Bu uçta denetimde ÖLÇÜLEN üç kusur vardı ve üçü de burada kapatılır:

1. **HIZ SINIRI YOKTU.** ``auth_middleware`` yalnız ``/api/`` ve ``/v1/``
   öneklerini kapsıyordu; ``/ws/`` HİÇ geçmiyordu. ``accept()`` da auth'tan
   ÖNCE yapıldığı için kimliği olmayan bir istemci sınırsız soket açıp her
   birini kimlik penceresi boyunca (5 sn) tutabiliyordu: bağlantı/bellek
   tüketimi ile hizmet dışı bırakma.
2. **ODA SAHİPLİĞİ YOKTU.** Yalnız paylaşılan dağıtım token'ı doğrulanıyordu.
   Token'ı bilen herkes ``/ws/{baskasinin_client_id}`` bağlanıp kurbanın
   odasının CANLI telemetrisini dinleyebiliyordu. Ölçüldü: ``auth_ok`` alındı
   ve kurbanın kasa logu (``"KASA: API Anahtarı girildi…"``) saldırgana aktı.
3. **``auth_ok`` SAHİPLİKTEN ÖNCE gönderiliyordu.** Reddedilen saldırgan bile
   "kimliğim geçerli ve soket açıldı" teyidi alıyordu.

DOĞRU SIRA: hız kapısı -> accept -> kimlik -> **SAHİPLİK** -> auth_ok -> oda.

``accept()`` neden auth'tan ÖNCE kalmak zorunda: Cloudflare'ın istemci
WebSocket API'si ÖZEL BAŞLIK iletmez (``functions/ws/[[path]].ts`` başlık
tabanlı auth'u bu yüzden kullanamaz). Token ilk MESAJLA gelir; bu bilinçli bir
tasarım seçimidir ve sır URL'ye/log'a yazılmaz. Karşılığında kimlik penceresi
kısa tutulur (``WS_AUTH_TIMEOUT_S``) ve bağlantı hızı sınırlanır.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Optional

from agent_core.utils.security import (
    SecurityConfigurationError,
    resolve_principal,
    security_posture,
    token_matches,
)
from backend.security.principal import (
    RoomForbiddenError,
    bind_principal,
    enforce_room_ownership,
    reset_principal,
)

logger = logging.getLogger(__name__)

__all__ = ["WS_AUTH_TIMEOUT_S", "run_telemetry_socket"]

#: Kimlik penceresi. Kimliksiz açılan bir soket en fazla bu süre kadar kaynak
#: tutar, sonra 1008 (Policy Violation) ile kapatılır.
WS_AUTH_TIMEOUT_S = 5.0

#: 1013 = Try Again Later (geçici; istemci geri çekilmeli).
_CLOSE_TRY_AGAIN = 1013
#: 1008 = Policy Violation (kimlik/politika reddi).
_CLOSE_POLICY = 1008


async def run_telemetry_socket(
    websocket: Any,
    client_id: str,
    *,
    get_room: Callable[[str], dict],
    rate_limit: Callable[[str, str], bool],
    room_capacity_error: type,
    http_exception: type,
) -> None:
    """Bir telemetri soketi oturumunu uçtan uca yürütür.

    Bağımlılıklar ENJEKTE edilir (``get_room``, ``rate_limit``): bu modül
    ``backend.api``'yi İÇE AKTARMAZ, dolayısıyla dairesel bağımlılık yoktur ve
    modül tek başına test edilebilir.

    Sözleşme: fonksiyon istisna FIRLATMAZ; her red yolu soketi uygun kodla
    kapatır ve ``None`` döner. ``asyncio.CancelledError`` BİLİNÇLİ olarak
    yutulmaz (iptal yukarı yayılır) — temizlik ``finally`` ile garanti edilir
    (bkz. ``tests/audit/test_production_audit_findings.py`` P1-18c).
    """
    try:
        posture = security_posture()
    except SecurityConfigurationError:
        await websocket.close(code=_CLOSE_TRY_AGAIN)
        return

    # (1) Hız kapısı accept()'ten ÖNCE: kimliksiz bağlantı seli kesilir.
    # `getattr`: Starlette WebSocket'i `.client` taşır ama test sahteleri
    # taşımayabilir — AttributeError ile patlamak yerine "unknown" kovasına
    # düşer (yine de SINIRLANIR, yani kapı atlanmaz).
    client = getattr(websocket, "client", None)
    peer = getattr(client, "host", None) or "unknown"
    if not rate_limit(f"ws:{peer}", "ws"):
        logger.warning("WS_RATE_LIMITED peer=%s", peer)
        await websocket.close(code=_CLOSE_TRY_AGAIN)
        return

    await websocket.accept()

    principal: Optional[str] = None
    principal_token = None
    try:
        if posture.get("auth_required"):
            presented = await _authenticate(websocket)
            if presented is None:
                await websocket.close(code=_CLOSE_POLICY)
                return
            # (2) Token -> OPERATÖR KİMLİĞİ. Oda sahipliği bunu okur.
            principal = resolve_principal(presented)

        # Kimlik doğrulama kapalıysa principal None kalır ve mühür uygulanmaz
        # (development). Production'da auth zorunlu olduğundan daima doludur.
        principal_token = bind_principal(principal)

        room = await _acquire_room(
            websocket,
            client_id,
            get_room=get_room,
            room_capacity_error=room_capacity_error,
            http_exception=http_exception,
            principal=principal,
        )
        if room is None:
            return  # soket _acquire_room içinde KAPATILDI (await ile)

        # (3) auth_ok YALNIZ sahiplik kontrolü geçtikten sonra.
        if posture.get("auth_required"):
            await websocket.send_json({"type": "auth_ok"})

        room["websockets"].add(websocket)
        try:
            while True:
                await websocket.receive_text()
        except Exception:
            # [AUDIT P1-18c] Eskiden bare `except:` idi: BaseException da
            # yakalandığı için asyncio.CancelledError yutuluyor ve görev iptal
            # edilmiş sayılmıyordu (task.cancelled() == False).
            # `except Exception:` tek başına YETMEZ: kontrol ölçümünde iptal
            # durumunda temizlik kayboluyordu. Bu yüzden temizlik finally'de.
            logger.debug("WebSocket bağlantısı koptu: %s", client_id)
        finally:
            room["websockets"].discard(websocket)
    finally:
        reset_principal(principal_token)


async def _authenticate(websocket: Any) -> Optional[str]:
    """İlk mesajdan token'ı doğrular; başarılıysa token'ı, değilse ``None``.

    Dönüş değeri ``resolve_principal`` için GEREKLİDİR: yalnız "geçerli/geçmez"
    değil, HANGİ operatör olduğu da çözülmelidir.
    """
    try:
        auth_message = await asyncio.wait_for(
            websocket.receive_json(), timeout=WS_AUTH_TIMEOUT_S
        )
    except (asyncio.TimeoutError, ValueError, RuntimeError):
        # ValueError  -> bozuk JSON gövdesi
        # RuntimeError -> istemci kimlik göndermeden soketi kapattı
        return None
    # İstemci JSON dizi/dize gönderirse `.get` AttributeError fırlatıyordu
    # (yakalanmamış istisna -> 500 izi). Tip açıkça doğrulanır.
    if not isinstance(auth_message, dict):
        return None
    presented = auth_message.get("token")
    if (
        auth_message.get("type") != "auth"
        or not isinstance(presented, str)
        or not token_matches(presented)
    ):
        return None
    return presented


async def _acquire_room(
    websocket: Any,
    client_id: str,
    *,
    get_room: Callable[[str], dict],
    room_capacity_error: type,
    http_exception: type,
    principal: Optional[str],
) -> Optional[dict]:
    """Odayı SAHİPLİK MÜHRÜ ile alır; reddedilirse soketi kapatır, ``None``.

    ``async`` olmasının nedeni dürüstlüktür: ``websocket.close()`` bir
    coroutine'dir ve kapatma ERTELENİRSE (``loop.create_task``) soket bir süre
    daha açık kalır — yani "reddedildi" kararı ile "bağlantı kapandı" gerçeği
    ayrışırdı. Burada kapatma DOĞRUDAN ``await`` edilir.
    """
    try:
        room = get_room(client_id)
    except RoomForbiddenError:
        # Oda adı yanıtta TEKRARLANMAZ: başka operatörün oda adının VARLIĞI
        # bile bilgi sızıntısıdır.
        logger.warning("WS_ROOM_FORBIDDEN principal=%s (oda adı loglanmadı)", principal)
        await _safe_close(websocket, _CLOSE_POLICY)
        return None
    except http_exception:
        await _safe_close(websocket, _CLOSE_POLICY)
        return None
    except room_capacity_error:
        await _safe_close(websocket, _CLOSE_TRY_AGAIN)
        return None
    # get_room ContextVar üzerinden zaten mühürler; ContextVar DIŞINDAN
    # çağrılan yollar (testler, iç çağrılar) için aynı kural bir kez daha
    # açıkça uygulanır. Idempotent: aynı principal -> değişiklik yok.
    if enforce_room_ownership(client_id, room, principal) == "forbidden":
        logger.warning("WS_ROOM_FORBIDDEN principal=%s (oda adı loglanmadı)", principal)
        await _safe_close(websocket, _CLOSE_POLICY)
        return None
    return room


async def _safe_close(websocket: Any, code: int) -> None:
    """Soketi kapatır; soket zaten kapalıysa patlamaz (dürüst log)."""
    try:
        await websocket.close(code=code)
    except Exception:  # pragma: no cover - soket zaten kapalı olabilir
        logger.debug("WS close sırasında hata (kod=%s)", code, exc_info=True)
