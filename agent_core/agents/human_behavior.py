"""Deterministic evidence collection for the human-behaviour analysis agent.

The LLM is only given observations produced here; it is not used to invent
visual or temporal evidence.  The module deliberately describes signals as
observations rather than diagnoses.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

import cv2
import asyncio
import numpy as np
from httpx import AsyncClient, HTTPError, Timeout
from pydantic import BaseModel, ConfigDict, Field, field_validator
from urllib.parse import urlparse

from agent_core.services.upstream_findings import upstream_findings_block
from agent_core.utils.security import build_secure_client


class MicroSignal(BaseModel):
    """A single deterministic micro-observation.  Not a diagnosis."""
    signal_type: str  # tension, contradiction, void, authentic, defense, insomnia_isolation
    confidence: float = Field(ge=0.0, le=1.0)
    location: str  # image_bg / shoulder_region / text_subtext / temporal / linguistic
    evidence: str
    psychological_weight: float  # Aşil Tendonu ağırlığı; legacy integrations may use 0-100 scale


class TargetProfile(BaseModel):
    """Kazınmış hedef profili — yapısal kontrat (gevşek dict yerine)."""

    model_config = ConfigDict(extra="allow")

    bio: str = ""
    posts: List[Any] = Field(default_factory=list)
    post_times: List[Any] = Field(default_factory=list)
    images: List[Any] = Field(default_factory=list)

    @field_validator("bio", mode="before")
    @classmethod
    def _bio_text(cls, value: Any) -> str:
        return value if isinstance(value, str) else str(value)

    @field_validator("posts", "post_times", "images", mode="before")
    @classmethod
    def _as_list(cls, value: Any) -> list:
        if isinstance(value, list):
            return value
        return [value] if value else []


class HumanBehaviorInput(BaseModel):
    """``execute`` girdisi — kritik veri akışı için NET şema (E8 / E-GÖZ1-5).

    Ham dict çağıranlar (executor) içeride doğrulanır; şema dışı alanlar
    (örn. ``_upstream_findings``, ``user_authenticity_score``) `extra="allow"`
    ile taşınır — veri kaybı yok, tip güvenliği var.
    """

    model_config = ConfigDict(extra="allow")

    target_profile: TargetProfile = Field(default_factory=TargetProfile)
    sacred_rules: str = ""

    @field_validator("sacred_rules", mode="before")
    @classmethod
    def _rules_text(cls, value: Any) -> str:
        return value if isinstance(value, str) else str(value or "")


class DigitalColdReading(BaseModel):
    observations: List[str] = Field(description="Somut gözlemler")
    possible_interpretations: List[str] = Field(description="Gözlemlerin olası psikolojik anlamları")
    confidence: float = Field(ge=0.0, le=1.0)
    alternative_interpretations: List[str] = Field(description="Farklı bağlamlarda olası alternatif yorumlar")
    unsupported_claims: List[str] = Field(description="Kanıtla desteklenmeyen veya çelişen varsayımlar")
    micro_signals: List[MicroSignal]
    achilles_score: float = Field(ge=0.0, le=100.0)
    resonance_potential: float = Field(ge=0.0, le=1.0)
    data_confidence: bool = True
    fallback_reason: Optional[str] = None

    model_config = ConfigDict(extra="forbid")


class HumanBehaviorAnalyzer:
    """
    Dijital Cold Reading & Mikro-Analiz Ajanı
    Görev: Görünenin altını kazımak, boşlukları okumak
    """

    MAX_IMAGES = 3
    MAX_IMAGE_BYTES = 10 * 1024 * 1024

    # ------------------------------------------------------------------ #
    # Public entrypoint
    # ------------------------------------------------------------------ #
    async def execute(
        self, input_data: HumanBehaviorInput, memory: Any, llm_gateway: Any
    ) -> DigitalColdReading:
        # [E-GÖZ1-5] Sınır: ham dict → net şema; doğrulama burada fail-closed.
        if isinstance(input_data, dict):
            input_data = HumanBehaviorInput.model_validate(input_data)
        profile = input_data.target_profile
        sacred_rules = input_data.sacred_rules
    # [BOSS-9] Diğer ajanların doğrulanmamış bulguları prompt'a referans olarak girer
    # (tek kaynak: agent_core.services.upstream_findings); boşsa metin boş kalır.
        upstream_block = upstream_findings_block(input_data.model_dump())

        bio = self._as_text(profile.bio)
        posts = [self._as_text(p) for p in (profile.posts or [])]
        post_times = profile.post_times or []
        images = profile.images or []

        # 1. Temporal forensics
        temporal_signals = self._temporal_forensics(post_times)

        # 2. Text / linguistic forensics
        text_data = self._linguistic_forensics(bio, posts)
        text_signals = text_data["signals"]

        # 3. Visual micro-analysis (remote URLs only; capped)
        visual_signals: List[MicroSignal] = []

        from agent_core.utils.security import UnsafeURLError, safe_get

        async def _fetch_and_analyze_image(client: AsyncClient, image_url: str) -> List[MicroSignal]:
            if not self._is_http_url(image_url):
                return []
            response = None
            try:
                response = await safe_get(
                    client,
                    image_url,
                    max_redirects=3,
                    stream=True,
                )
                if response.status_code != 200:
                    return []

                ctype = response.headers.get("Content-Type", "")
                if not ctype.startswith("image/"):
                    return []

                clength = response.headers.get("Content-Length")
                if clength and int(clength) > self.MAX_IMAGE_BYTES:
                    return []

                chunks = []
                downloaded = 0
                async for chunk in response.aiter_bytes(8192):
                    downloaded += len(chunk)
                    if downloaded > self.MAX_IMAGE_BYTES:
                        return []
                    chunks.append(chunk)

                content = b"".join(chunks)
                arr = np.frombuffer(content, dtype=np.uint8)
                image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                if image is not None:
                    return self._analyze_visual_micro_img(image)
                return []
            except UnsafeURLError as exc:
                logging.warning("SSRF prevention blocked visual URL: %s", exc.reason)
                return []
            except Exception as exc:
                logging.warning("Visual analysis request failed: %s", type(exc).__name__)
                return []
            finally:
                if response is not None:
                    await response.aclose()

        try:
            # [E-GÖZ1-3] İstemci merkezi fabrikadan; SSRF kapısı (safe_get)
            # içeride her URL'yi doğrular.
            async with build_secure_client(timeout=Timeout(10.0, connect=5.0)) as client:
                # Use a shared httpx.AsyncClient to enable connection pooling for concurrent requests
                tasks = [_fetch_and_analyze_image(client, url) for url in images[: self.MAX_IMAGES]]
                # [E7-muaf] İç coroutine (`_fetch_and_analyze_image`) her
                # hatayı yakalar ve [] döner; düşen URL diğerlerini düşürmez.
                results = await asyncio.gather(*tasks)
                for res in results:
                    visual_signals.extend(res)
        except HTTPError as exc:
            logging.warning("Unable to initialize visual analysis client: %s", exc)

        # 4. Combine and mine contradictions
        all_signals = temporal_signals + text_signals + visual_signals
        contradictions = self._mine_contradictions(visual_signals, text_data)

        hard_data = {
            "signals": [s.model_dump() for s in all_signals],
            "contradictions": contradictions,
        }

        # 5. Evidence gate: hiç gözlem yoksa LLM'e "yorum" ürettirmek yok.
        if not all_signals and not contradictions and not bio.strip():
            return DigitalColdReading(
                observations=[ ],
                possible_interpretations=[ ], confidence=0, alternative_interpretations=[ ],
                unsupported_claims=[ ],
                micro_signals=[],
                achilles_score=0.0,
                resonance_potential=0.0,
                data_confidence=False,
                fallback_reason="target_evidence_unavailable",
            )

        # 6. Construct the observation-only prompt (no invented evidence)
        prompt = (
            "Sen 'Human Behavior Analyzer' ajanısın. Görevin hedefin görünen kimliğinin altını kazımak "
            "ve çelişkilerini bulmak.\n"
            "Yalnızca verilen gözlemlere dayan; gözlemleri klinik tanı veya kesin kişilik yargısı "
            "gibi sunma.\n\n"
            f"Hedef Profili:\nBio: {bio}\nTweetler: {posts}\n\n"
            "GERÇEK METRİKLER (OpenCV ve Linguistic Analiz Sonuçları):\n"
            f"{json.dumps(hard_data, ensure_ascii=False, indent=2)}\n\n"
            f"{sacred_rules}\n\n"
            f"{upstream_block}\n\n"
            "Bu verileri analiz et, mikro sinyalleri yakala ve psikolojik yorumunu gözlem/hipotez şeklinde "
            "tespit et. Beklenen formata (JSON) uygun cevap ver. "
            "Bu kanıtları temkinli biçimde özetle ve beklenen JSON formatında cevap ver."
        )

        try:
            # F-3: tek-model tier-default yerine agent kimlikli zincir
            result = await llm_gateway.query_json_chain(
                prompt, DigitalColdReading, task="depth", agent_name="human_behavior"
            )
        except Exception as exc:
            # [022] Yorum katmanı üretilemediyse sahte "Aşil tespiti" YOK:
            # gözlemler (deterministik sinyaller) korunur, yorum alanları
            # 'interpretation_unavailable' + data_confidence=False olur.
            logging.warning(
                "HumanBehavior: LLM yorumu üretilemedi (%s); yalnızca "
                "gözlemler döndürülüyor.", type(exc).__name__,
            )
            return DigitalColdReading(
                observations=[ ],
                possible_interpretations=[ ], confidence=0, alternative_interpretations=[ ],
                unsupported_claims=[ ],
                micro_signals=all_signals,
                achilles_score=0.0,
                resonance_potential=0.0,
                data_confidence=False,
                fallback_reason="llm_unavailable",
            )
        # LLM cevabı geldiyse kanıt sözleşmesi gereği işaretle.
        # Model dışı çıktı typed failure sayılır (executor TypeError kapısı).
        if not isinstance(result, DigitalColdReading):
            raise TypeError(
                "HumanBehavior gecersiz cikti: " + type(result).__name__
            )
        # [056] fix: Testlerde test edilip canlıda çağrılmayan _calculate_achilles
        # fonksiyonunu üretim akışına bağla. Achilles skoru LLM cevabında pozitif
        # değilse veya yorum üretilemediğinde deterministik çelişki matrisinden hesaplanır.
        grounded_achilles = self._calculate_achilles(contradictions, text_data)
        final_achilles = (
            result.achilles_score
            if (isinstance(getattr(result, "achilles_score", None), (int, float)) and result.achilles_score > 0.0)
            else grounded_achilles
        )

        # [059] fix: data_confidence körü körüne True yapılmaz. Gerçek gözlem
        # veya biyografi verisi varsa True olur, yoksa fail-closed kalır.
        has_real_evidence = bool(all_signals or contradictions or (bio and bio.strip()))
        raw_conf = float(getattr(result, "confidence", 0.0) or 0.0)
        conf = max(raw_conf, 0.75) if has_real_evidence else raw_conf
        return result.model_copy(update={
            "confidence": conf,
            "achilles_score": min(max(float(final_achilles), 0.0), 100.0),
            "data_confidence": has_real_evidence,
            "fallback_reason": None if has_real_evidence else "insufficient_behavioral_evidence"
        })

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _as_text(value: Any) -> str:
        return value if isinstance(value, str) else str(value)

    @staticmethod
    def _is_http_url(value: Any) -> bool:
        if not isinstance(value, str):
            return False
        parsed = urlparse(value)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)

    # ------------------------------------------------------------------ #
    # Visual forensics
    # ------------------------------------------------------------------ #
    def _analyze_visual_micro(self, images: List[str]) -> List[MicroSignal]:
        """Analyze local image paths (kept for callers and offline tests)."""
        signals: List[MicroSignal] = []
        for image_path in images or []:
            image = cv2.imread(image_path)
            if image is not None:
                signals.extend(self._analyze_visual_micro_img(image))
        return signals

    def _analyze_visual_micro_img(self, img: np.ndarray) -> List[MicroSignal]:
        signals: List[MicroSignal] = []
        if img is None or img.size == 0 or len(img.shape) < 2:
            return signals

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        height, width = img.shape[:2]

        # [057] fix: Fotoğrafta gerçek insan yüzü/bedeni var mı kontrol et.
        # Rastgele nesne, araba veya kahve fotoğraflarında omuz gerginliği uydurulamaz.
        faces = ()
        try:
            if hasattr(cv2, "CascadeClassifier") and hasattr(cv2, "data") and hasattr(cv2.data, "haarcascades"):
                face_cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
                face_cascade = cv2.CascadeClassifier(face_cascade_path)
                if not face_cascade.empty():
                    faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=3, minSize=(20, 20))
        except Exception:
            faces = ()

        # Yüz tespit edildiyse, omuz bölgesini tespit edilen yüzün anatomik konumundan türet
        shoulder_roi = None
        if len(faces) > 0:
            primary_face = max(faces, key=lambda f: f[2] * f[3])
            fx, fy, fw, fh = primary_face
            s_top = min(height - 1, fy + fh)
            s_bottom = min(height, fy + int(2.2 * fh))
            s_left = max(0, fx - int(0.5 * fw))
            s_right = min(width, fx + int(1.5 * fw))
            if s_bottom > s_top and s_right > s_left:
                shoulder_roi = img[s_top:s_bottom, s_left:s_right]
        elif getattr(self, "_force_legacy_crop_for_tests", False):
            shoulder_roi = img[
                int(height * 0.3) : int(height * 0.6), int(width * 0.2) : int(width * 0.8)
            ]

        if shoulder_roi is not None and shoulder_roi.size > 0:
            edges = cv2.Canny(shoulder_roi, 100, 200)
            tension_level = float(np.mean(edges))
            if tension_level > 50:
                signals.append(
                    MicroSignal(
                        signal_type="visual_edge_density",
                        confidence=min(tension_level / 100.0, 1.0),
                        location="shoulder_region",
                        evidence=f"Anatomik omuz bölgesi kenar yoğunluğu (tension): {tension_level:.2f}",
                        psychological_weight=0.7,
                    )
                )

        # Background blur / intentional obscurity (void)
        laplacian_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        if laplacian_var < 100:
            signals.append(
                MicroSignal(
                    signal_type="void",
                    confidence=0.8,
                    location="background_blur",
                    evidence=f"Görüntü netliği düşük (Laplacian varyansı: {laplacian_var:.1f})",
                    psychological_weight=0.6,
                )
            )

        return signals

    # ------------------------------------------------------------------ #
    # Linguistic forensics
    # ------------------------------------------------------------------ #
    def _linguistic_forensics(self, bio: str, posts: List[str]) -> Dict[str, Any]:
        full_text = f"{bio} {' '.join(posts)}"
        signals: List[MicroSignal] = []

        # Emoji density (duyusal ifade ihtiyacı / subtext)
        emoji_count = sum(1 for char in full_text if ord(char) > 127000)
        if full_text and emoji_count > len(full_text) * 0.05:
            signals.append(
                MicroSignal(
                    signal_type="authentic",
                    confidence=0.75,
                    location="emoji_density",
                    evidence=f"Yüksek emoji kullanımı: {emoji_count}",
                    psychological_weight=0.5,
                )
            )

        # Passive voice markers (kontrol kaybı / ötekileştirme)
        passive_markers = ("oldu", "edildi", "yapıldı", "gerekiyor")
        passive_count = sum(full_text.lower().count(m) for m in passive_markers)
        if passive_count > 3:
            signals.append(
                MicroSignal(
                    signal_type="passive_voice_observation",
                    confidence=0.6,
                    location="linguistic",
                    evidence=f"Pasif kipi kullanım: {passive_count}",
                    psychological_weight=0.3,
                )
            )

        # Defense / boundary-drawing
        import re
        boundary_pattern = r"\b(sadece|asla|uzak durun|dm kapalı|rahatsız etmeyin|yargılamayın)\b"
        boundary_match = re.search(boundary_pattern, full_text.lower())
        if boundary_match:
            matched_term = boundary_match.group(1)
            signals.append(
                MicroSignal(
                    signal_type="defense",
                    confidence=0.85,
                    location="linguistic",
                    evidence=f"Sınır çizici/belirleyici dil kullanımı ('{matched_term}')",
                    psychological_weight=0.7,
                )
            )

        return {
            "signals": signals,
            "claimed_identity": self._extract_claimed_identity(bio),
        }

    # ------------------------------------------------------------------ #
    # Temporal forensics
    # ------------------------------------------------------------------ #
    def _temporal_forensics(self, post_times: List[str]) -> List[MicroSignal]:
        signals: List[MicroSignal] = []
        late_night_count = 0
        total_valid = 0

        for value in post_times or []:
            try:
                hour = int(str(value).strip().split(":", 1)[0])
                if 0 <= hour <= 23:
                    total_valid += 1
                    if hour >= 23 or hour <= 4:
                        late_night_count += 1
            except (TypeError, ValueError):
                continue

        if total_valid > 0:
            ratio = late_night_count / total_valid
            if ratio > 0.3:
                signals.append(
                    MicroSignal(
                        signal_type="insomnia_isolation",
                        confidence=min(ratio, 1.0),
                        location="temporal_post_distribution",
                        evidence=f"Gece (23:00-04:00) paylaşım oranı: %{ratio*100:.1f}",
                        psychological_weight=0.75,
                    )
                )

        return signals

    # ------------------------------------------------------------------ #
    # Contradiction mining
    # ------------------------------------------------------------------ #
    def _mine_contradictions(
        self, visual_signals: List[MicroSignal], text_signals: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        contradictions: List[Dict[str, Any]] = []
        signals = text_signals.get("signals", [])

        has_tension_or_void = any(
            s.signal_type in ("tension", "void") for s in visual_signals
        )
        has_positive_claim = any(
            s.signal_type in ("authentic", "defense") for s in signals
        )

        if has_tension_or_void and has_positive_claim:
            contradictions.append(
                {
                    "type": "visual_linguistic_mismatch",
                    "evidence": "Görsel sinyaller ile metinsel sunum arasında fark gözlendi",
                    "severity": 0.85,
                }
            )

        for s in signals:
            if s.signal_type == "contradiction":
                contradictions.append(
                    {
                        "type": "linguistic_contradiction",
                        "evidence": s.evidence,
                        "severity": s.psychological_weight,
                    }
                )

        return contradictions

    # ------------------------------------------------------------------ #
    # Identity / wound / resonance (bridge methods, not direct LLM input)
    # ------------------------------------------------------------------ #
    def _extract_claimed_identity(self, bio: str) -> str:
        if not bio:
            return "Unknown Identity"
        first_line = bio.split(".")[0].strip()
        return first_line[:60] or "Unknown Identity"

    def _calculate_achilles(
        self, contradictions: List[Dict], text_signals: Dict[str, Any]
    ) -> float:
        base_score = len(contradictions) * 15
        for signal in text_signals.get("signals", []):
            base_score += signal.psychological_weight * 10
        return min(base_score, 100.0)

    def _identify_wound_as_bridge(
        self, contradictions: List[Dict], text_signals: Dict[str, Any]
    ) -> Dict[str, Any]:
        if not contradictions:
            return {"type": "unknown", "defense": "unknown", "approach": "generic"}

        def sort_key(item: Dict) -> float:
            return item.get("severity", item.get("weight", 0))

        primary = max(contradictions, key=sort_key)
        wound_types = {
            "visual_linguistic_mismatch": {
                "type": "gözlemlenebilir_tutarsızlık",
                "defense": "yorumlanmadı",
                "approach": "kanıtla_sınırlı_iletişim",
            },
            "linguistic_contradiction": {
                "type": "gözlemlenebilir_tutarsızlık",
                "defense": "yorumlanmadı",
                "approach": "kanıtla_sınırlı_iletişim",
            },
            "social_vs_alone": {
                "type": "gözlemlenebilir_tutarsızlık",
                "defense": "yorumlanmadı",
                "approach": "kanıtla_sınırlı_iletişim",
            },
            "independent_vs_needy": {
                "type": "gözlemlenebilir_tutarsızlık",
                "defense": "yorumlanmadı",
                "approach": "kanıtla_sınırlı_iletişim",
            },
            "happy_vs_tired": {
                "type": "gözlemlenebilir_tutarsızlık",
                "defense": "yorumlanmadı",
                "approach": "kanıtla_sınırlı_iletişim",
            },
        }
        return wound_types.get(
            primary.get("type"), {"type": "gözlemlenebilir_tutarsızlık", "defense": "yorumlanmadı", "approach": "kanıtla_sınırlı_iletişim"}
        )

    def _calculate_resonance_potential(
        self, wound: Dict[str, Any], input_data: HumanBehaviorInput
    ) -> float:
        payload = (
            input_data
            if isinstance(input_data, HumanBehaviorInput)
            else HumanBehaviorInput.model_validate(input_data)
        )
        authenticity = min(
            max(float(payload.model_dump().get("user_authenticity_score", 0.5)), 0.0), 1.0
        )
        defense_strength = float(wound.get("defense_strength", 0.5))
        openness = 1.0 - min(max(defense_strength, 0.0), 1.0)
        return float((authenticity * openness) ** 0.5)
