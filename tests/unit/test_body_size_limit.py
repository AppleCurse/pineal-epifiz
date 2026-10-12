"""P0-BOOT-FIX — İstek gövdesi tavanı sözleşme testleri.

1. uvicorn 0.52.4'te `--limit-max-request-size` bayrağının bulunmadığı ve
   verildiğinde uvicorn'un çöktüğü (P0 kök nedeni kanıtı).
2. Dockerfile ve DEPLOYMENT_CLOUDFLARE.md içinde bu geçersiz bayrağın kalmadığı.
3. BodySizeLimitMiddleware'in app üzerinde kayıtlı olduğu.
4. 1 MiB altı isteklerin normal geçtiği.
5. Content-Length > 1 MiB olan isteklerin 413 BODY_TOO_LARGE ile reddedildiği.
6. Chunked / akış şeklinde 1 MiB aşan isteklerin 413 ile kesildiği.
7. PINEAL_MAX_BODY_BYTES ortam değişkeninin tavanı dinamik değiştirebildiği.
8. 413 yanıtının dürüst hata şeması ve max_bytes içerdiği.
"""

import os
import subprocess
import sys
import pytest
from starlette.testclient import TestClient

from backend.api import app, BodySizeLimitMiddleware


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


def test_uvicorn_rejects_limit_max_request_size_flag():
    """P0 kanıtı: uvicorn 0.52.4 --limit-max-request-size bayrağını reddeder."""
    result = subprocess.run(
        [sys.executable, "-m", "uvicorn", "--limit-max-request-size", "1048576"],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    combined = (result.stdout + result.stderr).lower()
    assert "no such option" in combined or "unrecognized" in combined


def test_dockerfile_cmd_has_no_limit_max_request_size():
    """Dockerfile CMD satırında geçersiz --limit-max-request-size bayrağı bulunmamalı."""
    dockerfile_path = os.path.join(os.path.dirname(__file__), "..", "..", "Dockerfile")
    with open(dockerfile_path, "r", encoding="utf-8") as f:
        content = f.read()

    for line in content.splitlines():
        line_clean = line.strip()
        if line_clean.startswith("CMD") or line_clean.startswith("ENTRYPOINT"):
            assert "--limit-max-request-size" not in line_clean, (
                "Dockerfile boot komutunda uvicorn'u çökertecek --limit-max-request-size bayrağı var!"
            )


def test_deployment_doc_has_no_invalid_uvicorn_flag():
    """DEPLOYMENT_CLOUDFLARE.md içinde uvicorn komutu olarak bayrak geçmemeli."""
    doc_path = os.path.join(os.path.dirname(__file__), "..", "..", "docs", "DEPLOYMENT_CLOUDFLARE.md")
    with open(doc_path, "r", encoding="utf-8") as f:
        content = f.read()

    for line in content.splitlines():
        if "uvicorn" in line.lower() or "cmd" in line.lower():
            assert "--limit-max-request-size" not in line


def test_middleware_registered_on_app():
    """BodySizeLimitMiddleware app.user_middleware listesinde kayıtlı olmalıdır."""
    registered_classes = [m.cls for m in app.user_middleware]
    assert BodySizeLimitMiddleware in registered_classes, (
        "BodySizeLimitMiddleware app üzerinde kayıtlı değil!"
    )


def test_small_request_passes(client):
    """1 MiB altındaki normal istekler 413 almaz (200 veya normal api cevabı alır)."""
    small_payload = b'{"client_id": "test", "url": "test"}'
    response = client.post("/api/initiate", content=small_payload, headers={"Content-Type": "application/json"})
    assert response.status_code != 413


def test_content_length_oversized_returns_413(client):
    """Content-Length 1 MiB (1048576) aşan istekler anında 413 BODY_TOO_LARGE döner."""
    oversized_len = 1048576 + 1024  # ~1.001 MiB
    fake_body = b"X" * oversized_len
    response = client.post(
        "/api/initiate",
        content=fake_body,
        headers={"Content-Type": "application/json", "Content-Length": str(oversized_len)},
    )
    assert response.status_code == 413
    data = response.json()
    assert data.get("code") == "BODY_TOO_LARGE" or data.get("error", {}).get("code") == "BODY_TOO_LARGE"
    assert data.get("max_bytes") == 1048576 or data.get("error", {}).get("max_bytes") == 1048576


def test_streaming_body_oversized_returns_413(client):
    """Chunked / akış şeklinde gönderilen ve 1 MiB'ı aşan gövde 413 ile kesilir."""
    def gen_chunks():
        chunk = b"A" * 65536  # 64 KiB
        for _ in range(20):     # 20 * 64 KiB = 1.25 MiB (> 1 MiB)
            yield chunk

    response = client.post(
        "/api/initiate",
        content=gen_chunks(),
        headers={"Content-Type": "application/octet-stream"},
    )
    assert response.status_code == 413
    data = response.json()
    assert "BODY_TOO_LARGE" in str(data)


def test_custom_env_override(client, monkeypatch):
    """PINEAL_MAX_BODY_BYTES ortam değişkeni ile tavan özelleştirilebilir."""
    monkeypatch.setenv("PINEAL_MAX_BODY_BYTES", "500")

    # 400 bayt -> geçer (413 almaz)
    res_ok = client.post(
        "/api/initiate",
        content=b"X" * 400,
        headers={"Content-Type": "application/json", "Content-Length": "400"},
    )
    assert res_ok.status_code != 413

    # 600 bayt -> 413 alır
    res_over = client.post(
        "/api/initiate",
        content=b"X" * 600,
        headers={"Content-Type": "application/json", "Content-Length": "600"},
    )
    assert res_over.status_code == 413
    data = res_over.json()
    assert "BODY_TOO_LARGE" in str(data)
    assert data.get("max_bytes") == 500 or data.get("error", {}).get("max_bytes") == 500

# ─────────────────────────────────────────────────────────────────────────
# [AUDIT 2026-10-07 · P0] Middleware'in istisna yutma kusuru
#
# Kusur: `BodySizeLimitMiddleware.__call__` içindeki `except Exception: pass`
# gövde tavanıyla ilgisi OLMAYAN her uygulama hatasını yutuyordu. İstemci
# yarım/boş cevap alıyor, hata Starlette'in ServerErrorMiddleware'ine hiç
# ulaşmıyordu (teşhis edilemez 500'ler). Sözleşme artık: bu middleware
# YALNIZCA kendi BodySizeLimitExceeded sinyalini yakalar.
# ─────────────────────────────────────────────────────────────────────────


def _build_probe_app():
    """Middleware'i saran, kontrollü şekilde patlayan minimal bir uygulama."""
    from fastapi import FastAPI

    probe = FastAPI()
    probe.add_middleware(BodySizeLimitMiddleware)

    @probe.post("/boom")
    async def boom():
        raise RuntimeError("DOWNSTREAM_SENTINEL")

    @probe.get("/ok")
    async def ok():
        return {"ok": True}

    return probe


def test_unrelated_downstream_exception_reaches_the_client():
    """Ajan/uygulama hatası YUTULMAZ: istemci açıklamalı bir 500 alır.

    Kusurlu sürümde cevap gövdesi TAMAMEN BOŞ kalıyordu (''), çünkü
    middleware hatayı yutup sessizce dönüyordu. Düzeltilmiş sürümde hata
    ServerErrorMiddleware'e ulaşır ve istemci standart 'Internal Server
    Error' gövdesini alır. Bu yüzden gövdeyi de kontrol ediyoruz.
    """
    client = TestClient(_build_probe_app(), raise_server_exceptions=False)
    response = client.post("/boom", json={})
    assert response.status_code == 500
    assert response.text == "Internal Server Error", (
        "boş cevap gövdesi = istisna hâlâ yutuluyor: gövde-tavanı "
        "middleware'i kendisine ait olmayan hatayı sahiplenmiş"
    )


def test_downstream_exception_surfaces_to_the_server_layer():
    """Hata ServerErrorMiddleware'e ulaşmalı: orijinal istisna yükselir.

    Starlette'in ServerErrorMiddleware'i istemciye 500 yazdıktan sonra
    ASGI sunucusuna (burada TestClient'a) orijinal istisnayı yeniden
    fırlatır. Middleware hatayı yutarsa bu katman hiç devreye girmez ve
    orijinal istisna çağırana hiç ulaşmaz — yani teşhis imkânsız olur.
    """
    client = TestClient(_build_probe_app(), raise_server_exceptions=True)
    with pytest.raises(RuntimeError, match="DOWNSTREAM_SENTINEL"):
        client.post("/boom", json={})


def test_middleware_reraises_non_body_limit_exceptions():
    """Birim düzeyi kanıt: BodySizeLimitExceeded DIŞINDA her şey yükselir."""

    async def exploding_app(scope, receive, send):  # noqa: ARG001
        raise RuntimeError("DOWNSTREAM_SENTINEL")

    middleware = BodySizeLimitMiddleware(exploding_app, max_bytes=1024)
    scope = {"type": "http", "headers": []}

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):  # pragma: no cover - hiç çağrılmamalı
        raise AssertionError("istisna yutuldu: cevap kanalı kullanıldı")

    import asyncio

    with pytest.raises(RuntimeError, match="DOWNSTREAM_SENTINEL"):
        asyncio.run(middleware(scope, receive, send))


