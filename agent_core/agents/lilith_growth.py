"""LILITH — 360° insan analizini viral içeriğe çeviren büyüme ajanı.

Sunucusuz/hafif hedef: Raspberry Pi'de bile sıfır ek yükle koşacak şekilde
tasarlanmıştır. Sınıf, hem CLI (``run_lilith.py``) hem de boru hattı
entegrasyonları için TEK gerçek kaynaktır (prompt, formül, rapor biçimi dahil).

Katmanlar:
  * Matematiksel güvenlik zırhı (``_safe_float``/``_clamp``): NaN/Inf/str/list
    girdiler sessizce varsayılana düşer, ASLA exception fırlatmaz.
  * Nörokimyasal formül → ``NeuroMetrics`` (dopamin/serotonin/kortizol/oksitosin
    + bilişsel sürtünme; deterministik, LLM'siz).
  * İki taşıma: ``OpenAICompatibleGateway`` (anahtar varsa) ve
    ``FreeTextGateway`` (anahtar yokken: uydurma içerik ÜRETİLMEZ, dürüst
    "gateway yok" yolu). ``from_cli_credentials`` bu seçimi yapar.

Test: ``tests/unit/test_lilith_growth.py``.
"""

import json
import logging
import math
import urllib.parse
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from agent_core.capabilities.egress import open_client
from agent_core.services.confidence import normalize_confidence
from agent_core.services.llm_gateway import LLMGateway

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Matematiksel Güvenlik Katmanı (Uç-Durum Zırhı)
# --------------------------------------------------------------------------- #

def _safe_float(value: Any, default: float) -> float:
    """
    Herhangi bir girdiyi (None, str, list, NaN, Inf...) güvenle float'a çevirir.
    Dönüştürülemeyen veya sonlu (finite) olmayan her değer varsayılana düşer.
    ASLA exception fırlatmaz.
    """
    try:
        f = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    if not math.isfinite(f):
        return default
    return f


def _clamp(value: float, lo: float, hi: float) -> float:
    """Değeri [lo, hi] aralığına sabitler (kenetler)."""
    return max(lo, min(hi, value))


def _strip_code_fences(content: str) -> str:
    """LLM çıktısındaki ```json ... ``` sarmalayıcılarını temizler."""
    if "```json" in content:
        return content.split("```json")[1].split("```")[0].strip()
    if "```" in content:
        return content.split("```")[1].split("```")[0].strip()
    return content.strip()


# --------------------------------------------------------------------------- #
# Kutsal Sistem Promptu (TEK KAYNAK — CLI ve Agent aynı promptu paylaşır)
# --------------------------------------------------------------------------- #

LILITH_SYSTEM_PROMPT = """Sen LILITH'sin: Nörobilişsel Kitle Mühendisliği, Dopaminerjik Kanca ve Evrimsel Psikoloji Otoritesi.

BİLİMSEL TEMEL VE FORMÜLLER:
1. DOPAMİNERJİK ÖDÜL TAHMİN HATASI (Reward Prediction Error - Schultz):
   Formül: δ = R_gerçek - R_beklenen
   İnsan beyni sürekli bir sonraki düşünceyi tahmin eder (Predictive Coding). Kancanın (Hook) biyolojik görevi, bu öngörüyü anında parçalamaktır (Pattern Interrupt). Beklenti kırıldığı an Nucleus Accumbens'te ani bir dopamin dalgası tetiklenir ve "Merak Uçurumu" (Loewenstein Curiosity Gap) açılır.

2. AMİGDALA & KAYIPTAN KAÇINMA (Kahneman-Tversky Loss Aversion):
   Formül: V(Kayıp) ≈ 2.25 × V(Kazanç)
   Kayıp tehdidi, amigdalayı kazanç vaadinden 2 kat daha hızlı ve derin uyarır. Kitleye ne kazanacaklarını değil; hangi bilişsel yanılgı yüzünden statü, güç, zaman veya özgünlük kaybettiklerini doğrudan hissettir.

3. SEROTONİN & STATÜ PARA BİRİMİ (Social Currency - Berger / Sapolsky Hiyerarşisi):
   Bireyler içerik tüketmez; sosyal statü satın alır. Okuyucu bu içeriği paylaştığında veya savunduğunda akranları gözünde "derin, korkusuz, elit veya uyanmış" görünmelidir.

4. OKSİTOSİN & KABİLE REZONANSI (In-Group vs Out-Group):
   Bilişsel çelişkiyi bireysel suçluluktan çıkar; kolektif bir yanılsamaya ("sürü psikolojisi", "endüstri masalları") bağlayarak kabile aidiyeti yarat.

5. ZEİGARNİK NÖRAL DÖNGÜSÜ (Açık Bilişsel Döngüler):
   Bir düşünceyi asla erken doyurma. Kanca bir kapı açar, gövde kapının ardındaki labirenti gösterir, CTA ise anahtarı okuyucunun zihnine bırakır.

ÜSLUP VE TON:
- Keskin, hipnotik, manyetik ve nörolojik olarak sarsıcı.
- Klişe AI jargonu ("çağımızda", "şüphesiz", "önem taşımaktadır", "adım adım") ASLA YOK.
- Her satır bir nöron ateşlemesi yaratacak ritimde ve kadansta olmalıdır.
"""


