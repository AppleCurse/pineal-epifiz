"""Dil uçlarının TAŞIMA sözleşmesi — hız sınırı · kasa mandalı · hata gövdeleri.

[2026-10-14 DENETİM BULGUSU] ``backend/routes/language.py`` modül açıklaması
"her üç uç da ``language:{client_id}`` kovasını paylaşır" diyordu; ama
``GET /api/language/status`` hiç ``rate_limit`` çağırmıyordu — yazılanla koşan
ayrışmıştı. Sözleşme koda uyduruldu ve burada BEHAVİOR olarak kilitlendi.

Kilitlenen iddialar
-------------------
1. **Paylaşılan kova:** ``status`` · ``detect`` · ``translate`` aynı kovayı
   (``language:{client_id}``) kullanır. Kanıt: bir uçta kovayı tüketmek
   diğerlerini 429'a düşürür (ayrı kova olsaydı düşmezdi).
2. **Limit aşımı 429 + tek biçim:** üçü de ``{"error": {"code": "RATE_LIMITED"}}``
   gövdesini ve 429 durum kodunu döner.
3. **Kasa mandalı:** ``detect``/``translate`` kasa kilitliyken KOŞMAZ
   (``denied_by == "vault"``, üretilen çıktı yok).
4. **``status`` kasadan bağımsız okuma raporudur:** kilitliyken de çalışır —
   bu bir istisna değil, modül sözleşmesinin parçasıdır (gizli davranış yok).
5. **Gövde sözleşmesi:** bozuk/eksik payload 422 döner (Pydantic sınırları).

Test yöntemi: her senaryo KENDİ ``client_id``'sini kullanır; kovalar süreç
genelinde tutulduğu için testler birbirinin hız bütçesini yemez.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend import api

TR_TEXT = (
    "Merhaba, bugün hava çok güzel ve ben dışarı çıkmak istiyorum. "
    "Ama önce işlerimi bitirmem gerekiyor çünkü yarın için hazırlık yapmalıyım."
)

# Kova sınırı backend/api.py → RATE_LIMITS["language"] = (60, 60).
# Test, limiti SABİT SAYMAZ: gerçek sınırı ölçer (aşağıda tavana kadar dener).
DENEME_TAVANI = 80


@pytest.fixture()
def client():
    with TestClient(api.app) as test_client:
        yield test_client


def _kova_tuket(client: TestClient, yol: str, client_id: str, *, adet: int = 1) -> list[int]:
    """``yol`` ucuna ``adet`` istek atar, DURUM KODLARINI döner (ölçüm, tahmin değil)."""
    kodlar = []
    for _ in range(adet):
        kodlar.append(client.get(f"{yol}?client_id={client_id}").status_code)
    return kodlar


def _limit_asilana_kadar(client: TestClient, yol: str, client_id: str) -> list[int]:
    """Kova tükenene kadar ister; ilk 429'dan sonra durur. Kod dizisini döner."""
    kodlar = []
    for _ in range(DENEME_TAVANI):
        kod = client.get(f"{yol}?client_id={client_id}").status_code
        kodlar.append(kod)
        if kod == 429:
            break
    return kodlar


