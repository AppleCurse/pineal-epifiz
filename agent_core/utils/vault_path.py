"""Kasa dosyası yolunun TEK çözüm kuralı (P1-33).

Öncelik: ``PINEAL_VAULT_FILE`` (açık ayar) > ``/app/vault-data`` (birim
bağlıysa) > çalışma dizini. Eskiden her çağıran kendi kararını veriyordu:
API CWD-göreli okurken compose/railway /app/vault-data birimini bağlıyordu —
hacim kalıcı diye belgelenmişti ama uygulama hiç okumuyordu.
"""

from __future__ import annotations

import os

#: Kasa hacminin bağlandığı kanonik yol (docker-compose.yml / railway.toml).
VAULT_DATA_DIR = "/app/vault-data"


def default_vault_file() -> str:
    env = os.getenv("PINEAL_VAULT_FILE", "").strip()
    if env:
        return env
    if os.path.isdir(VAULT_DATA_DIR):
        return f"{VAULT_DATA_DIR}/.pineal_vault.json"
    return ".pineal_vault.json"
