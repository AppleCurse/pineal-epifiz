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

from pydantic import BaseModel, ConfigDict, field_validator

from agent_core.capabilities.egress import open_client
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
    except (TypeError, ValueError):
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


class LilithContentPackage(BaseModel):
    """Lilith tarafından üretilen viral ve nörobilişsel içerik paketi."""
    platform: str = "x_twitter"
    hook: str
    psychological_angle: str
    content_body: str
    call_to_action: str
    pollinations_image_prompt: str
    pollinations_image_url: str
    confidence: float = 0.0
    data_confidence: bool = False
    fallback_reason: Optional[str] = None

    neurochemical_profile: Optional[NeurochemicalProfile] = None
    neuro_metrics: Optional[NeuroMetrics] = None
    subconscious_trigger: Optional[str] = None
    retention_loop_strategy: Optional[str] = None
    formula_breakdown: Optional[str] = None

    model_config = ConfigDict(extra="allow")

    @field_validator("confidence", mode="before")
    @classmethod
    def _clamp_confidence(cls, v: Any) -> float:
        return _clamp(_safe_float(v, 0.5), 0.0, 1.0)


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
        encoded = urllib.parse.quote(clean_prompt)
        return f"https://image.pollinations.ai/prompt/{encoded}?width={width}&height={height}&model={model}&nologo=true"

    @staticmethod
    def render_console_report(package: "LilithContentPackage") -> str:
        """
        `LilithContentPackage`'ı okunabilir bir konsol raporuna dönüştürür.
        Başarı ve fallback durumları için TEK ortak formatlayıcı (kod tekrarı yok).
        """
        metrics = package.neuro_metrics or LilithGrowthAgent.compute_neuro_formula()
        chem = package.neurochemical_profile or NeurochemicalProfile()
        mode_label = "NÖRAL BASELINE (Fallback)" if package.fallback_reason else "CANLI ANALİZ"

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
            "📊 NÖROKİMYASAL MATRİS & FORMÜL SKORLARI (D.O.S.E.):",
            f"  • Dopamin (Merak & Ödül Hatası δ) : %{round(chem.dopamine_potential * 100)}",
            f"  • Serotonin (Statü Sermayesi)     : %{round(chem.serotonin_status_currency * 100)}",
            f"  • Kortizol (Amigdala / Kayıp)     : %{round(chem.cortisol_urgency * 100)}",
            f"  • Oksitosin (Kabile Bağı)         : %{round(chem.oxytocin_affinity * 100)}",
            f"  • 🎯 Baskın Nörotransmitter        : {metrics.dominant_neurotransmitter} → {metrics.target_brain_region}",
            f"  • 🚀 BİLEŞİK VİRAL KATSAYI (Vc)   : {metrics.viral_coefficient_score} / 10.0",
            "-" * 65,
            f"\n🎨 [GÖRSEL PROMPTU]:\n{package.pollinations_image_prompt}",
            f"\n🔗 [POLLINATIONS GÖRSEL LİNKİ]:\n{package.pollinations_image_url}",
        ]
        if package.fallback_reason:
            lines.append(f"\n⚠️ [FALLBACK NEDENİ]: {package.fallback_reason}")
        lines.append("=" * 65 + "\n")
        return "\n".join(lines)

    async def execute(self, payload: Dict[str, Any]) -> LilithContentPackage:
        """
        Aspasia profilini veya doğrudan konuyu alıp nörobilişsel viral içerik üretir.
        """
        topic = payload.get("topic", "")
        platform = payload.get("platform", "x_twitter")

        target_profile = payload.get("target_profile", {})
        friction = payload.get("friction_profile", {})
        passion = payload.get("passion_profile", {})
        cognitive = payload.get("cognitive_style", {})

        frictions_text = ", ".join(
            friction.get("sensitivities", []) + friction.get("stress_triggers", [])
        )
        passions_text = ", ".join(
            passion.get("core_passions", []) + passion.get("energizing_topics", [])
        )
        tone_pref = cognitive.get("communication_tone", "doğrudan")

        has_profile = bool(frictions_text or passions_text or target_profile)

        context_block = f"""
Hedef Kitle / Konu: {topic or 'Belirtilmedi'}
Platform: {platform}
Tercih Edilen Üslup: {tone_pref}
Hassasiyetler & Sürtünme Noktaları (Aspasia): {frictions_text or 'Statü tehdidi, bilişsel uyumsuzluk, belirsizlik'}
Tutku & Enerji Alanları (Aspasia): {passions_text or 'Yüksek merak, güç asimetrisi, derin içgörü'}
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
            res = await self.llm_gateway.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                response_format={"type": "json_object"},
            )
            raw = res.choices[0].message.content or "{}"
            data = json.loads(raw)

            img_prompt = data.get(
                "pollinations_image_prompt", f"cinematic dark aesthetic photography of {topic}"
            )
            img_url = self.build_pollinations_url(img_prompt)

            # Tek tek alanlarda bozuk veri, TÜM üretimi çökertmesin diye _safe_float kullanılır.
            dopamine = _safe_float(data.get("dopamine"), 0.88)
            serotonin = _safe_float(data.get("serotonin"), 0.82)
            cortisol = _safe_float(data.get("cortisol"), 0.62)
            oxytocin = _safe_float(data.get("oxytocin"), 0.70)

            neuro_chem = NeurochemicalProfile(
                dopamine_potential=dopamine,
                serotonin_status_currency=serotonin,
                cortisol_urgency=cortisol,
                oxytocin_affinity=oxytocin,
            )

            metrics = self.compute_neuro_formula(
                dopamine=dopamine,
                serotonin=serotonin,
                cortisol=cortisol,
                oxytocin=oxytocin,
            )

            return LilithContentPackage(
                platform=platform,
                hook=data.get("hook", ""),
                psychological_angle=data.get("psychological_angle", ""),
                content_body=data.get("content_body", ""),
                call_to_action=data.get("call_to_action", ""),
                pollinations_image_prompt=img_prompt,
                pollinations_image_url=img_url,
                confidence=_safe_float(data.get("confidence"), 0.9),
                data_confidence=has_profile,
                fallback_reason=None,
                neurochemical_profile=neuro_chem,
                neuro_metrics=metrics,
                subconscious_trigger=data.get(
                    "subconscious_trigger", "Statü Hiyerarşisi ve Bilişsel Dissonans"
                ),
                retention_loop_strategy=data.get(
                    "retention_loop_strategy",
                    "Zeigarnik Açık Döngü: Çelişkiyi son satıra kadar çözmeme",
                ),
                formula_breakdown=data.get(
                    "formula_breakdown",
                    f"Vc={metrics.viral_coefficient_score} "
                    f"[D={dopamine:.2f}, S={serotonin:.2f}, C={cortisol:.2f}, PIR={metrics.pattern_interrupt_index:.2f}]",
                ),
            )
        except Exception as e:
            logger.error(f"Lilith içerik üretimi sırasında hata: {e}")
            fallback_prompt = f"minimalist dark aesthetic concept art of {topic or 'insight'}"
            fallback_metrics = self.compute_neuro_formula(0.80, 0.75, 0.60, 0.65)
            return LilithContentPackage(
                platform=platform,
                hook=f"Çoğu insanın göremediği gerçek: {topic or 'başarı'} hakkında bildiklerinizi unutun.",
                psychological_angle="Bilişsel çelişki (Festinger) ve kayıptan kaçınma (Kahneman)",
                content_body="Gürültünün ortasında sinyali yakalamak için önce neye neden tepki verdiğinizi anlamanız gerekir.",
                call_to_action="Sizce en büyük nörolojik yanılgı nerede?",
                pollinations_image_prompt=fallback_prompt,
                pollinations_image_url=self.build_pollinations_url(fallback_prompt),
                confidence=0.5,
                data_confidence=False,
                fallback_reason=f"error: {str(e)}",
                neurochemical_profile=NeurochemicalProfile(
                    dopamine_potential=0.80,
                    serotonin_status_currency=0.75,
                    cortisol_urgency=0.60,
                    oxytocin_affinity=0.65,
                ),
                neuro_metrics=fallback_metrics,
                subconscious_trigger="Bilişsel Uyumsuzluk ve Kayıp Korkusu",
                retention_loop_strategy="Zeigarnik Beklenti Boşluğu",
                formula_breakdown=f"Vc={fallback_metrics.viral_coefficient_score} (Fallback baseline)",
            )