class TestSharedBucket:
    """Sözleşme: üç uç AYNI kovayı paylaşır (modül docstring'i)."""

    def test_status_now_honours_the_shared_bucket(self, client):
        """[BULGU 1'İN KANITI] status kendi kovasını kullansaydı hiç 429 vermezdi."""
        kodlar = _limit_asilana_kadar(client, "/api/language/status", "lsp-ts-status")
        assert 200 in kodlar, f"ilk durum isteği geçmeliydi: {kodlar[:3]}"
        assert kodlar[-1] == 429, (
            f"status {len(kodlar)} istekten sonra 429 vermedi — kova uygulanmıyor: {kodlar[-5:]}"
        )
        # Limit, gerçek RATE_LIMITS değerinden gelir (elle yazılmış sayı değil).
        limit = api.RATE_LIMITS["language"][0]
        assert len(kodlar) == limit + 1, (
            f"429 {len(kodlar)}. istekte geldi; RATE_LIMITS['language'] limiti {limit}"
        )

    def test_status_spending_consumes_detect_and_translate_budget(self, client, monkeypatch):
        """Kova PAYLAŞILDIĞI için: status ile tüket → detect/translate 429."""
        monkeypatch.setenv("ENABLE_LOCAL_TRANSLATE", "true")
        monkeypatch.setenv("PINEAL_TRANSLATE_URL", "http://127.0.0.1:1/t")
        cid = "lsp-ts-paylasim"
        kodlar = _limit_asilana_kadar(client, "/api/language/status", cid)
        assert kodlar[-1] == 429, "kova tükenmedi"

        detect = client.post("/api/language/detect", json={"text": TR_TEXT, "client_id": cid})
        translate = client.post(
            "/api/language/translate", json={"text": TR_TEXT, "target": "en", "client_id": cid}
        )
        assert detect.status_code == 429, (
            "detect 429 almadı: kova paylaşılmıyor demektir (sözleşme ihlali)"
        )
        assert translate.status_code == 429, "translate 429 almadı: kova paylaşılmıyor"
        for resp in (detect, translate):
            assert resp.json()["error"]["code"] == "RATE_LIMITED"

    def test_detect_spending_consumes_status_budget(self, client):
        """Tersi yön: detect ile tüketilen bütçe status'u da 429'a düşürür."""
        cid = "lsp-ts-ters"
        kodlar = []
        for _ in range(DENEME_TAVANI):
            kod = client.post(
                "/api/language/detect", json={"text": TR_TEXT, "client_id": cid}
            ).status_code
            kodlar.append(kod)
            if kod == 429:
                break
        assert kodlar[-1] == 429, f"detect kovası tükenmedi: {kodlar[-5:]}"
        assert client.get(f"/api/language/status?client_id={cid}").status_code == 429

    def test_other_client_has_its_own_budget(self, client):
        """Kova ANAHTARI client_id'dir: bir istemcinin tükenmesi diğerini etkilemez."""
        cid = "lsp-ts-dolu"
        _limit_asilana_kadar(client, "/api/language/status", cid)
        assert client.get(f"/api/language/status?client_id={cid}").status_code == 429
        taze = client.get("/api/language/status?client_id=lsp-ts-bos")
        assert taze.status_code == 200, "farklı istemcinin bütçesi ayrı olmalı"


class TestRateLimitBody:
    """429 gövdesi üç uçta AYNI biçimde olmalı (istemci tek yerde işler)."""

    @pytest.mark.parametrize("uc", ["status", "detect", "translate"])
    def test_rate_limited_body_shape(self, client, monkeypatch, uc):
        monkeypatch.setenv("ENABLE_LOCAL_TRANSLATE", "true")
        monkeypatch.setenv("PINEAL_TRANSLATE_URL", "http://127.0.0.1:1/t")
        cid = f"lsp-ts-govde-{uc}"
        _limit_asilana_kadar(client, "/api/language/status", cid)
        if uc == "status":
            resp = client.get(f"/api/language/status?client_id={cid}")
        elif uc == "detect":
            resp = client.post("/api/language/detect", json={"text": TR_TEXT, "client_id": cid})
        else:
            resp = client.post(
                "/api/language/translate", json={"text": TR_TEXT, "target": "en", "client_id": cid}
            )
        assert resp.status_code == 429
        govde = resp.json()
        assert set(govde) == {"error"}, f"429 gövdesi tek 'error' anahtarı taşımalı: {govde}"
        assert govde["error"]["code"] == "RATE_LIMITED"
        assert isinstance(govde["error"]["message"], str) and govde["error"]["message"]


class TestVaultInterlock:
    """Tüzük Md.4: kasa kilitliyken dış dünyaya çıkan yetenek koşmaz."""

    def test_detect_denied_when_vault_locked(self, client):
        cid = "lsp-ts-kasa-detect"
        assert not api._check_vault_interlock(cid), "test odası kilitli başlamalı"
        payload = client.post(
            "/api/language/detect", json={"text": TR_TEXT, "client_id": cid}
        ).json()
        assert payload["denied_by"] == "vault"
        assert payload["language"] == "" and payload["confidence"] == 0.0

    def test_translate_denied_when_vault_locked(self, client, monkeypatch):
        monkeypatch.setenv("ENABLE_LOCAL_TRANSLATE", "true")
        monkeypatch.setenv("PINEAL_TRANSLATE_URL", "http://127.0.0.1:1/t")
        cid = "lsp-ts-kasa-translate"
        payload = client.post(
            "/api/language/translate", json={"text": TR_TEXT, "target": "en", "client_id": cid}
        ).json()
        assert payload["denied_by"] == "vault"
        assert payload["text"] == "", "kasa kilitliyken çeviri metni ÜRETİLMEZ"

    def test_status_is_a_read_only_report_not_vault_gated(self, client):
        """Sözleşme: status yalnız okuma raporudur; kilitliyken de çalışır.

        Bu, 'gizli istisna' değil AÇIK sözleşmedir (modül docstring'i yazar);
        test onu kilitler ki sessizce değişmesin.
        """
        cid = "lsp-ts-kasa-status"
        assert not api._check_vault_interlock(cid)
        resp = client.get(f"/api/language/status?client_id={cid}")
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["detect"] == {"available": True, "method": "deterministic_local"}
        assert "translate" in payload and "last" in payload


