"""UX dil sözleşmesi — operatörün gördüğü metinler teknik jargon taşımaz.

`UX_Kullanılabilirlik_Raporu.md` 4 madde yazdı; bu dosya o maddelerin
karşılığını kilitler. Kural: insani cümle ÖNE çıkar, teknik neden GİZLENMEZ
(etiketli korunur). Arka plan sözleşmeleri (backend `source` anahtarları,
kilitli `REDIS PUB/SUB` / `in_memory` etiketleri) bu değişikliklerin dışındadır
ve `test_status_source_honesty.py` tarafından ayrıca kilitlenir.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AGENT_RACK = ROOT / "frontend" / "src" / "components" / "AgentRack.svelte"
WAR_ROOM = ROOT / "frontend" / "src" / "components" / "TacticalWarRoom.svelte"
COMPACT = ROOT / "frontend" / "src" / "components" / "UnifiedCompactPanel.svelte"


def test_agent_rack_source_labels_use_operator_language():
    """UX-1: taşıyıcı etiketlerinde 'TRACKER' jargonu yok, operatör dili var."""
    source = AGENT_RACK.read_text(encoding="utf-8")
    labels = source[source.index("SOURCE_LABELS") : source.index("$: busLabel")]
    # Açıklama yorumları eski etiketi ibret olsun diye ALINTILAR; ölçülen DERLENEN
    # satırlardır (yorumlar ayıklanır — test kendi belgesini kusur sanmamalı).
    labels_code = "\n".join(
        ln for ln in labels.splitlines() if not ln.strip().startswith("//")
    )
    assert "TRACKER" not in labels_code, "iç modül adı (tracker) kullanıcı etiketinde"
    assert "BAĞLANTI KOPTU" in labels_code
    # Backend sözleşmesi korunur: anahtar adı değişemez, yalnız görünen metin çevrilir.
    assert "fallback: 'BAĞLANTI KOPTU'" in labels_code
    # Slot rozetiyle alt toplam aynı dili konuşur (HATA/HATA, değil HATA/ERROR).
    assert '<span class="stat-label">HATA</span>' in source


def test_war_room_launch_failure_is_visible_and_guiding():
    """UX-2: görev başlatma arızası sessiz değil; Türkçe + çözüm önerisi ekranda."""
    source = WAR_ROOM.read_text(encoding="utf-8")
    guidance = "Görev başlatılamadı, internet bağlantınızı kontrol edip tekrar deneyin."
    assert guidance in source, "yönlendirici Türkçe mesaj kaybolmuş"
    assert 'role="alert"' in source, "arıza bandı erişilebilirlik rolü taşımalı"
    assert "launchError" in source
    # Konsol kaydı durur (teşhis için) ama TEK kanal olamaz: ekranda bant da var.
    assert "console.error('Sistem Görevi Başlatamadı:'" in source
    assert "{#if launchError}" in source


def test_compact_panel_vault_rejection_is_a_visible_alert():
    """UX-3: kasa reddi loga gömülü değil; ekranda `role=\"alert\"` uyarı."""
    source = COMPACT.read_text(encoding="utf-8")
    assert "KASA KİLİTLİ. Analiz için kasayı açmalısınız." in source
    assert "{#if vaultNotice}" in source
    assert '<div class="vault-alert" role="alert">' in source
    # Log kaydı da durur (izlenebilirlik): iki kanal birbirini dışlamaz.
    assert "ATEŞLEME REDDEDİLDİ" in source


def test_war_room_keeps_the_technical_cause_under_a_label():
    """UX-4: ham neden insan diline çevrilir ama GİZLENMEZ (TEKNİK AYRINTI)."""
    source = WAR_ROOM.read_text(encoding="utf-8")
    human = "Sistem bu hedef için yeterli veri bulamadığı için araştırmayı güvenli şekilde durdurdu."
    assert human in source, "insani durma cümlesi kaybolmuş"
    assert "TEKNİK AYRINTI:" in source
    assert "{run.error_message}" in source, "ham teknik neden şablondan düşmüş"
    # Kart satırı ham metni taşımaz; ayrıntı röntgen panelindedir.
    assert "DURDU: yeterli veri bulunamadığı için güvenli şekilde durduruldu" in source
