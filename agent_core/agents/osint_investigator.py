"""SOTA OSINT katmanı — kullanıcı adı, e-posta ve açık kaynak izleri.

Gerçek taramaları YETENEK OMURGASI (``agent_core.capabilities``) üzerinden
koşar; her çağrının çıktısı kanıt zaman çizelgesine mühürlenir. Faz 2 Maigret
kullanıcı-adı taraması, Faz 3 Holehe e-posta kayıt taraması görev payload'ının
politika durumuna göre "dürüstçe birleştirilir" — yetenek kapalıysa uydurma
bulgu üretilmez, kaynak-kullanılamaz sinyali yazılır.

Kasa (vault) kilitliyken dış çağrı yapılmaz; politika tek kaynaktan
(``capabilities.state``) okunur.

Test: ``tests/unit/test_osint_*.py``, ``tests/unit/test_maigret_scanner.py``,
``tests/unit/test_holehe_scanner.py``.
"""

import logging
import asyncio
import dataclasses
import aiohttp
import os
from typing import Dict, Any, Optional
from pydantic import BaseModel, ConfigDict, Field
from agent_core.services.llm_gateway import LLMGateway

logger = logging.getLogger(__name__)

class OsintProfile(BaseModel):
    connected_emails: list[str] = []
    connected_phones: list[str] = []
    associated_platforms: list[str] = []
    digital_footprint_score: float = 0.0  # 0.0 (hayalet) - 1.0 (çok aktif)
    dark_web_hits: int = 0
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    data_confidence: bool = False
    fallback_reason: Optional[str] = "unavailable"
    error_code: Optional[str] = None

    model_config = ConfigDict(extra="allow")

