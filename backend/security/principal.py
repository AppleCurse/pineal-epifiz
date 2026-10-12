"""Operatör kimliği (principal) ve oda sahipliği mührü.

``client_id`` istemcinin serbestçe seçtiği bir dizedir; tek başına güvenlik
sınırı DEĞİLDİR. Bu modül sunulan token'ı bir operatör KİMLİĞİNE çözer
(``resolve_principal``) ve odayı o kimliğe MÜHÜRLER. Mühür ``ContextVar`` ile
taşınır; böylece ``get_room``'un 300+ çağrı yerinin imzası değişmez.

Kurallar:
  * ``principal is None`` -> kimlik doğrulama KAPALI (development): mühür
    uygulanmaz; mevcut davranış korunur. Production'da auth fail-closed
    zorunludur (``security_posture`` -> ``PRODUCTION_AUTH_REQUIRED``),
    dolayısıyla principal daima doludur.
  * Oda YOK -> çağıran oluşturur ve ``"_owner": principal`` yazar.
  * Oda VAR ama SAHİPSİZ (eski kayıt) -> ilk erişen mühürler.
  * Oda başka bir principal'a mühürlü -> erişim reddedilir (403).

Tek ``PINEAL_TOKEN`` paylaşan dağıtımda herkes AYNI principal'dır ("root") ve
mühür ayrıştırmaz: tek token = tek operatör. Operatörleri ayırt etmek için
``PINEAL_OPERATOR_TOKENS`` ile operatör başına ayrı token tanımlanır
(bkz. ``.env.example`` ve ``README.md`` "Çok operatörlü kimlik").
"""

from __future__ import annotations

import logging
from contextvars import ContextVar
from typing import Optional

logger = logging.getLogger(__name__)

__all__ = [
    "RoomForbiddenError",
    "bind_principal",
    "current_principal",
    "enforce_room_ownership",
    "forbidden_body",
    "reset_principal",
]


class RoomForbiddenError(RuntimeError):
    """Başka bir operatöre mühürlü odaya erişim denemesi (sahiplik reddi).

    Bilinçli olarak ``client_id``'yi MESAJDA TAŞIMAZ: başka bir operatörün oda
    adı başlı başına bilgi olabilir. Yalnız uzunluk loglanır.
    """

    def __init__(self, client_id: str):
        self.client_id = client_id
        super().__init__("ROOM_FORBIDDEN")


_current_principal: ContextVar[Optional[str]] = ContextVar(
    "pineal_principal", default=None
)


def bind_principal(principal: Optional[str]):
    """İstek/bağlantı başına operatör kimliğini bağlar.

    Döndürdüğü token ``ContextVar.reset()`` ile GERİ ALINMALIDIR; aksi halde
    kimlik aynı task içindeki sonraki işlere sızar. Kullanım::

        token = bind_principal(principal)
        try:
            ...
        finally:
            if token is not None:
                reset_principal(token)
    """
    return _current_principal.set(principal)


def reset_principal(token) -> None:
    """``bind_principal`` ile alınan token'ı geri alır (sessiz, güvenli)."""
    if token is None:
        return
    try:
        _current_principal.reset(token)
    except (ValueError, LookupError):  # pragma: no cover - farklı context
        logger.debug("principal token başka bir context'te üretildi; atlandı")


def current_principal() -> Optional[str]:
    """Bağlı operatör kimliği; bağlanmamışsa ``None`` (development)."""
    return _current_principal.get()


def enforce_room_ownership(
    client_id: str, room: Optional[dict], principal: Optional[str]
) -> Optional[str]:
    """Oda sahipliğini uygular; oda kaydına mührü YAZAR.

    Dönüş:
      * ``None``            -> erişim SERBEST (mühür uygulandı/taşındı).
      * ``"forbidden"``     -> oda BAŞKA bir operatöre mühürlü; çağıran 403
                               (``RoomForbiddenError``) üretmelidir.

    Kurallar:
      1. ``principal is None`` -> kimlik doğrulama kapalı: mühür YOK
         (development; bugünkü davranış korunur).
      2. Oda YOK -> çağıran oluşturacak; ``None`` döner ve oluşturan taraf
         ``"_owner": principal`` yazmalıdır.
      3. Oda VAR ama SAHİPSİZ (eski sürümden kalma / auth sonradan açılmış) ->
         ÇAĞIRAN MÜHÜRLER. Bilinçli: mevcut dağıtımlar kilitlenip dışarıda
         bırakılmaz; ilk erişen sahip olur.
      4. Oda VAR ve sahibi FARKLI -> ``"forbidden"``.

    Ret durumunda odanın VARLIĞI da doğrulanmaz: yanıt 404 değil 403'tür ve
    gövde oda adını İÇERMEZ.
    """
    if principal is None:
        return None
    if room is None:
        return None
    owner = room.get("_owner")
    if owner is None:
        room["_owner"] = principal
        return None
    if owner != principal:
        logger.warning(
            "ROOM_FORBIDDEN: principal=%s başka bir operatöre mühürlü odaya "
            "erişmeye çalıştı (client_id uzunluğu=%d)",
            principal,
            len(client_id or ""),
        )
        return "forbidden"
    return None


def forbidden_body(*, openai_style: bool, error_factory) -> dict:
    """403 ROOM_FORBIDDEN gövdesi — TEK sözleşme (HTTP ve /v1 için).

    ``openai_style`` -> ``/v1/*`` OpenAI-uyumlu hata şeması ister.
    Gövde oda adını İÇERMEZ; oda adı yanıtta tekrarlanmaz.
    """
    if openai_style:
        return error_factory(
            "This room belongs to another operator",
            "authentication_error",
            "room_forbidden",
        )
    return {
        "error": {
            "code": "ROOM_FORBIDDEN",
            "message": "Bu oda başka bir operatöre mühürlü.",
        }
    }
