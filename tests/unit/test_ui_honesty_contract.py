"""[BOSS-10 + BOSS-12] Arayüz dürüstlüğü sözleşmesi.

Röntgen bulguları (ölçüldü):
  B10 — UnifiedCompactPanel: `runs['depth_forensics']` ÖLÜ anahtar (backend
        'depth_analyst' yazar); başarısız derinlik/görsel/gölge/OSINT modalları
        "Kanıtlar incelendi / Fotoğraf analiz edildi / Doğal profil / Temiz"
        gibi UYDURMA başarı metinleri basıyordu; ASPASIA sohbeti 4 kurgu
        mesajla (Aegean shell entities senaryosu) açılıyordu.
  B12 — App.svelte: `telemetryEvents` hiç render edilmiyordu, NeuralTelemetryBoard
        import edilip basılmıyordu, fetchTelemetry/fetchTasks/deleteTask ölüydü,
        hata çerçevesi "OPERASYON TAMAMLANDI" diye INFO yazılıyordu.

Bu testler kaynak metni taramaz-yok-saymaz; davranışın kaynakta var olduğunu
kilitler (frontend test altyapısı olmadığı için statik kontrat).
"""

from __future__ import annotations

import re
from pathlib import Path

PANEL = Path("frontend/src/components/UnifiedCompactPanel.svelte")
APP = Path("frontend/src/App.svelte")


def _panel() -> str:
    return PANEL.read_text(encoding="utf-8")


def _app() -> str:
    return APP.read_text(encoding="utf-8")


def _code_lines(source: str) -> list[str]:
    """Yorum satırlarını atar: kaldırılanın NEDEN kaldırıldığını anlatan
    açıklamalar 'ölü kod' sayılmamalı."""
    return [line for line in source.splitlines() if not line.strip().startswith(("//", "<!--", "*"))]


def test_dead_run_key_is_gone():
    """`depth_forensics` anahtarını backend yazmıyor: fallback ölüydü."""
    source = _panel()
    assert "runs['depth_forensics']" not in source
    assert "runs[agent.id]" in source


def test_failure_states_are_not_rendered_as_success():
    """Başarısız üretim, uydurma başarı metniyle bastırılamaz."""
    source = _panel()
    for fake in ("'Kanıtlar incelendi.'", "'Fotoğraf analiz edildi.'", "'Klasik'", "'Doğal profil'", "'Temiz'"):
        assert fake not in source, f"uydurma başarı metni hâlâ ekranda: {fake}"
    # Hata hâli açıkça etiketlenmeli.
    assert "ÜRETİLEMEDİ" in source
    assert "GÖRSEL ANALİZ YOK" in source
    assert "GÖLGE KATMANI VERİSİZ" in source
    assert "OSINT VERİSİ YOK" in source
    assert "veri yok" in source


def test_aspasia_chat_does_not_open_with_fabricated_scenario():
    source = _panel()
    for fake in ("Aegean shell", "AIS spoofing", "Risk score: 0.78", "Cyprus → Luxembourg"):
        assert fake not in source, f"kurgu sohbet içeriği: {fake}"
    # Başlangıç boş; tek sistem satırı ne yapılacağını söyler.
    assert "ASPASIA hazır" in source
    assert re.search(r"let messages:[^=]*= \[\s*\n\s*\{ sender: 'SİSTEM'", source)


def test_app_renders_telemetry_board_and_feeds_it():
    """Import edilip basılmayan pano = ölü parça; artık gerçek veriyle basılır."""
    source = _app()
    assert "<NeuralTelemetryBoard" in source, "pano hâlâ render edilmiyor"
    assert "telemetry={telemetryData}" in source
    assert "fetchTelemetry()" in source
    assert "setInterval(fetchTelemetry" in source, "canlı besleme yok → pano kurgu moduna düşer"


def test_dead_fetch_polling_and_unbounded_event_store_are_gone():
    code = "\n".join(_code_lines(_app()))
    for dead in ("telemetryEvents", "fetchTasks", "deleteTask", "tasksData"):
        assert dead not in code, f"ölü UI parçası duruyor: {dead}"


def test_error_frames_are_not_logged_as_completed():
    source = _app()
    assert "OPERASYON TAMAMLANDI" not in source
    assert "OPERASYON SONUÇLANDI" in source
    # Terminal olmayan durumlar ERROR seviyesinde yazılmalı.
    assert '["completed", "partially_completed"]' in source
