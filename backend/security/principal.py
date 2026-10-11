"""Operatör kimliği (principal) ve oda sahipliği mühürü.

[PROD AUDIT 2026-10-11 · P0] Bu modül, canlı PoC ile ÖLÇÜLEN bir IDOR
(Insecure Direct Object Reference) kusurunu kapatmak için eklendi.

ÖLÇÜLEN KUSUR (yamadan önce, production konfigürasyonu ile çalışan gerçek
sunucuya karşı):

    Dağıtımın TEK bir kimliği vardı (``PINEAL_TOKEN``). Oda anahtarı olan
    ``client_id`` ise istemcinin SERBESTÇE seçtiği bir dizeydi ve sunucuda
    HİÇBİR sahiplik bağı yoktu — ``get_room()`` yalnız BİÇİM ve UZUNLUK
    doğruluyordu. Sonuç: aynı token'ı bilen ikinci bir operatör, ``client_id``
    yazarak başka bir operatörün odasına tam erişiyordu.

    Kanıtlanan saldırılar (hepsi HTTP 200 / kabul edildi):
      * ``GET  /api/tasks?client_id=<kurban>``       -> görev listesi okundu
      * ``GET  /api/telemetry?client_id=<kurban>``   -> telemetri okundu
      * ``GET  /api/vault/status?client_id=<kurban>``-> kasa durumu okundu
      * ``POST /api/vault``  ``client_id=<kurban>``  -> kurbanın LLM anahtarı
        ve X oturum çerezi SALDIRGANIN değeriyle DEĞİŞTİRİLDİ
        (``has_cookie: true``, ``can_scrape: true``)
      * ``DELETE /api/tasks/<gerçek_id>?client_id=<kurban>`` ->
        ``{"status":"deleted","memory_file_deleted":true}`` yani ADLİ KANIT
        DİSKTEN KALICI SİLİNDİ (zincir-i vekaat yok oldu)
      * ``/ws/<kurban>`` -> ``auth_ok`` + CANLI telemetri karesi yakalandı
        (kurbanın kasa logu saldırgana aktı)

KAPATMA: token artık bir KİMLİĞE çözülür (``resolve_principal``) ve oda o
kimliğe MÜHÜRLENİR. Mühür ``ContextVar`` ile taşınır; ``get_room``'un 300+
çağrı yerinin imzasını değiştirmeye gerek kalmaz.

GERİYE DÖNÜK UYUM (bilinçli):
  * ``principal is None`` -> kimlik doğrulama KAPALI (development). Mühür
    uygulanmaz; bu, bugünkü davranışın birebir aynısıdır. Production'da auth
    zaten fail-closed zorunludur (``security_posture`` ->
    ``PRODUCTION_AUTH_REQUIRED``), dolayısıyla principal daima doludur.
  * Tek ``PINEAL_TOKEN`` paylaşan bir dağıtımda herkes AYNI principal'dır
    ("root") ve mühür AYRIŞTIRMAZ. Kimlikleri ayırt etmek imkânsızdır:
    TEK token = TEK operatör. Bu yüzden production'da
    ``PINEAL_OPERATOR_TOKENS`` ile operatör başına ayrı token ZORUNLUDUR
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
    """Başka bir operatöre mühürlü odaya erişim denemesi (IDOR reddi).

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

    Sızıntı yüzeyini daraltmak için ret durumunda odanın VARLIĞI da
    doğrulanmaz: yanıt 404 değil 403'tür ama gövde oda adı İÇERMEZ.
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
    Gövde oda adını İÇERMEZ: başka bir operatörün oda adı bilgi sızıntısıdır.
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