# --------------------------------------------------------------------------- #
# Pydantic v2 Şemaları — Validator Seviyesinde Kenetleme (Defense-in-Depth)
# --------------------------------------------------------------------------- #

class NeurochemicalProfile(BaseModel):
    """İçeriğin nörokimyasal tetikleyici haritası (D.O.S.E.). Tüm alanlar [0.0, 1.0]."""
    dopamine_potential: float = 0.85
    serotonin_status_currency: float = 0.80
    cortisol_urgency: float = 0.60
    oxytocin_affinity: float = 0.70
    model_config = ConfigDict(extra="allow")

    @field_validator(
        "dopamine_potential",
        "serotonin_status_currency",
        "cortisol_urgency",
        "oxytocin_affinity",
        mode="before",
    )
    @classmethod
    def _clamp_unit_interval(cls, v: Any) -> float:
        return _clamp(_safe_float(v, 0.5), 0.0, 1.0)


class NeuroMetrics(BaseModel):
    """İçeriğin bilişsel ve formüle dayalı etki metrikleri."""
    pattern_interrupt_index: float = 0.90
    cognitive_dissonance_score: float = 0.85
    viral_coefficient_score: float = 8.4  # 0.0 - 10.0
    dominant_neurotransmitter: str = "dopamine"
    target_brain_region: str = "nucleus_accumbens"
    model_config = ConfigDict(extra="allow")

    @field_validator("pattern_interrupt_index", "cognitive_dissonance_score", mode="before")
    @classmethod
    def _clamp_zero_one(cls, v: Any) -> float:
        return _clamp(_safe_float(v, 0.5), 0.0, 1.0)

    @field_validator("viral_coefficient_score", mode="before")
    @classmethod
    def _clamp_viral_score(cls, v: Any) -> float:
        return _clamp(_safe_float(v, 5.0), 0.0, 10.0)

    @field_validator("dominant_neurotransmitter", mode="before")
    @classmethod
    def _validate_neurotransmitter(cls, v: Any) -> str:
        allowed = {"dopamine", "serotonin", "cortisol", "oxytocin"}
        candidate = str(v).strip().lower() if v else "dopamine"
        return candidate if candidate in allowed else "dopamine"


class LilithGenerationResponse(BaseModel):
    """LLM response contract. Empty content is allowed by the schema so the
    caller can reject it explicitly instead of turning defaults into success.
    """

    hook: str = ""
    psychological_angle: str = ""
    content_body: str = ""
    call_to_action: str = ""
    pollinations_image_prompt: str = ""
    dopamine: Optional[float] = None
    serotonin: Optional[float] = None
    cortisol: Optional[float] = None
    oxytocin: Optional[float] = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    subconscious_trigger: str = ""
    retention_loop_strategy: str = ""
    formula_breakdown: str = ""

    model_config = ConfigDict(extra="ignore")


class LilithContentPackage(BaseModel):
    """Lilith tarafından üretilen viral ve nörobilişsel içerik paketi."""
    platform: str = "x_twitter"
    hook: str
    psychological_angle: str
    content_body: str
    call_to_action: str
    pollinations_image_prompt: str
    pollinations_image_url: str
    # URL construction is not proof that the remote service generated an image.
    image_generation_status: str = "not_requested"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    data_confidence: bool = False
    confidence_reason: Optional[str] = None
    fallback_reason: Optional[str] = None

    neurochemical_profile: Optional[NeurochemicalProfile] = None
    neuro_metrics: Optional[NeuroMetrics] = None
    subconscious_trigger: Optional[str] = None
    retention_loop_strategy: Optional[str] = None
    formula_breakdown: Optional[str] = None

    model_config = ConfigDict(extra="allow")


