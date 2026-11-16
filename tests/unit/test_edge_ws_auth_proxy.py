"""Cloudflare edge → backend WebSocket KİMLİK akışı (P0-15 · D-01, 2026-11-11).

Ölçülen kusur:
    `functions/ws/[[path]].ts` içinde `upstream` hâlâ CONNECTING iken istemciye
    101 dönülüyordu ve pump `if (to.readyState !== WebSocket.OPEN) return;`
    yüzünden istemcinin İLK çerçevesini (`{type:"auth", token}`) SESSİZCE
    düşürüyordu. Sonuç: Cloudflare üzerinden gelen HER soket backend'de
    5 sn sonra 1008 ile kapanıyordu. Hata görünmüyordu — çünkü hiçbir yerde
    "çerçeve düştü" demiyordu.

Bu dosya iki şeyi ölçer:
    1. Worker kodu (Node 22 ile TS'i sıyrılarak) sahte Cloudflare ortamında
       koşar: erken gelen auth çerçevesi KAYBOLMAZ, sıra korunur, kuyruk
       tavanında sessiz düşürme yerine bağlantı kapanır.
    2. Backend tarafı: `/ws/{client_id}` ilk mesajdan token ister ve auth_ok'u
       YALNIZ doğruladıktan sonra gönderir (sözleşme burada kilitlenir).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
EDGE_PROBE = REPO_ROOT / "tests" / "edge" / "ws_proxy_auth.mjs"
WORKER = REPO_ROOT / "functions" / "ws" / "[[path]].ts"


def test_worker_still_reads_backend_origin_and_origin_allowlist():
    """Edge sözleşmesi: yapılandırma yoksa uydurma davranış YOK (502/403)."""
    source = WORKER.read_text(encoding="utf-8")
    assert "BACKEND_ORIGIN_NOT_CONFIGURED" in source
    assert "WS_ALLOWED_ORIGINS" in source
    assert "status: 426" in source, "upgrade olmayan istek 426 almalı"


def test_worker_buffers_frames_while_upstream_is_connecting():
    """Kaynak düzeyinde kilit: erken çerçeve tamponu ve tavanı KODDA var."""
    source = WORKER.read_text(encoding="utf-8")
    assert "WebSocket.CONNECTING" in source, (
        "CONNECTING durumu ele alınmıyor — ilk auth çerçevesi yine düşer"
    )
    assert "MAX_PENDING_FRAMES" in source and "MAX_PENDING_BYTES" in source, (
        "tampon tavanı yok: sınırsız kuyruk bellek şişmesi demek"
    )
    assert "1013" in source, "tavan aşımı sessiz düşürme değil, açık kapanış olmalı"


def _node_supports_strip_types() -> tuple[bool, str]:
    """Node 22.6+ TS'i sıyırabilir. Daha eskisinde bayrak yoktur (ölçülür).

    Bu kontrol YOKKEN test CI'da sessizce yanlış nedene düşebiliyordu:
    bayrak desteklenmiyorsa Node 9 ile çıkar ve "edge kırık" gibi görünür.
    Artık yetenek ÖLÇÜLÜR: destek yoksa test SKIP olur (yanlış alarm yok,
    ama destek varsa davranış gerçekten ölçülür).
    """
    node = shutil.which("node")
    if node is None:
        return False, "node yok"
    try:
        probe = subprocess.run(
            [node, "--experimental-strip-types", "-e", "const x: number = 1;"],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover
        return False, f"node çalıştırılamadı: {type(exc).__name__}"
    if probe.returncode != 0:
        return False, "node --experimental-strip-types desteklenmiyor (Node < 22.6?)"
    return True, ""


_STRIP_OK, _STRIP_REASON = _node_supports_strip_types()


@pytest.mark.skipif(not _STRIP_OK, reason=_STRIP_REASON or "node yok")
def test_edge_proxy_forwards_early_auth_frame_to_upstream():
    """DAVRANIŞ ÖLÇÜMÜ: Worker gerçekten koşar, auth çerçevesi upstream'e varır."""
    result = subprocess.run(
        ["node", "--experimental-strip-types", str(EDGE_PROBE)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )
    output = result.stdout + result.stderr
    assert "EDGE_OK" in output, f"edge ölçümü başarısız:\n{output}"
    # Senaryo adları görünür olsun: hangi sözleşme ölçüldü, rapor edilebilir.
    assert "PASS erken gelen auth çerçevesi upstream açılınca iletilir" in output
    assert "PASS birden çok erken çerçeve SIRAYLA iletilir" in output
    assert "PASS kuyruk tavanı aşılırsa iki uç da kapatılır (sessiz düşürme yok)" in output
    assert "PASS upstream açılmadan kapanırsa istemci de kapatılır" in output, (
        "asılı bağlantı senaryosu çalışmadı"
    )


def test_backend_requires_first_message_auth_within_timeout():
    """Backend sözleşmesi: token İLK mesajla gelir, sır URL'ye yazılmaz."""
    source = (REPO_ROOT / "backend" / "routes" / "websocket.py").read_text(encoding="utf-8")
    assert "WS_AUTH_TIMEOUT_S" in source
    assert 'auth_message.get("type") != "auth"' in source
    assert "token_matches(presented)" in source, "token doğrulanmadan auth_ok verilmemeli"
    # auth_ok sahiplik kontrolünden SONRA gönderilir.
    auth_ok_index = source.index('"auth_ok"')
    acquire_index = source.index("_acquire_room(")
    assert acquire_index < auth_ok_index, "auth_ok sahiplikten ÖNCE gönderiliyor"


def test_frontend_sends_auth_as_first_frame():
    """İstemci tarafı: ilk çerçeve auth olmalı (edge tamponu buna göre kuruldu)."""
    app = (REPO_ROOT / "frontend" / "src" / "App.svelte").read_text(encoding="utf-8")
    on_open = app.index("ws.onopen")
    auth_send = app.index("type: 'auth'", on_open)
    # `ws.send(` çağrısının kendisi auth'u taşıyan satır OLMALI.
    # onopen gövdesindeki İLK `ws.send(` çağrısı auth'u taşıyan çağrı olmalı
    # (token değişkeni aynı satırda kuruluyor: `const token = ...`).
    first_send = app.index("if (token && ws) ws.send(", on_open)
    # İLK gönderimin gövdesi (satır sonuna kadar) auth'u taşımalı.
    line_end = app.index("\n", first_send)
    first_send_line = app[first_send:line_end]
    assert "type: 'auth'" in first_send_line, (
        f"onopen içindeki İLK gönderim auth değil: {first_send_line!r}"
    )
    assert "JSON.stringify({ type: 'auth', token })" in app, (
        "auth çerçevesinin şekli değişmiş: edge tamponu ve backend ayrışır"
    )
