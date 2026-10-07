"""Ağ hijyeni — hedef GERÇEKTEN dış ağda mı? (SSRF kapısı, fail-closed).

Üç sensör ailesi bu kapıyı paylaşır (kurum taraması · medya indirme · benzeri
dış istekler). Kural tek yerde yaşar; kopyası yasak:

    Hedef adı özel/yerel bir IP'ye çözülüyorsa istek REDDEDİLİR.
    Operatör açıkça istisna verdiyse (ortam değişkeni) geçer.

Ortam değişkeni bilinçli olarak ÇAĞIRANDAN gelir: her aile kendi anahtarını
kullanır (``PINEAL_COMPANY_ALLOW_PRIVATE`` · ``PINEAL_MEDIA_ALLOW_PRIVATE``),
böylece bir ailenin istisnası diğerini sessizce açmaz.
"""

from __future__ import annotations
import logging
logger = logging.getLogger(__name__)

import ipaddress
import os
import socket

__all__ = ["allow_private", "is_private_host"]

_TRUTHY = frozenset({"1", "true", "yes", "on"})


def allow_private(env_name: str) -> bool:
    """Operatör bu aile için özel adres istisnası verdi mi?"""
    return os.getenv(env_name, "").strip().lower() in _TRUTHY


def is_private_host(hostname: str, *, env_name: str) -> bool:
    """Hedef özel/yerel ağa mı çözülüyor?

    Çözülemiyorsa ``False`` döner (kararı ağ katmanı verir; uydurma ret yok).
    """
    if allow_private(env_name):
        return False
    host = (hostname or "").strip().strip("[]").lower()
    if not host:
        return False
    if host in {"localhost", "localhost.localdomain"}:
        return True
    try:
        infos = socket.getaddrinfo(host, None)
    except Exception:
        return False
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except Exception:
            logger.warning('Suppressed exception observed at agent_core/services/net_hygiene.py:52 (continue)')
            continue
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return True
    return False