class OsintInvestigatorAgent:
    """
    SOTA (State of the Art) OSINT katmanı.
    osint.industries / SpiderFoot API'leri üzerinden hedefin kullanıcı adını
    kullanarak dijital ayak izini (e-posta, telefon, diğer platformlar) çıkarır.
    """

    def __init__(self, llm_gateway: Optional[LLMGateway] = None):
        self.llm_gateway = llm_gateway or LLMGateway()
        # osint.industries API key vault'tan veya env'den alınabilir.
        self.osint_api_key = os.getenv("OSINT_INDUSTRIES_KEY", None)

    # ---------------------------------------------------------------- omurga
    @staticmethod
    def _policy_state(payload: Dict[str, Any] | None = None):
        """Görev payload'ından capability politika durumu (tek kaynak: state.py).

        Kasa interlock'u API sınırında uygulanır (`/api/initiate` → 423); ajan
        içinde bilinmiyorsa dar taraf seçilir: `vault_locked=True` (hiçbir
        dış yetenek koşmaz). Payload'da `policy` varsa o değerler geçerlidir.

        [ÇOCUK KİLİDİ — API girişi] `policy.minor_case` de aynı yerden taşınır:
        operatör bir hedefi çocuk olarak beyan ettiyse o beyan kapıda
        REDDEDİLMEDİYSE bile omurga onu GÖRÜR ve koşucu kendi katmanında ikinci
        kez uygular (kuşak kuşak savunma; beyan kaybolursa kilit gevşemez,
        çünkü çeviri `coerce_minor_case` ile fail-closed yapılır).
        """
        from agent_core.capabilities.state import policy_state
        from agent_core.safety import coerce_minor_case

        overrides = (payload or {}).get("policy") or {}
        state = policy_state(
            vault_locked=bool(overrides.get("vault_locked", True)),
            rate_ok=overrides.get("rate_ok"),
            minor_case=coerce_minor_case(overrides.get("minor_case")),
        )
        # [2026-10-23 · ONAY KABLOSU] Operatör `/api/scraper/authorize-alternative`
        # ile çapraz aramaya AÇIKÇA onay verdiyse bu görev için
        # `ENABLE_CROSS_PLATFORM` kapısı açılır. Onay aksi hâlde hiçbir şeyi
        # değiştirmez (varsayılan hâlâ KAPALI) — yetki env'den gelmez, oda
        # kaydından gelir ve yalnız o görevi kapsar.
        if overrides.get("cross_platform_authorized"):
            state = dataclasses.replace(
                state,
                enabled_flags={**dict(state.enabled_flags), "ENABLE_CROSS_PLATFORM": True},
            )
        return state

    @staticmethod
    async def _run_spine(
        capability_id: str,
        subject: str,
        payload: Dict[str, Any] | None = None,
        params: Dict[str, Any] | None = None,
    ):
        """Yeteneği OMURGADAN koşar + çıktısını kanıt zaman çizelgesine mühürler.

        Dönen ikili: ``(CapabilityResult, EvidenceTimeline)``. Böylece maigret/
        holehe bulgusu artık yalnız bir profile dict'i değil, MÜHÜRLÜ kanıttır;
        çocuk kilidi, kasa ve env kapıları otomatik uygulanır (Faz A · Retina).
        """
        from agent_core.capabilities import (
            CapabilityContext,
            bootstrap,
            run_capability,
        )
        from agent_core.capabilities.timeline_bridge import seal_results

        bootstrap()
        result = await run_capability(
            capability_id,
            CapabilityContext(subject=subject, params=params or {}),
            state=OsintInvestigatorAgent._policy_state(payload),
        )
        return result, seal_results([result])

    async def _apply_username_scan(self, profile: OsintProfile, clean_username: str, payload: Dict[str, Any] | None = None) -> OsintProfile:
        """[FAZ 2] Maigret kullanıcı-adı taramasını dürüstçe birleştirir.

        - Kapı (ENABLE_MAIGRET) kapalıysa / tarama kullanılamıyorsa: profil
          alanları DEĞİŞMEZ; yalnız kanıt-provenance olarak `username_scan`
          alanı eklenir (makine-okunur sebep ile).
        - Tarama güvenilir tamamlandıysa: gözlenen platformlar gerçek veri
          olarak girer; güven = gözlenen kapsama VE mevcut güvenin altına
          inmez (başka kaynağın gözlemini ezmez — holehe ile aynı monoton
          kural; bkz. `_apply_email_scan`).
        - Güvenilir yokluk (sıfır hata + sıfır eşleşme): data_confidence=True
          kalır; hiç gözlem yoksa skor dürüstçe sıfır + sebep
          'username_scan_no_match', başka kaynak gözlemi varsa mevcut
          değerler korunur (başka taramanın kanıtını ezmez).

        [FAZ A] Tarama artık doğrudan servise değil, CAPABILITY OMURGASINA
        gider (`sensor.identity.maigret`): kasa/env kapıları, çocuk kilidi ve
        timeout aynı yerden uygulanır; çıktı `EvidenceTimeline`'a mühürlenir
        (`username_scan_evidence`). Profil alanlarının anlamı DEĞİŞMEZ.
        """
        from agent_core.services.maigret_scanner import MaigretScanResult

        try:
            result, timeline = await self._run_spine(
                "sensor.identity.maigret", clean_username, payload
            )
        except Exception as exc:  # tarama asıl OSINT sonucunu asla bozmasın
            logger.warning("maigret scan skipped: %s: %s", type(exc).__name__, str(exc)[:80])
            return profile

        scan = result.payload if isinstance(result.payload, MaigretScanResult) else None
        if scan is None:
            # Kapı/kasa/çocuk kilidi reddi: sebep korunur, site UYDURULMAZ.
            scan = MaigretScanResult(
                requested_username=clean_username,
                available=False,
                reason=(result.unavailable_reason or "unavailable"),
            )
        sealed = {
            "username_scan_evidence": timeline.model_dump(mode="json"),
            "username_scan_sealed": len(timeline.entries),
        }

        if scan.available and scan.found_sites:
            merged = sorted({*profile.associated_platforms, *(h.site for h in scan.found_sites)})
            coverage = (len(scan.found_sites) / scan.scanned_count) if scan.scanned_count else 0.0
            # Güven monoton: gözlenen kapsama MEVCUT güvenin altına inmez —
            # sağlayıcı ya da başka taramanın gözlemini ezmez (holehe ile aynı
            # kural; bkz. `_apply_email_scan`). Uydurma skor yok.
            confidence = max(profile.confidence, round(coverage, 3))
            return profile.model_copy(update={
                "associated_platforms": merged,
                "data_confidence": True,
                "confidence": confidence,
                "fallback_reason": None if not profile.fallback_reason else profile.fallback_reason,
                "username_scan": scan.model_dump(),
                **sealed,
            })
        if scan.available and scan.scanned_count and scan.error_count == 0:
            # Güvenilir yokluk: yalnız HİÇ gözlem yoksa skor sıfırlanır ve
            # sebep yazılır; başka kaynağın gözlemi varsa değerleri ezilmez.
            no_platforms = not profile.associated_platforms
            return profile.model_copy(update={
                "data_confidence": True,
                "confidence": 0.0 if no_platforms else profile.confidence,
                "fallback_reason": "username_scan_no_match" if no_platforms else profile.fallback_reason,
                "username_scan": scan.model_dump(),
                **sealed,
            })
        return profile.model_copy(update={"username_scan": scan.model_dump(), **sealed})

    async def _apply_cross_platform_probe(
        self,
        profile: OsintProfile,
        clean_username: str,
        payload: Dict[str, Any] | None = None,
    ) -> OsintProfile:
        """[2026-10-23] Native çapraz platform yoklaması — X/IG/FB/Threads...

        Neden: kullanıcı adı çapraz araması yalnız ``ENABLE_MAIGRET`` kapısına
        bağlıydı; maigret varsayılan KAPALI olduğu için "X'te bulunan hedef
        Instagram'da / Facebook'ta / Threads'te aransın" beklentisi pratikte
        hiç koşmuyordu. Bu adım ``sensor.identity.handle_probe`` yeteneğini
        dener; kapı kapalıysa ALANLAR DEĞİŞMEZ, yalnız makine-okunur sebep
        mühürlenir (sessiz yutma yok).

        Birleştirme kuralları (maigret ile aynı monoton kural):
          * Bulunan platformlar ``associated_platforms``'a EKLENİR (silinmez).
          * Güven mevcut değerin altına İNMEZ.
          * "Hiçbir yerde yok" iddiası yalnız ``absence_claimable`` ise yazılır;
            aksi hâlde yalnız gözlem kaydı düşülür.
        """
        try:
            result, timeline = await self._run_spine(
                "sensor.identity.handle_probe", clean_username, payload
            )
        except Exception as exc:  # yoklama asıl OSINT sonucunu asla bozmasın
            logger.warning("handle_probe skipped: %s: %s", type(exc).__name__, str(exc)[:80])
            return profile

        probe = getattr(result, "payload", None)
        scan = probe.to_username_scan() if hasattr(probe, "to_username_scan") else None
        if scan is None:
            scan = {
                "requested_username": clean_username,
                "available": False,
                "provider": "handle_probe",
                "reason": result.unavailable_reason or "unavailable",
                "found_sites": [],
            }
        sealed = {
            "handle_probe_evidence": timeline.model_dump(mode="json"),
            "handle_probe_sealed": len(timeline.entries),
        }
        updates: Dict[str, Any] = {"handle_probe": scan, **sealed}

        if scan.get("available") and scan.get("found_sites"):
            platforms = {str(site.get("site", "")).strip() for site in scan["found_sites"]}
            platforms.discard("")
            merged = sorted({*profile.associated_platforms, *platforms})
            coverage = len(platforms) / max(1, int(scan.get("scanned_count") or 1))
            updates.update({
                "associated_platforms": merged,
                "data_confidence": True,
                "confidence": max(profile.confidence, round(min(coverage, 1.0), 3)),
            })
        elif scan.get("available") and scan.get("absence_claimable"):
            # Kanıtlanabilir yokluk: yalnız hiç gözlem yoksa skor sıfırlanır.
            if not profile.associated_platforms:
                updates.update({
                    "data_confidence": True,
                    "confidence": 0.0,
                    "fallback_reason": "cross_platform_probe_no_match",
                })
        return profile.model_copy(update=updates)

    async def _apply_email_scan(self, profile: OsintProfile, email: str, payload: Dict[str, Any] | None = None) -> OsintProfile:
        """[FAZ 3] Holehe e-posta kayıt taramasını dürüstçe birleştirir.

        - Kapı (ENABLE_HOLEHE) kapalıysa / tarama kullanılamıyorsa: profil
          alanları DEĞİŞMEZ; yalnız provenance olarak `email_scan` alanı
          eklenir (makine-okunur sebep ile).
        - Eşleşme varsa: gözlenen siteler gerçek veri olarak
          `associated_platforms`'a girer; güven = gözlenen kapsama ve MEVCUT
          güvenin ALTINA inmez (başka kaynağın bulduğu platformları silmez).
        - Güvenilir yokluk (sıfır hata + sıfır eşleşme): yalnız hâlâ tek
          gözlem yoksa confidence 0.0 + 'email_scan_no_match'; aksi halde
          mevcut değerler korunur (başka taramanın kanıtını ezmez).
        """
        # [FAZ A] holehe de omurgadan koşar (sensor.identity.holehe) ve çıktısı
        # mühürlü kanıt olur; kapı/kasa reddi sebep olarak korunur.
        from agent_core.services.holehe_scanner import HoleheScanResult

        try:
            result, timeline = await self._run_spine(
                "sensor.identity.holehe", email, payload
            )
        except Exception as exc:  # tarama asıl OSINT sonucunu asla bozmasın
            logger.warning("holehe scan skipped: %s: %s", type(exc).__name__, str(exc)[:80])
            return profile

        scan = result.payload if isinstance(result.payload, HoleheScanResult) else None
        if scan is None:
            scan = HoleheScanResult(
                requested_email=email,
                available=False,
                reason=(result.unavailable_reason or "unavailable"),
            )
        sealed = {
            "email_scan_evidence": timeline.model_dump(mode="json"),
            "email_scan_sealed": len(timeline.entries),
        }

        if scan.available and scan.found_sites:
            merged = sorted({*profile.associated_platforms, *(h.site for h in scan.found_sites)})
            coverage = (len(scan.found_sites) / scan.scanned_count) if scan.scanned_count else 0.0
            confidence = max(profile.confidence, round(coverage, 3))
            return profile.model_copy(update={
                "associated_platforms": merged,
                "data_confidence": True,
                "confidence": confidence,
                "email_scan": scan.model_dump(),
                **sealed,
            })
        if scan.available and scan.scanned_count and scan.error_count == 0:
            no_platforms = not profile.associated_platforms
            return profile.model_copy(update={
                "data_confidence": True,
                "confidence": 0.0 if no_platforms else profile.confidence,
                "fallback_reason": "email_scan_no_match" if no_platforms else profile.fallback_reason,
                "email_scan": scan.model_dump(),
                **sealed,
            })
        # [P4 · 2026-10-16] Kapı/kasa reddi de MÜHÜRLÜ kanıt olarak korunur
        # (maigret ile simetri): reddedilen tarama da zincirde görünür.
        return profile.model_copy(update={"email_scan": scan.model_dump(), **sealed})

    @staticmethod
    def _no_target_email_seal() -> Dict[str, Any]:
        """[FAZ 3] E-posta yokken Holehe ÇALIŞMAZ; dürüst `not_run` kaydı yazılır.

        "E-posta bulunmadığında Holehe'yi çağrılmış gibi göstermek" yasak:
        `email_scan` alanı taramanın gerçek durumunu taşır
        (`available=False, reason="no_target_email"`) ve kanal durumu
        çevirisinde `not_run` + sebep olur.
        """
        return {
            "requested_email": "",
            "available": False,
            "provider": "holehe",
            "reason": "no_target_email",
            "found_sites": [],
            "scanned_count": 0,
            "error_count": 0,
        }

    async def _continue_independent_sensors(
        self,
        profile: OsintProfile,
        clean_username: str,
        payload: Dict[str, Any] | None,
        candidate_emails: list[str] | None = None,
    ) -> OsintProfile:
        """[PR #136 · KABLO] Bağımsız sensörleri (Maigret → Holehe) dürüstçe birleştirir.

        Sağlayıcı çıktısı — ya da sağlayıcı hatası — PIPELINE'IN SONU DEĞİLDİR:
        bir API anahtarının varlığı (ya da o anahtarın hata vermesi) Maigret/
        Holehe'yi sessizce devre dışı bırakamaz. Bu yardımcı TÜM sağlayıcı
        yollarından (anahtar yok / 200 / HTTP hatası / timeout / ağ hatası)
        çağrılır; böylece tek uygulama, tek koşum yolu olur.

        - Maigret her zaman denenir (kapı/kasa reddinde yalnız `not_run`
          provenance'ı mühürlenir; alanlar değişmez).
        - Holehe YALNIZ gerçek bir e-posta girdisi varsa koşar; yoksa
          `no_target_email` ile dürüst `not_run` kaydı yazılır.
        """
        profile = await self._apply_username_scan(profile, clean_username, payload)
        # [2026-10-23] Maigret'ten BAĞIMSIZ ikinci yol: kapı (ENABLE_CROSS_PLATFORM)
        # açıksa kullanıcı adı bilinen platformlarda gerçekten yoklanır.
        profile = await self._apply_cross_platform_probe(profile, clean_username, payload)
        if profile.connected_emails:
            return await self._apply_email_scan(profile, profile.connected_emails[0], payload)
        if candidate_emails:
            # [P1 · KABLO BAĞLANTISI] Sağlayıcı e-posta döndürmese bile hedef
            # profilinde/biyografisinde/arama snippet'inde gerçek bir e-posta
            # varsa Holehe onunla koşar.
            return await self._apply_email_scan(profile, candidate_emails[0], payload)
        return profile.model_copy(update={"email_scan": self._no_target_email_seal()})

    def _get_alf_headers(self) -> Dict[str, str]:
        import random
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0"
        ]
        headers = {
            "User-Agent": random.choice(user_agents),
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
            "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "cross-site",
        }
        if self.osint_api_key:
            headers["api-key"] = self.osint_api_key
        return headers

    @staticmethod
    def _extract_candidate_emails(target: dict[str, Any], payload: dict[str, Any]) -> list[str]:
        """Hedef profil, biyografi veya arama snippet'lerinden e-posta adaylarını çıkarır."""
        import re
        from agent_core.services.holehe_scanner import sanitize_email

        candidates: list[str] = []

        def _add(raw: Any):
            if isinstance(raw, str):
                s = sanitize_email(raw)
                if s and s not in candidates:
                    candidates.append(s)

        # 1. target.connected_emails
        raw_conn = target.get("connected_emails")
        if isinstance(raw_conn, (list, tuple, set)):
            for e in raw_conn:
                _add(e)
        elif isinstance(raw_conn, str):
            _add(raw_conn)

        # 2. target.email
        _add(target.get("email"))

        # 3. target.bio
        bio = str(target.get("bio") or "")
        if bio:
            for match in re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", bio):
                _add(match)

        # 4. payload.search_snippets / target.search_snippets
        snippets = payload.get("search_snippets") or target.get("search_snippets") or []
        if isinstance(snippets, list):
            for snip in snippets:
                text = snip.get("text", "") if isinstance(snip, dict) else str(snip)
                if text:
                    for match in re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text):
                        _add(match)

        return candidates

    async def execute(self, payload: Dict[str, Any]) -> OsintProfile:
        payload = payload if isinstance(payload, dict) else {}
        raw_target = payload.get("target_profile")
        target = raw_target if isinstance(raw_target, dict) else {}

        raw_username = target.get("username", "")
        username = raw_username.strip() if isinstance(raw_username, str) else ""

        if not username:
            return OsintProfile(
                confidence=0.0,
                data_confidence=False,
                fallback_reason="no_target_identity",
                error_code="NO_TARGET_IDENTITY",
            )

        clean_username = username.lstrip("@")
        candidate_emails = self._extract_candidate_emails(target, payload)

        # [011] Gerçek API anahtarı yoksa MOCK veri dönülmez: dürüst boş
        # fallback döner (confidence=0.0, data_confidence=False). Sahte
        # e-posta/telefon/oturum üretmek yasak.
        if not self.osint_api_key:
            logger.info(f"[OSINT] API anahtarı bulunamadı, '{clean_username}' için analiz atlanıyor.")
            # Return empty/unknown state due to lack of API key, avoiding LLM hallucinations.
            profile = OsintProfile(
                connected_emails=candidate_emails,
                connected_phones=[],
                associated_platforms=[],
                digital_footprint_score=0.0,
                dark_web_hits=0,
                confidence=0.0,
                data_confidence=False,
                fallback_reason="provider_credentials_unavailable",
            )
            # [FAZ 2/3 + PR #136] ENABLE_MAIGRET / ENABLE_HOLEHE kapalıysa
            # profil alanları değişmez; kapı açıksa yalnız gerçek gözlemler
            # dürüstçe birleştirilir. E-posta yoksa dürüst 'no_target_email'
            # gerekçesi mühürlenir (sessizce kaybolmaz).
            return await self._continue_independent_sensors(
                profile, clean_username, payload, candidate_emails
            )
        else:
            # [E-GÖZ2-3 · YAPRAK] aiohttp yolu da kasa kapısından geçer:
            # kilitliyken istek HİÇ OLUŞTURULMAZ, dürüst vault_locked profili
            # döner (ağ istisnası gibi sönümlenmez).
            from agent_core.scraper.vault_gate import (
                VaultLockedError as _VaultLockedError,
                require_open as _require_open,
            )

            try:
                _require_open(purpose="osint")
            except _VaultLockedError:
                logger.warning(
                    "[OSINT] KASA KİLİTLİ: canlı API isteği oluşturulmadı "
                    "(amaç=osint; kullanıcı/anahtar kaydedilmedi)"
                )
                return OsintProfile(
                    connected_emails=[],
                    connected_phones=[],
                    associated_platforms=[],
                    digital_footprint_score=0.0,
                    dark_web_hits=0,
                    confidence=0.0,
                    data_confidence=False,
                    fallback_reason="vault_locked",
                    error_code="VAULT_LOCKED",
                )
            try:
                async with aiohttp.ClientSession() as session:
                    headers = self._get_alf_headers()
                    async with session.get(f"https://api.osint.industries/v1/user/{clean_username}", headers=headers, timeout=15) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            emails = data.get("emails", [])
                            phones = data.get("phones", [])
                            platforms = data.get("platforms", [])
                            observed_fields = sum(bool(value) for value in (emails, phones, platforms))
                            # [PR #136] Sağlayıcı çıktısı kaynaklardan biridir,
                            # pipeline'ın SONU değildir: başarılı API yanıtı
                            # Maigret/Holehe'yi sessizce devre dışı bırakmaz.
                            profile = OsintProfile(
                                connected_emails=emails,
                                connected_phones=phones,
                                associated_platforms=platforms,
                                # Coverage, not an invented provider-trust score.
                                confidence=round(observed_fields / 3, 3),
                                # Sağlayıcı 200 + BOŞ gözlem "veri güveni" DEĞİLDİR:
                                # tarama kapsamı bilinmediği için güvenilir yokluk
                                # iddia edilemez (bkz. `_apply_*` güvenilir yokluk
                                # ölçütü: tamamlanmış + hatasız tarama).
                                data_confidence=bool(observed_fields),
                                fallback_reason=None if observed_fields else "provider_returned_no_observations",
                            )
                            return await self._continue_independent_sensors(
                                profile, clean_username, payload, candidate_emails
                            )
                        logger.warning(f"[OSINT] Canlı API hatası: HTTP {resp.status} - {await resp.text()}")
                        error_code = "AUTH_FAILED" if resp.status in (401, 403) else "RATE_LIMITED" if resp.status == 429 else "PROVIDER_ERROR"
                        # [PR #136] HTTP hata yolu da sensörleri ATLAZ: erken
                        # return, yapılandırılmış anahtarı olan her görevde
                        # Maigret/Holehe'yi görünmez kılardı. Sağlayıcı hatası
                        # `fallback_reason="api_error"` + `error_code` ile AÇIK
                        # kalır; bağımsız sensörler yine koşar (koşullu ve
                        # güvenli: kapı/kasa/çocuk kilidi omurgadan uygulanır).
                        return await self._continue_independent_sensors(
                            OsintProfile(
                                connected_emails=candidate_emails,
                                confidence=0.0,
                                data_confidence=False,
                                fallback_reason="api_error",
                                error_code=error_code,
                            ),
                            clean_username,
                            payload,
                            candidate_emails,
                        )
            except asyncio.TimeoutError as e:
                logger.warning(f"[OSINT] Canlı API timeout: {e}")
                return await self._continue_independent_sensors(
                    OsintProfile(
                        connected_emails=candidate_emails,
                        confidence=0.0,
                        data_confidence=False,
                        fallback_reason="api_error",
                        error_code="TIMEOUT",
                    ),
                    clean_username,
                    payload,
                    candidate_emails,
                )
            except Exception as e:
                logger.warning(f"[OSINT] Canlı API bağlantı hatası: {e}")
                return await self._continue_independent_sensors(
                    OsintProfile(
                        connected_emails=candidate_emails,
                        confidence=0.0,
                        data_confidence=False,
                        fallback_reason="api_error",
                        error_code="NETWORK_ERROR",
                    ),
                    clean_username,
                    payload,
                    candidate_emails,
                )