# --------------------------------------------------------------------------- #
# LLMGateway ile Duck-Type Uyumlu Hafif Adaptörler
# (run_lilith.py bu adaptörleri seçer; agent hangisini aldığını bilmez.)
# --------------------------------------------------------------------------- #

class _ChatMessage:
    __slots__ = ("content",)

    def __init__(self, content: str):
        self.content = content


class _ChatChoice:
    __slots__ = ("message",)

    def __init__(self, content: str):
        self.message = _ChatMessage(content)


class _ChatResponse:
    __slots__ = ("choices",)

    def __init__(self, content: str):
        self.choices: List[_ChatChoice] = [_ChatChoice(content)]


class FreeTextGateway:
    """
    API anahtarı gerektirmeyen metin üretim gateway'i (Pollinations.ai).

    NOT: Pollinations text API zaman zaman 402/429 dönebilir (tier/rate-limit
    politikası değişkendir). Bu durumda LilithGrowthAgent.execute() zaten
    kendi deterministik nöro-fallback'ine düşer — burada ekstra retry mantığına
    GEREK YOK, sorumluluk ayrımı ve sıfır-çökme garantisi korunur.
    """

    TEXT_API_URL = "https://text.pollinations.ai/"

    def __init__(self, timeout: float = 7.0):
        self.timeout = timeout

    async def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        response_format: Optional[Dict[str, str]] = None,
    ) -> _ChatResponse:
        payload = {"messages": messages, "jsonMode": True}
        async with open_client(purpose="llm", timeout=self.timeout) as client:
            resp = await client.post(
                self.TEXT_API_URL,
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            content = resp.text.strip()
        return _ChatResponse(_strip_code_fences(content))


class OpenAICompatibleGateway:
    """OpenAI veya OpenRouter uyumlu chat/completions uç noktaları için hafif httpx adaptörü."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-4o",
        timeout: float = 45.0,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    async def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        response_format: Optional[Dict[str, str]] = None,
    ) -> _ChatResponse:
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if response_format:
            payload["response_format"] = response_format

        async with open_client(purpose="llm", timeout=self.timeout) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
        return _ChatResponse(_strip_code_fences(content))


# --------------------------------------------------------------------------- #
# Ana Ajan
# --------------------------------------------------------------------------- #

class LilithGrowthAgent:
    """
    Aspasia'nın 360° insan analizini viral sosyal medya içeriklerine dönüştüren ajan.
    Tüy kadar hafif, sunucusuz, Raspberry Pi'de bile sıfır yükle çalışır.

    Bu sınıf, hem CLI (`run_lilith.py`) hem de pipeline entegrasyonları için
    TEK gerçek kaynaktır (prompt, formül, rapor formatlama dahil).
    """

    def __init__(self, llm_gateway: Optional[Any] = None):
        self.llm_gateway = llm_gateway or LLMGateway()

    @classmethod
    def from_cli_credentials(
        cls,
        api_key: Optional[str],
        base_url: Optional[str],
        model: str = "gpt-4o",
    ) -> "LilithGrowthAgent":
        """
        CLI kimlik bilgilerinden uygun gateway'i seçip ajanı inşa eder.
        api_key yoksa otomatik olarak sıfır-maliyet FreeTextGateway'e düşer.
        """
        if api_key:
            gateway: Any = OpenAICompatibleGateway(
                api_key=api_key,
                base_url=base_url or "https://api.openai.com/v1",
                model=model,
            )
        else:
            gateway = FreeTextGateway()
        return cls(llm_gateway=gateway)

    @staticmethod
    def compute_neuro_formula(
        dopamine: Any = 0.85,
        serotonin: Any = 0.80,
        cortisol: Any = 0.60,
        oxytocin: Any = 0.70,
        cognitive_friction: Any = 0.25,
    ) -> NeuroMetrics:
        """
        Lilith Viral İndeks (Vc) Formülü:

            Vc = [ (D^1.2 * S * (1 + 0.8*C)) / max(0.1, F) ] * (0.8 + 0.4*O) * 2.2

        MATEMATİKSEL SINIR GARANTİLERİ:
        - D, S, C, O ∈ [0.05, 1.0]  → taban her zaman pozitif, D^1.2 ASLA
          complex sayı üretmez (negatif taban + kesirli üs riski yok edildi).
        - F (bilişsel sürtünme) ∈ [0.10, 1.0] → sıfıra bölme kalıcı olarak
          imkânsız kılındı.
        - NaN, +/-Inf, None, liste, sözlük, sayısal olmayan string gibi
          HER TÜRLÜ bozuk girdi `_safe_float` tarafından sessizce
          varsayılan değere düşürülür; fonksiyon ASLA exception fırlatmaz.
        - Nihai Vc skoru daima [0.5, 10.0] aralığına kenetlenir.
        - `NeuroMetrics` modelinin kendi validator'ları da aynı kenetlemeyi
          ikinci kez uygular (çift katmanlı savunma).
        """
        d = _clamp(_safe_float(dopamine, 0.85), 0.05, 1.0)
        s = _clamp(_safe_float(serotonin, 0.80), 0.05, 1.0)
        c = _clamp(_safe_float(cortisol, 0.60), 0.05, 1.0)
        o = _clamp(_safe_float(oxytocin, 0.70), 0.05, 1.0)
        f = _clamp(_safe_float(cognitive_friction, 0.25), 0.10, 1.0)

        try:
            raw_vc = ((d ** 1.2) * s * (1.0 + 0.8 * c) / f) * (0.8 + 0.4 * o)
            if not math.isfinite(raw_vc):
                raw_vc = 1.0
        except (ZeroDivisionError, ValueError, OverflowError):
            # f>=0.10 ve d>=0.05 olduğu için pratikte tetiklenemez;
            # gelecekteki formül değişikliklerine karşı güvenlik ağı.
            raw_vc = 1.0

        viral_score = _clamp(round(raw_vc * 2.2, 2), 0.5, 10.0)
        pattern_interrupt = _clamp(round(0.55 * d + 0.45 * c, 2), 0.0, 1.0)
        cognitive_dissonance = _clamp(round(0.60 * c + 0.40 * d, 2), 0.0, 1.0)

        weights = {"dopamine": d, "serotonin": s, "cortisol": c, "oxytocin": o}
        dominant = max(weights.items(), key=lambda x: x[1])[0]

        regions = {
            "dopamine": "nucleus_accumbens (Ödül & Beklenti)",
            "cortisol": "amygdala (Tehdit & Kayıp Kaçınması)",
            "serotonin": "prefrontal_cortex (Statü & Karar)",
            "oxytocin": "anterior_cingulate_cortex (Kabile Rezonansı)",
        }

        return NeuroMetrics(
            pattern_interrupt_index=pattern_interrupt,
            cognitive_dissonance_score=cognitive_dissonance,
            viral_coefficient_score=viral_score,
            dominant_neurotransmitter=dominant,
            target_brain_region=regions.get(dominant, "nucleus_accumbens"),
        )

    def build_pollinations_url(
        self,
        prompt: str,
        width: int = 1080,
        height: int = 1080,
        model: str = "flux",
    ) -> str:
        """Pollinations.ai üzerinden 0-token, API key'siz anında görsel URL'i oluşturur."""
        clean_prompt = (prompt or "").strip().replace("\n", " ")
        if not clean_prompt:
            return ""
        encoded = urllib.parse.quote(clean_prompt)
        return f"https://image.pollinations.ai/prompt/{encoded}?width={width}&height={height}&model={model}&nologo=true"

    async def _request_generation(self, prompt: str) -> Any:
        """Call either the gateway's structured chain or an explicit chat adapter.

        The production ``LLMGateway`` exposes ``query_json_chain`` rather than
        ``chat``. CLI/test adapters may implement the small OpenAI-chat surface.
        Keeping the two contracts explicit prevents a mock-only ``.chat`` method
        from masking a broken default integration.
        """
        gateway = self.llm_gateway
        chat = getattr(gateway, "chat", None)
        if callable(chat):
            return await chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                response_format={"type": "json_object"},
            )

        query_json_chain = getattr(gateway, "query_json_chain", None)
        if callable(query_json_chain):
            return await query_json_chain(
                prompt=prompt,
                schema=LilithGenerationResponse,
                task="dialogue",
                temperature=0.7,
                agent_name="lilith_growth",
            )

        query_json = getattr(gateway, "query_json", None)
        if callable(query_json):
            return await query_json(
                prompt=prompt,
                schema=LilithGenerationResponse,
                temperature=0.7,
                task="dialogue",
                agent_name="lilith_growth",
            )

        raise TypeError("unsupported_llm_gateway_contract")

    @staticmethod
    def _response_data(response: Any) -> Dict[str, Any]:
        """Normalize typed gateway and OpenAI-style responses to a JSON object."""
        if isinstance(response, LilithGenerationResponse):
            return response.model_dump()
        if isinstance(response, BaseModel):
            return response.model_dump()
        if isinstance(response, dict):
            return response

        if isinstance(response, str):
            content = response
        else:
            choices = getattr(response, "choices", None)
            if not (isinstance(choices, (list, tuple)) and choices):
                # LLMGateway.chat_completion wraps the provider response in a
                # value object; adapters that already return `choices` need no
                # wrapper handling.
                response = getattr(response, "response", response)
                choices = getattr(response, "choices", None)
            if not (isinstance(choices, (list, tuple)) and choices):
                raise ValueError("empty_model_response")
            message = getattr(choices[0], "message", None)
            content = getattr(message, "content", None)

        if not isinstance(content, str) or not content.strip():
            raise ValueError("empty_model_content")
        parsed = json.loads(_strip_code_fences(content))
        if not isinstance(parsed, dict):
            raise ValueError("model_response_must_be_json_object")
        return parsed

    @staticmethod
    def render_console_report(package: "LilithContentPackage") -> str:
        """
        `LilithContentPackage`'ı okunabilir bir konsol raporuna dönüştürür.
        Başarı ve fallback durumları için TEK ortak formatlayıcı (kod tekrarı yok).
        """
        metrics = package.neuro_metrics
        chem = package.neurochemical_profile
        mode_label = (
            "MODEL ÇAĞRISI BAŞARISIZ — FALLBACK"
            if package.fallback_reason
            else "MODEL ÇIKTISI — BAĞIMSIZ OLARAK DOĞRULANMADI"
        )

        lines = [
            "=" * 65,
            f"🔥 LILITH NÖROBİLİŞSEL VİRAL İÇERİK MOTORU — {mode_label}",
            "=" * 65,
            f"\n📌 [BİLİŞSEL KANCA / PATTERN INTERRUPT]:\n{package.hook}",
            f"\n🧠 [NÖROPSİKOLOJİK AÇI]:\n{package.psychological_angle}",
            f"\n🧬 [BİLİNÇALTI TETİKLEYİCİ]:\n{package.subconscious_trigger or '-'}",
            f"\n📝 [İÇERİK GÖVDESİ (ZEİGARNİK RİTMİ)]:\n{package.content_body}",
            f"\n⚡ [EYLEME ÇAĞRI (CTA)]:\n{package.call_to_action}",
            "\n" + "-" * 65,
            "📊 HEURİSTİK FORMÜL ÇIKTILARI (biyolojik/klinik ölçüm değildir):",
            (
                f"  • Dopamin girdisi  : %{round(chem.dopamine_potential * 100)}\n"
                f"  • Serotonin girdisi: %{round(chem.serotonin_status_currency * 100)}\n"
                f"  • Kortizol girdisi : %{round(chem.cortisol_urgency * 100)}\n"
                f"  • Oksitosin girdisi: %{round(chem.oxytocin_affinity * 100)}\n"
                f"  • Formül etiketi   : {metrics.dominant_neurotransmitter}"
                if chem is not None and metrics is not None
                else "  • Hesaplanmadı — model çıktısı yok."
            ),
            (
                f"  • BİLEŞİK VİRAL KATSAYI (heuristik): {metrics.viral_coefficient_score} / 10.0"
                if metrics is not None
                else ""
            ),
            "-" * 65,
            f"\n🎨 [GÖRSEL PROMPTU]:\n{package.pollinations_image_prompt}",
            f"\n🔗 [POLLINATIONS İSTEK URL'İ — ÜRETİM DOĞRULANMADI]:\n{package.pollinations_image_url or '-'}",
            f"Görsel durumu: {package.image_generation_status}",
            f"Profil bağlamı mevcut: {'evet' if package.data_confidence else 'hayır / doğrulanmadı'}",
            f"Model güven alanı: {package.confidence:.2f} (kalibre edildiği anlamına gelmez)",
        ]
        if package.confidence_reason:
            lines.append(f"Güven/veri durumu: {package.confidence_reason}")
        if package.fallback_reason:
            lines.append(f"\n⚠️ [FALLBACK NEDENİ]: {package.fallback_reason}")
        lines.append("=" * 65 + "\n")
        return "\n".join(lines)

    async def execute(self, payload: Dict[str, Any]) -> LilithContentPackage:
        """
        Aspasia profilini veya doğrudan konuyu alıp nörobilişsel viral içerik üretir.
        """
        topic = str(payload.get("topic") or "").strip()
        platform = str(payload.get("platform") or "x_twitter").strip()

        target_profile = payload.get("target_profile", {})
        friction = payload.get("friction_profile", {})
        passion = payload.get("passion_profile", {})
        cognitive = payload.get("cognitive_style", {})

        target_profile = target_profile if isinstance(target_profile, dict) else {}
        friction = friction if isinstance(friction, dict) else {}
        passion = passion if isinstance(passion, dict) else {}
        cognitive = cognitive if isinstance(cognitive, dict) else {}

        def _items(value: Any) -> List[str]:
            if isinstance(value, str):
                return [value.strip()] if value.strip() else []
            if isinstance(value, (list, tuple)):
                return [str(item).strip() for item in value if str(item).strip()]
            return []

        frictions_text = ", ".join(
            _items(friction.get("sensitivities")) + _items(friction.get("stress_triggers"))
        )
        passions_text = ", ".join(
            _items(passion.get("core_passions")) + _items(passion.get("energizing_topics"))
        )
        tone_pref = str(cognitive.get("communication_tone") or "").strip()

        # Only explicitly supplied public text is copied into this prompt. The
        # original implementation counted target_profile's mere truthiness as
        # evidence while never using its contents.
        target_bio = target_profile.get("bio")
        target_bio = target_bio.strip() if isinstance(target_bio, str) else ""
        target_posts = _items(target_profile.get("posts"))[:10]
        profile_lines = []
        if target_bio:
            profile_lines.append(f"Biyografi: {target_bio}")
        if target_posts:
            profile_lines.append("Paylaşımlar: " + " | ".join(target_posts))
        target_profile_text = "\n".join(profile_lines)

        has_profile = bool(target_profile_text or frictions_text or passions_text or tone_pref)

        context_block = f"""
Hedef Kitle / Konu: {topic or 'Belirtilmedi'}
Platform: {platform}
Hedef Profili (sağlanan metin): {target_profile_text or 'veri yok'}
Tercih Edilen Üslup (sağlandıysa): {tone_pref or 'veri yok'}
Hassasiyetler & Sürtünme Noktaları (sağlanan): {frictions_text or 'veri yok'}
Tutku & Enerji Alanları (sağlanan): {passions_text or 'veri yok'}
"""

        prompt = f"""{LILITH_SYSTEM_PROMPT}

Aşağıdaki verileri incele ve hedef kitlenin Nucleus Accumbens (dopamin) ve Amigdala (kayıp korkusu) devrelerini aynı anda tetikleyecek, ezber bozan bir nöro-içerik paketi üret.

GİRDİ ANALİZİ:
{context_block}

Gereksinimler:
1. 'hook': İlk 3 saniyede varsayılan bilişsel akışı kıran (Pattern Interrupt) vuruş (1-2 cümle).
2. 'psychological_angle': Hedeflenen nörobilişsel açının 1 cümlelik teknik açıklaması.
3. 'content_body': Ana gövde metni.
4. 'call_to_action': Zeigarnik döngüsünü kapatmayan kapanış sorusu.
5. 'pollinations_image_prompt': İngilizce, sinematik, minimalist sanat tarifi.
6. 'subconscious_trigger': Hedeflenen evrimsel/arkaik dürtü.
7. 'retention_loop_strategy': Zeigarnik açık döngü stratejisi.
8. Nörokimyasal Değerler (0.0 - 1.0): 'dopamine', 'serotonin', 'cortisol', 'oxytocin'.

Aşağıdaki JSON şemasına BİREBİR uygun yanıt ver:
{{
  "hook": "...",
  "psychological_angle": "...",
  "content_body": "...",
  "call_to_action": "...",
  "pollinations_image_prompt": "...",
  "subconscious_trigger": "...",
  "retention_loop_strategy": "...",
  "dopamine": 0.92,
  "serotonin": 0.85,
  "cortisol": 0.65,
  "oxytocin": 0.70,
  "formula_breakdown": "...",
  "confidence": 0.95
}}
"""

        try:
            response = await self._request_generation(prompt)
            data = self._response_data(response)

            required_fields = (
                "hook",
                "psychological_angle",
                "content_body",
                "call_to_action",
            )
            for field_name in required_fields:
                value = data.get(field_name)
                if not isinstance(value, str) or not value.strip():
                    raise ValueError(f"missing_required_content:{field_name}")

            img_prompt = data.get("pollinations_image_prompt")
            img_prompt = img_prompt.strip() if isinstance(img_prompt, str) else ""
            img_url = self.build_pollinations_url(img_prompt)

            # These are heuristic inputs, not physiological measurements. If
            # any model field is missing/invalid, do not synthesize a baseline.
            raw_metrics = {
                name: _safe_float(data.get(name), float("nan"))
                for name in ("dopamine", "serotonin", "cortisol", "oxytocin")
            }
            has_numeric_inputs = all(math.isfinite(value) for value in raw_metrics.values())
            neuro_chem = None
            metrics = None
            cognitive_friction = _safe_float(
                payload.get("cognitive_friction", friction.get("cognitive_friction", 0.25)),
                0.25,
            )
            if has_numeric_inputs:
                neuro_chem = NeurochemicalProfile(
                    dopamine_potential=raw_metrics["dopamine"],
                    serotonin_status_currency=raw_metrics["serotonin"],
                    cortisol_urgency=raw_metrics["cortisol"],
                    oxytocin_affinity=raw_metrics["oxytocin"],
                )
                metrics = self.compute_neuro_formula(
                    dopamine=raw_metrics["dopamine"],
                    serotonin=raw_metrics["serotonin"],
                    cortisol=raw_metrics["cortisol"],
                    oxytocin=raw_metrics["oxytocin"],
                    cognitive_friction=cognitive_friction,
                )

            model_confidence, confidence_valid = normalize_confidence(data.get("confidence"))
            data_confidence = bool(has_profile and confidence_valid and model_confidence > 0.0)
            confidence_reason = (
                None if data_confidence
                else "invalid_model_confidence" if not confidence_valid
                else "no_profile_evidence" if not has_profile
                else "model_confidence_zero"
            )
            model_confidence = model_confidence if data_confidence else 0.0
            formula_breakdown = str(data.get("formula_breakdown") or "")
            if not formula_breakdown and metrics is not None:
                formula_breakdown = (
                    f"Vc={metrics.viral_coefficient_score} "
                    f"[D={raw_metrics['dopamine']:.2f}, S={raw_metrics['serotonin']:.2f}, "
                    f"C={raw_metrics['cortisol']:.2f}, O={raw_metrics['oxytocin']:.2f}, "
                    f"F={cognitive_friction:.2f}]"
                )

            return LilithContentPackage(
                platform=platform,
                hook=data["hook"],
                psychological_angle=data["psychological_angle"],
                content_body=data["content_body"],
                call_to_action=data["call_to_action"],
                pollinations_image_prompt=img_prompt,
                pollinations_image_url=img_url,
                image_generation_status=(
                    "request_url_created_unverified" if img_url else "not_requested"
                ),
                confidence=model_confidence,
                data_confidence=data_confidence,
                confidence_reason=confidence_reason,
                fallback_reason=None,
                neurochemical_profile=neuro_chem,
                neuro_metrics=metrics,
                subconscious_trigger=str(data.get("subconscious_trigger") or ""),
                retention_loop_strategy=str(data.get("retention_loop_strategy") or ""),
                formula_breakdown=formula_breakdown,
            )
        except Exception as e:
            logger.warning("Lilith içerik üretilemedi (%s)", type(e).__name__)
            reason = (
                "invalid_model_response"
                if isinstance(e, (json.JSONDecodeError, ValueError, TypeError, KeyError))
                else "llm_unavailable"
            )
            # No template is presented as generated content and no baseline
            # neurochemical scores are invented on the error path.
            return LilithContentPackage(
                platform=platform,
                hook="",
                psychological_angle="",
                content_body="",
                call_to_action="",
                pollinations_image_prompt="",
                pollinations_image_url="",
                image_generation_status="not_requested",
                confidence=0.0,
                data_confidence=False,
                fallback_reason=reason,
                neurochemical_profile=None,
                neuro_metrics=None,
                subconscious_trigger="",
                retention_loop_strategy="",
                formula_breakdown="",
            )
