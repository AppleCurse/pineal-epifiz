"""Dil kalıpları motoru — gömülü komut ve varsayım (presupposition) üretimi.

``EmbeddedCommandEngine`` hedefin temsil sistemi (görsel/işitsel/dokunsal) ve
profili üzerinden sıralı bir pace–komut–kapanış akışı kurar;
``PresuppositionEngine`` verilen inançlardan varsayım zinciri üretir.

Bu modül ETİK SINIRIN altındadır: manipülasyon değil, yalnız ifade biçimi
üretir; çıktılar ``shadow_executor`` içinde "öneri" olarak taşınır ve kanıt
yoksa hiç üretilmez.

Test: ``tests/unit/test_dark_nlp_and_shadow.py``.
"""

from typing import List, Dict
import re

class EmbeddedCommandEngine:
    TRIGGER_PATTERNS = {
        'visual': ['gör', 'bak', 'fark et', 'imgele', 'hayal et'],
        'auditory': ['dinle', 'duy', 'ses', 'yankılan'],
        'kinesthetic': ['hisset', 'deneyimle', 'dokun', 'ağır']
    }
    
    def generate_sequence(self, target_profile: Dict, desired_action: str) -> List[Dict]:
        """Generate cues only when source text and a detectable cue exist."""
        if not isinstance(target_profile, dict) or not isinstance(desired_action, str):
            return []
        if not desired_action.strip():
            return []
        dominant = self._detect_rep_system(target_profile)
        if dominant == "unknown":
            return []

        return [
            {'phase': 'pace', 'text': self._generate_pace(target_profile, dominant)},
            {'phase': 'command', 'text': self._embed_command(desired_action, dominant)},
            {'phase': 'closure', 'text': self._generate_closure(dominant)}
        ]

    def _detect_rep_system(self, profile: Dict) -> str:
        posts = profile.get('posts', [])
        if isinstance(posts, str):
            posts = [posts]
        if not isinstance(posts, (list, tuple)):
            posts = []
        bio = profile.get('bio', '')
        if not isinstance(bio, str):
            bio = ''
        text = ' '.join([str(post) for post in posts if post] + [bio]).strip()
        if not text:
            return "unknown"
        scores = {
            system: sum(len(re.findall(rf'\b{re.escape(word)}', text, re.I)) for word in words)
            for system, words in self.TRIGGER_PATTERNS.items()
        }
        if not scores or max(scores.values()) <= 0:
            return "unknown"
        return max(scores, key=scores.get)

    def _embed_command(self, action: str, system: str) -> str:
        templates = {
            'visual': f"O anı gördüğünde, {action} ve bunu fark edeceksin...",
            'auditory': f"Bu sesi duyduğunda, {action} ve yankılanacak...",
            'kinesthetic': f"O hissi aldığında, {action} ve bedenin hatırlayacak..."
        }
        return templates.get(system, templates['kinesthetic'])
    
    def _generate_pace(self, profile: Dict, system: str) -> str:
        return (
            f"Sağlanan metinde {system} türünde anahtar ifadeler var; "
            "bu tek başına kişinin bilişsel tarzını kanıtlamaz."
        )
    
    def _generate_closure(self, system: str) -> str:
        closures = {
            'visual': "Bu imge kaybolurken...",
            'auditory': "Bu ses sessizleşirken...",
            'kinesthetic': "O his hafiflerken..."
        }
        return closures.get(system, closures['kinesthetic'])


class PresuppositionEngine:
    TEMPLATES = {
        'existence': "O {X} kişisi...",
        'time': "Yine {X} yapıyorsun...",
        'awareness': "Bildiğin gibi {X}...",
        'causation': "{X} yapınca {Y} olur...",
        'identity': "Sen {X} birisin..."
    }
    
    def generate_chain(self, beliefs: List[str]) -> List[Dict]:
        chain = []
        types = list(self.TEMPLATES.keys())
        
        for i, belief in enumerate(beliefs[:5]):
            template = self.TEMPLATES[types[i % len(types)]]
            sentence = template.replace("{X}", belief).replace("{Y}", "fark edeceksin")
            if i > 0:
                sentence = f"Ve tabii ki, {sentence}, bu da {beliefs[i-1]} demek..."
            chain.append({'type': types[i % len(types)], 'sentence': sentence})
        
        return chain
