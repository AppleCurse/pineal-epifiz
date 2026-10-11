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
COCKPIT = Path("frontend/src/components/AtlasPinealCockpit.svelte")

#: Ölçüm yokluğunun TEK metni — bileşendeki `INSUFFICIENT_EVIDENCE` ile aynı.
#: (Statik kontrat testi olduğu için burada dize olarak tekrarlanır.)
INSUFFICIENT_MARKER = "YETERSİZ KANIT"


def _panel() -> str:
    return PANEL.read_text(encoding="utf-8")


def _app() -> str:
    return APP.read_text(encoding="utf-8")


def _cockpit() -> str:
    return COCKPIT.read_text(encoding="utf-8")


def _strip_comments(text: str) -> str:
    """Yorum/blok dışı, gerçekten DERLENEN içerik.

    Zorunlu: bu deponun düzeltme yorumları, eski kusurlu kodu ibret olsun
    diye ALINTILIYOR (ör. `display: none`). Ham metin taranırsa test kendi
    açıklamasını kusur sayar.
    """
    stripped = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    stripped = re.sub(r"/\*.*?\*/", "", stripped, flags=re.S)
    return "\n".join(
        line for line in stripped.splitlines() if not line.lstrip().startswith("//")
    )


def _app_visible() -> str:
    return _strip_comments(_app())


def _cockpit_code() -> str:
    """Kokpit kaynağı, YORUMLAR AYIKLANMIŞ hâlde.

    Kaldırılanın neden kaldırıldığını anlatan açıklamalar "ölü kod" sayılmaz
    (`_code_lines` ile aynı gerekçe).
    """
    return "\n".join(_code_lines(_cockpit()))


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


# ─────────────────────────────────────────────────────────────────────────────
# [E6] ADLİ SÜTUN: ÖLÇÜM YOKLUĞU BİR DURUMDUR, DOLGU METNİ DEĞİL
#
# Bulunan açık (ölçüldü): AtlasPinealCockpit'in adli sütun modalları eksik
# alanları `|| 'Veri mevcut değil'` ve `?? 0` ile dolduruyordu. İkisi de AYNI
# yalanı söylüyordu — ölçüm yokken kart DOLU görünüyor, sayı alanında ise "0"
# gerçek bir ölçüm gibi okunuyordu (Md.1 uydurma yasağı).
# ─────────────────────────────────────────────────────────────────────────────


def test_cockpit_has_no_neutral_data_placeholder():
    """DoD: `grep -rn "'Veri mevcut değil'" frontend/src` → **0**."""
    offenders = [
        str(path)
        for path in Path("frontend/src").rglob("*.svelte")
        if "'Veri mevcut değil'" in path.read_text(encoding="utf-8")
    ]
    assert offenders == [], f"nötr dolgu metni geri geldi: {offenders}"


def test_cockpit_marks_insufficient_evidence_as_a_state():
    """Boş alan bir DURUM olarak işaretlenir: metin + uyarı stili + sebep."""
    code = _cockpit_code()
    assert INSUFFICIENT_MARKER in code, "YETERSİZ KANIT işareti yok"
    assert "evidence-insufficient" in code, "uyarı sınıfı kullanılmıyor"
    assert code.count("evidence-insufficient") >= 14, (
        "adli sütunların alanları işaretsiz kalmış: "
        f"{code.count('evidence-insufficient')} kullanım"
    )
    # İşaret sebebini SÖYLER: operatör "boş döndü" ile "ölçülmedi"yi ayırt eder.
    assert 'title="Alan boş döndü — ölçüm yok"' in code


def test_insufficient_evidence_has_a_visual_warning_style():
    """İşaret stil olarak da uyarır (görünmez metin dürüstlük sağlamaz)."""
    source = _cockpit()
    match = re.search(r"\.evidence-insufficient\s*\{([^}]*)\}", source)
    assert match, ".evidence-insufficient stili tanımsız"
    body = match.group(1)
    assert "color" in body and "#ef4444" in body, f"uyarı rengi yok: {body[:120]}"
    assert "border-bottom" in body, "işaret gövde metninden ayrışmıyor"


def test_cockpit_does_not_fabricate_zero_metrics():
    """Ölçüm yokken `0` gösterilmez: `0` GERÇEK ölçümdür (kayıp değil)."""
    code = _cockpit_code()
    for pattern in (
        "reality_index || 0",
        "compatibility_score ?? 0",
        "narcissism ?? 0",
        "night_share ?? 0",
        "data_completeness ?? 0",
        "follower_count ?? 0",
    ):
        assert pattern not in code, f"uydurma sıfır geri geldi: {pattern}"
    # Ve `0`'ın kayıp sayılmaması kuralı kodda YAZILI.
    assert "Number.isFinite" in code, "hasEvidence sayı kuralı kaybolmuş"
    assert "function hasEvidence(" in code


# ─────────────────────────────────────────────────────────────────────────
# [AUDIT 2026-10-07 · Madde 3] "12 özerk düğüm" iddiası
#
# Agent Rack başlığında "12 AUTONOMOUS NODES" yazıyordu: bu slotların her
# birinin BAĞIMSIZ bir işlemci olduğu iddiası. Gerçek: 12 slot,
# orkestratörün süreç içinde yürüttüğü 12 analiz ROLÜDÜR. Etiket
# "12 ANALYSIS ROLES" olarak düzeltildi; aşağıdaki testler hem etiketin
# dürüstlüğünü hem de frontend'deki rol listesinin backend ile
# BİRE-BİR aynı olduğunu kilitler (liste kopyası bayatlayamaz).
# ─────────────────────────────────────────────────────────────────────────

