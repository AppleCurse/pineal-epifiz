"""Karanlik uclu: Kanıt ve psikodinamik derinlik tabanlı ölçüm gövdesi.

GÖREV 2.1 ile statik sözlük sayımı kaldırıldı (kelime-sayma narsisizm ölçümü değildir).
Yeni kural: Trait skorları ve sömürülebilirlik (exploitability) YALNIZCA somut alıntılı
kanıt (evidence_quotes) veya psychodynamic_depth yapısal sinyalleri varsa ölçülür.
Alıntısız sıradan metinlerde trait_scores_measured=False kalır ve trait'ler 0.0 döner (UI'da null).
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from agent_core.services.theme_cluster import cluster_texts


class DarkTriadProfile(BaseModel):
    machiavellianism: float = 0.0
    narcissism: float = 0.0
    psychopathy: float = 0.0
    exploitability: float = 0.0
    theme_analysis: Optional[Dict[str, Any]] = None
    trait_scores_measured: bool = False
    evidence_quotes: Dict[str, List[str]] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


# GÖREV 2 artığı: derinlik->strateji eşikleri (tasarım kararı, test-kilitli).
# Öncelik: mirroring > alliance > thrill.
DEPTH_MIRRORING_REACTION = 0.40
DEPTH_ALLIANCE_REPETITION = 0.40


class DarkTriadAnalyzer:
    """Karanlık üçlü psikolojik profil analisti.
    
    Yalnızca doğrulanabilir alıntılar veya psikodinamik derinlik sinyalleri
    mevcut olduğunda ölçülmüş skor (trait_scores_measured=True) üretir.
    """

    def analyze(self, profile_data: Dict, *, depth: Optional[Dict[str, Any]] = None) -> DarkTriadProfile:
        raw_posts = (profile_data or {}).get("posts") or []
        if isinstance(raw_posts, str):
            raw_posts = [raw_posts]
        posts = [p for p in raw_posts if isinstance(p, str) and p.strip()]
        bio = (profile_data or {}).get("bio") or ""
        texts = ([bio] if isinstance(bio, str) and bio.strip() else []) + posts
        themes = cluster_texts(texts)

        # 1. Açık veya enjekte edilmiş psychodynamic_depth kontrolü
        depth_data = depth or (profile_data or {}).get("psychodynamic_depth")

        narcissism = 0.0
        machiavellianism = 0.0
        psychopathy = 0.0
        evidence_quotes: Dict[str, List[str]] = {}

        if isinstance(depth_data, dict) and depth_data.get("verdict") == "ok":
            reaction = depth_data.get("reaction_formation_index")
            channels = depth_data.get("channels") or {}
            decl = channels.get("declaration") if isinstance(channels, dict) else {}
            dsig = decl.get("signals") if isinstance(decl, dict) else {}
            repetition = dsig.get("repetition_score") if isinstance(dsig, dict) else None
            rhythm = channels.get("rhythm") if isinstance(channels, dict) else {}
            rsig = rhythm.get("signals") if isinstance(rhythm, dict) else {}
            n_rup = rsig.get("n_ruptures", 0) if isinstance(rsig, dict) else 0
            kinds = rsig.get("rupture_kinds", []) if isinstance(rsig, dict) else []

            quotes = depth_data.get("evidence_quotes") or (profile_data or {}).get("evidence_quotes") or []
            if isinstance(quotes, list) and quotes:
                valid_quotes = [str(q).strip() for q in quotes if str(q).strip()]
            else:
                valid_quotes = [t for t in texts if len(t.split()) >= 4][:3]

            if reaction is not None and isinstance(reaction, (int, float)) and reaction >= DEPTH_MIRRORING_REACTION:
                narcissism = round(min(1.0, float(reaction) * 1.5), 2)
                evidence_quotes["narcissism"] = valid_quotes[:2]

            if repetition is not None and isinstance(repetition, (int, float)) and repetition >= DEPTH_ALLIANCE_REPETITION:
                machiavellianism = round(min(1.0, float(repetition) * 1.5), 2)
                evidence_quotes["machiavellianism"] = valid_quotes[:2]

            if (isinstance(n_rup, int) and n_rup >= 1) or "entropy_jump" in kinds:
                psychopathy = 0.65
                evidence_quotes["psychopathy"] = valid_quotes[:2]

        # 2. Doğrudan profile_data['evidence_quotes'] taşıyan açık analiz girdisi
        raw_evidence = (profile_data or {}).get("evidence_quotes")
        if isinstance(raw_evidence, dict):
            for trait in ("narcissism", "machiavellianism", "psychopathy"):
                t_quotes = raw_evidence.get(trait)
                if isinstance(t_quotes, list) and any(bool(q) for q in t_quotes):
                    evidence_quotes[trait] = [str(q).strip() for q in t_quotes if str(q).strip()]
                    if trait == "narcissism" and narcissism == 0.0:
                        narcissism = 0.75
                    elif trait == "machiavellianism" and machiavellianism == 0.0:
                        machiavellianism = 0.65
                    elif trait == "psychopathy" and psychopathy == 0.0:
                        psychopathy = 0.55

        measured = bool(evidence_quotes) and any(
            t > 0.0 for t in (narcissism, machiavellianism, psychopathy)
        )
        exploitability = round(max(narcissism, machiavellianism, psychopathy) * 0.8, 2) if measured else 0.0

        return DarkTriadProfile(
            machiavellianism=machiavellianism,
            narcissism=narcissism,
            psychopathy=psychopathy,
            exploitability=exploitability,
            theme_analysis=themes,
            trait_scores_measured=measured,
            evidence_quotes=evidence_quotes,
        )

    def generate_strategy(self, profile: DarkTriadProfile) -> Dict:
        if all(getattr(profile, t, 0.0) == 0.0 for t in ("machiavellianism", "narcissism", "psychopathy")):
            # Hiç gözlemlenebilir işaret yok; strateji ÜRETİLMEZ.
            return {'vector': 'unavailable', 'tactic': 'Gözlemlenebilir karanlık üçlü işareti bulunamadı.'}
        if profile.narcissism > 0.7:
            return {'vector': 'mirroring', 'tactic': 'Özel ve seçilmiş hissettir'}
        elif profile.machiavellianism > 0.6:
            return {'vector': 'alliance', 'tactic': 'Karşılıklı çıkar vurgusu'}
        elif profile.psychopathy > 0.5:
            return {'vector': 'thrill', 'tactic': 'Risk ve heyecan'}
        # Kısmi işaretler var ama eşik geçilmedi: yine de empathy UYDURMA;
        # strateji belirsiz işaretlenir ki aşağı akışta kanıt sayılmasın.
        return {'vector': 'unobserved', 'tactic': 'İşaretler eşiğin altında; strateji türetilmedi.'}

    def strategy_from_depth(self, depth: Dict) -> Dict:
        """GÖREV 2 artığı: derinlik-motoru yapısal indekslerinden strateji.

        Eşikler tasarım kararıdır (test-kilitli); öncelik mirroring >
        alliance > thrill. verdict != ok ise 'unavailable'; eşik-altı ok
        ise 'unobserved'. TOTAL: bozuk şekilde çökmez, sinyal anlık
        görüntüsü 'signal' altında denetime açık taşınır.
        """
        nope = {'vector': 'unavailable',
                'tactic': 'Gözlemlenebilir karanlık üçlü işareti bulunamadı.'}
        if not isinstance(depth, dict) or depth.get("verdict") != "ok":
            return dict(nope, source="psychodynamic_depth", signal=None)
        channels = depth.get("channels")
        if not isinstance(channels, dict):
            return dict(nope, source="psychodynamic_depth", signal=None)
        decl = channels.get("declaration")
        rhythm = channels.get("rhythm")
        dsig = decl.get("signals") if isinstance(decl, dict) else None
        rsig = rhythm.get("signals") if isinstance(rhythm, dict) else None
        dsig = dsig if isinstance(dsig, dict) else {}
        rsig = rsig if isinstance(rsig, dict) else {}
        kinds = rsig.get("rupture_kinds")
        kinds = list(kinds) if isinstance(kinds, list) else []
        n_rup = rsig.get("n_ruptures")
        reaction = depth.get("reaction_formation_index")
        repetition = dsig.get("repetition_score")
        signal = {"reaction_formation_index": reaction,
                  "repetition_score": repetition,
                  "n_ruptures": n_rup,
                  "rupture_kinds": kinds}

        def _num(v):
            return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None

        reaction_n, repetition_n = _num(reaction), _num(repetition)
        ruptured = (
            (isinstance(n_rup, int) and not isinstance(n_rup, bool) and n_rup >= 1)
            or "entropy_jump" in kinds
        )
        if reaction_n is not None and reaction_n >= DEPTH_MIRRORING_REACTION:
            return {'vector': 'mirroring',
                    'tactic': 'Savunulan benlik idealini ve vitrini aynala',
                    'source': 'psychodynamic_depth', 'signal': signal}
        if repetition_n is not None and repetition_n >= DEPTH_ALLIANCE_REPETITION:
            return {'vector': 'alliance',
                    'tactic': 'Kompülsif tekrar döngüsüne uyumlu öngörülebilir ortak çıkar',
                    'source': 'psychodynamic_depth', 'signal': signal}
        if ruptured:
            return {'vector': 'thrill',
                    'tactic': 'Faz kırılması ve volatiliteye uyumlu risk',
                    'source': 'psychodynamic_depth', 'signal': signal}
        return {'vector': 'unobserved',
                'tactic': 'İşaretler eşiğin altında; strateji türetilmedi.',
                'source': 'psychodynamic_depth', 'signal': signal}