class TestCapabilityUnavailable:
    """Yetenek yoksa DÜRÜST sonuç: uydurma çıktı yok, sebep var."""

    def test_translate_reports_unavailable_with_reason_not_fake_text(self, client, monkeypatch):
        monkeypatch.delenv("ENABLE_LOCAL_TRANSLATE", raising=False)
        monkeypatch.delenv("PINEAL_TRANSLATE_URL", raising=False)
        monkeypatch.setenv("PINEAL_TRANSLATE_CMD", "pineal-olmayan-komut")
        cid = "lsp-ts-yetenek-yok"
        client.get(f"/api/telemetry?client_id={cid}")
        api.get_room(cid)["vault"]["or_key"] = True   # kasa açık → ret SEBEBİ yetenek olmalı
        resp = client.post(
            "/api/language/translate", json={"text": TR_TEXT, "target": "en", "client_id": cid}
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["available"] is False
        assert payload["text"] == ""
        assert payload["denied_by"] or payload["reason"], "sebep gizlenemez"

    def test_translate_remote_endpoint_refused_reason_is_machine_readable(self, client, monkeypatch):
        """Kasa AÇIK olsa bile uzak uç reddedilir: sebep makine-okunur olmalı."""
        monkeypatch.setenv("ENABLE_LOCAL_TRANSLATE", "true")
        monkeypatch.setenv("PINEAL_TRANSLATE_URL", "https://uzak.example.com/t")
        cid = "lsp-ts-uzak"
        client.get(f"/api/telemetry?client_id={cid}")
        api.get_room(cid)["vault"]["or_key"] = True   # kasa açık → ret SEBEBİ uzak uç olmalı
        payload = client.post(
            "/api/language/translate", json={"text": TR_TEXT, "target": "en", "client_id": cid}
        ).json()
        assert payload["available"] is False
        assert payload["denied_by"] is None, "kasa açıkken kasa reddi raporlanmamalı"
        assert payload["reason"] == "non_local_endpoint"
        assert payload["text"] == ""


class TestPayloadContract:
    """Gövde sözleşmesi: bozuk/eksik payload 200 DÖNMEZ."""

    @pytest.mark.parametrize(
        "govde",
        [
            {"text": ""},                                    # min_length=1
            {"text": "   " * 1, "client_id": "x" * 200},      # client_id max_length=128
        ],
    )
    def test_detect_rejects_invalid_payload(self, client, govde):
        resp = client.post("/api/language/detect", json=govde)
        assert resp.status_code in (400, 422), f"bozuk gövde kabul edildi: {resp.status_code}"
        assert "detail" in resp.json()

    def test_invalid_client_id_fails_closed_without_running_capability(self, client):
        """ÖLÇÜLEN DAVRANIŞ: geçersiz `client_id` (boşluk içerir) 422 değil
        FAIL-CLOSED üretir — `_check_vault_interlock` kimliği çözemeyince
        "dar taraf = kilitli" kararı verir (backend/api.py:3379).

        Bu, güvenlik sözleşmesidir: kimliği doğrulanamayan istemci için yetenek
        KOŞMAZ; yanıt yine de 200 gövdesinde `denied_by=vault` ile gelir ve
        üretilmiş dil çıktısı taşımaz.
        """
        cid = "geçersiz-boşluk var"
        payload = client.post(
            "/api/language/detect", json={"text": TR_TEXT, "client_id": cid}
        ).json()
        assert payload["denied_by"] == "vault"
        assert payload["reason"] == "policy:vault_locked"
        assert payload["language"] == "" and payload["confidence"] == 0.0

    def test_detect_rejects_oversized_text(self, client):
        resp = client.post("/api/language/detect", json={"text": "a" * 20001, "client_id": "lsp"})
        assert resp.status_code == 422

    def test_translate_rejects_oversized_text(self, client):
        resp = client.post(
            "/api/language/translate",
            json={"text": "a" * 2001, "target": "en", "client_id": "lsp"},
        )
        assert resp.status_code == 422

    @pytest.mark.parametrize("hedef", ["", "e", "ingilizce-cok-uzun-hedef"])
    def test_translate_rejects_bad_target_language(self, client, hedef):
        resp = client.post(
            "/api/language/translate",
            json={"text": TR_TEXT, "target": hedef, "client_id": "lsp"},
        )
        assert resp.status_code == 422, f"geçersiz hedef dil kabul edildi: {hedef!r}"
