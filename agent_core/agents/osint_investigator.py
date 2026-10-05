import logging
import asyncio
import aiohttp
import os
from typing import Dict, Any, Optional
from pydantic import BaseModel, ConfigDict
from agent_core.services.llm_gateway import LLMGateway

logger = logging.getLogger(__name__)

class OsintProfile(BaseModel):
    connected_emails: list[str] = []
    connected_phones: list[str] = []
    associated_platforms: list[str] = []
    digital_footprint_score: float = 0.0  # 0.0 (hayalet) - 1.0 (çok aktif)
    dark_web_hits: int = 0
    confidence: float = 1.0
    data_confidence: bool = True          # False → LLM kullanılamadı veya API yoktu
    fallback_reason: Optional[str] = None
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
        """
        from agent_core.capabilities.state import policy_state

        overrides = (payload or {}).get("policy") or {}
        return policy_state(
            vault_locked=bool(overrides.get("vault_locked", True)),
            rate_ok=overrides.get("rate_ok"),
        )

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
          olarak girer; güven = gözlenen kapsama (uydurma skor yok).
        - Güvenilir yokluk (sıfır hata + sıfır eşleşme): data_confidence=True
          kalır, düşük skor dürüstçe sıfır; sebep 'username_scan_no_match'.

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
            return profile.model_copy(update={
                "associated_platforms": merged,
                "data_confidence": True,
                "confidence": round(coverage, 3),
                "fallback_reason": None if not profile.fallback_reason else profile.fallback_reason,
                "username_scan": scan.model_dump(),
                **sealed,
            })
        if scan.available and scan.scanned_count and scan.error_count == 0:
            return profile.model_copy(update={
                "data_confidence": True,
                "confidence": 0.0,
                "fallback_reason": "username_scan_no_match",
                "username_scan": scan.model_dump(),
                **sealed,
            })
        return profile.model_copy(update={"username_scan": scan.model_dump(), **sealed})

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
        return profile.model_copy(update={"email_scan": scan.model_dump()})

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

    async def execute(self, payload: Dict[str, Any]) -> OsintProfile:
        target = payload.get("target_profile", {})
        username = target.get("username", "")

        if not username:
            return OsintProfile(
                confidence=0.0,
                data_confidence=False,
                fallback_reason="no_target_identity",
                error_code="NO_TARGET_IDENTITY",
            )

        clean_username = username.lstrip("@")
        
        # [011] Gerçek API anahtarı yoksa MOCK veri dönülmez: dürüst boş
        # fallback döner (confidence=0.0, data_confidence=False). Sahte
        # e-posta/telefon/oturum üretmek yasak.
        if not self.osint_api_key:
            logger.info(f"[OSINT] API anahtarı bulunamadı, '{clean_username}' için analiz atlanıyor.")
            # Return empty/unknown state due to lack of API key, avoiding LLM hallucinations.
            profile = OsintProfile(
                connected_emails=[],
                connected_phones=[],
                associated_platforms=[],
                digital_footprint_score=0.0,
                dark_web_hits=0,
                confidence=0.0,
                data_confidence=False,
                fallback_reason="provider_credentials_unavailable",
            )
            # [FAZ 2] ENABLE_MAIGRET kapalıysa profil alanları değişmez; kapı
            # açıksa yalnız gerçek gözlemler dürüstçe birleştirilir.
            profile = await self._apply_username_scan(profile, clean_username, payload)
            # [FAZ 3] Bağlı e-posta varsa holehe kayıt taraması (ENABLE_HOLEHE
            # kapalıysa profil alanları yine değişmez; yalnız provenance eklenir).
            if profile.connected_emails:
                profile = await self._apply_email_scan(
                    profile, profile.connected_emails[0], payload
                )
            return profile
        else:
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
                            return OsintProfile(
                                connected_emails=emails,
                                connected_phones=phones,
                                associated_platforms=platforms,
                                # Coverage, not an invented provider-trust score.
                                confidence=round(observed_fields / 3, 3),
                                data_confidence=True,
                            )
                        logger.warning(f"[OSINT] Canlı API hatası: HTTP {resp.status} - {await resp.text()}")
                        error_code = "AUTH_FAILED" if resp.status in (401, 403) else "RATE_LIMITED" if resp.status == 429 else "PROVIDER_ERROR"
                        return OsintProfile(confidence=0.0, data_confidence=False, fallback_reason="api_error", error_code=error_code)
            except asyncio.TimeoutError as e:
                logger.warning(f"[OSINT] Canlı API timeout: {e}")
                return OsintProfile(confidence=0.0, data_confidence=False, fallback_reason="api_error", error_code="TIMEOUT")
            except Exception as e:
                logger.warning(f"[OSINT] Canlı API bağlantı hatası: {e}")
                return OsintProfile(confidence=0.0, data_confidence=False, fallback_reason="api_error", error_code="NETWORK_ERROR")