RACK = Path("frontend/src/components/AgentRack.svelte")


def _rack() -> str:
    return RACK.read_text(encoding="utf-8")


def _rack_visible() -> str:
    """Yorum/blok dışı, gerçekten DERLENEN içerik.

    Zorunlu: bu dosyanın kendi açıklama yorumları eski etiketi ("12
    AUTONOMOUS NODES") ibret olsun diye ALINTILIYOR. Ham metin taranırsa
    test kendi yorumunu kusur sanır. Bu yüzden HTML/JS yorumları ayıklanır.
    """
    return _strip_comments(_rack())


def test_rack_subtitle_does_not_claim_autonomous_nodes():
    """'AUTONOMOUS NODES': slotların bağımsız işlemci olduğu iddiası — kaldırıldı."""
    source = _rack_visible()
    assert "AUTONOMOUS NODES" not in source, (
        "Agent Rack hâlâ 'AUTONOMOUS NODES' diyor: bu slotlar bağımsız/otonom "
        "işlemci değil, orkestratörün yürüttüğü analiz rolleridir"
    )
    assert "12 ANALYSIS ROLES" in source, "dürüst '12 ANALYSIS ROLES' etiketi bulunamadı"


def test_rack_subtitle_explains_the_architecture():
    """Kullanıcı etikete geldiğinde gerçek mimariyi görmeli (title ipucu)."""
    source = _rack()
    assert "beacon-*" in source, "ipucu metni Docker beacon servislerini açıklamalı"
    assert "analiz yürütmez" in source.lower()


def test_frontend_slot_ids_match_backend_definitions_exactly():
    """Frontend'deki 12 rol listesi backend ile BİRE-BİR aynı olmalı.

    Frontend listesi backend'den KOPYALANMIŞ durumda; kopya bayatlarsa
    ekranda var olmayan bir rol görünür (ya da gerçek rol görünmez).
    Bu test o sapmayı yakalar.
    """
    from agent_core.services.agent_status_tracker import AGENT_DEFINITIONS

    backend_ids = [agent["id"] for agent in AGENT_DEFINITIONS]
    frontend_ids = re.findall(r"\{\s*id:\s*'([a-z0-9_]+)'", _rack())

    assert backend_ids, "backend ajan tanımı bulunamadı"
    assert len(set(frontend_ids)) == len(backend_ids), (
        f"rol sayısı uyuşmuyor: frontend {len(set(frontend_ids))} != backend {len(backend_ids)}"
    )
    assert set(frontend_ids) == set(backend_ids), (
        "frontend rol listesi backend'den sapmış: "
        f"yalnız frontend'de {sorted(set(frontend_ids) - set(backend_ids))}, "
        f"yalnız backend'de {sorted(set(backend_ids) - set(frontend_ids))}"
    )


# ─────────────────────────────────────────────────────────────────────────
# [AUDIT 2026-10-07 · Madde 6] Gözlemlenebilirlik: gizli telemetri panosu
#
# `App.svelte` içinde `NeuralTelemetryBoard` şu bloğun İÇİNDE basılıyordu::
#
#     <div style="display: none;" aria-hidden="true">
#       <NeuralTelemetryBoard telemetry={telemetryData} />
#     </div>
#
# Yani bileşen DOM'da vardı ama kullanıcı HİÇ GÖREMİYORDU: telemetri
# gözlemlenebilirliği fiilen sıfırdı ve "TELEMETRY OFFLINE" uyarısı da
# dahil hiçbir durum ekrana ulaşmıyordu. Pano artık görünür; kapatmak
# kullanıcının bilinçli seçimi.
# ─────────────────────────────────────────────────────────────────────────


def test_telemetry_board_is_not_hidden_in_display_none_dom():
    """[AUDIT] Pano `display: none` içinde basılıyordu — asla görünmüyordu."""
    visible = _app_visible()
    assert "NeuralTelemetryBoard" in visible, "telemetri panosu hiç basılmıyor"
    assert "display: none" not in visible, (
        "telemetri panosu hâlâ `display: none` ile gizleniyor: "
        "bileşen DOM'da var ama kullanıcı GÖREMİYOR (gözlemlenebilirlik sıfır)"
    )
    assert 'aria-hidden="true"' not in visible, (
        "telemetri panosu erişilebilirlik ağacından da gizlenmiş"
    )


def test_telemetry_board_is_visible_by_default_and_toggleable():
    """Varsayılan AÇIK olmalı ve kullanıcı kapatabilmeli (bilinçli seçim)."""
    source = _app()
    assert "telemetryVisible = true" in source, (
        "telemetri panosu varsayılan olarak kapalı: 'gizli kalsın' kusuru sürüyor"
    )
    # Gizlemek için BİR YOL olmalı, ama tek yol olmamalı.
    assert "telemetryVisible = !telemetryVisible" in source
    assert "aria-expanded" in source, "açma/kapama düğmesi erişilebilir işaret taşımalı"


def test_telemetry_board_still_receives_live_data():
    """Görünür panonun beslendiği veri yolu bozulmamalı (regresyon)."""
    source = _app()
    assert "telemetry={telemetryData}" in source
    assert "setInterval(fetchTelemetry" in source