def test_middleware_swallows_only_its_own_body_limit_signal():
    """Kendi sinyali yutulur ve 413 üretilir (kontrol deneyi)."""
    sent = []

    async def oversized_app(scope, receive, send):  # noqa: ARG001
        # Gövdeyi sonuna kadar oku -> tavan aşılır -> sinyal fırlar.
        while True:
            message = await receive()
            if not message.get("more_body", False):
                break

    middleware = BodySizeLimitMiddleware(oversized_app, max_bytes=10)
    scope = {"type": "http", "headers": []}
    chunks = [b"X" * 6, b"Y" * 6]
    index = {"i": 0}

    async def receive():
        i = index["i"]
        index["i"] += 1
        if i < len(chunks):
            return {"type": "http.request", "body": chunks[i], "more_body": True}
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    import asyncio

    asyncio.run(middleware(scope, receive, send))

    statuses = [m.get("status") for m in sent if m["type"] == "http.response.start"]
    assert statuses == [413], f"yalnızca tek bir 413 çerçevesi beklenir, gelen: {statuses}"


def test_cancellation_is_never_swallowed():
    """CancelledError bir BaseException'dır: middleware onu da yutmamalı."""
    import asyncio

    async def cancelling_app(scope, receive, send):  # noqa: ARG001
        raise asyncio.CancelledError()

    middleware = BodySizeLimitMiddleware(cancelling_app, max_bytes=1024)
    scope = {"type": "http", "headers": []}

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):  # pragma: no cover
        raise AssertionError("iptal yutuldu")

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(middleware(scope, receive, send))


def test_healthy_route_is_unaffected_by_the_narrowed_handler(client):
    """Daraltılmış yakalayıcı normal akışı bozmaz (regresyon koruması)."""
    assert client.get("/health").status_code in (200, 503)
