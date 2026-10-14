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
        dominant = self._detect_rep_system(target_profile)
        
        return [
            {'phase': 'pace', 'text': self._generate_pace(target_profile, dominant)},
            {'phase': 'command', 'text': self._embed_command(desired_action, dominant)},
            {'phase': 'closure', 'text': self._generate_closure(dominant)}
        ]
    
    def _detect_rep_system(self, profile: Dict) -> str:
        text = ' '.join(profile.get('posts', []) + [profile.get('bio', '')])
        scores = {sys: sum(len(re.findall(rf'\b{w}', text, re.I)) for w in words) 
                 for sys, words in self.TRIGGER_PATTERNS.items()}
        return max(scores, key=scores.get) if scores else 'kinesthetic'
    
    def _embed_command(self, action: str, system: str) -> str:
        templates = {
            'visual': f"O anı gördüğünde, {action} ve bunu fark edeceksin...",
            'auditory': f"Bu sesi duyduğunda, {action} ve yankılanacak...",
            'kinesthetic': f"O hissi aldığında, {action} ve bedenin hatırlayacak..."
        }
        return templates.get(system, templates['kinesthetic'])
    
    def _generate_pace(self, profile: Dict, system: str) -> str:
        return f"Sen {system} bir insansın, detayları {system} olarak işliyorsun..."
    
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
