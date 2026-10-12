import asyncio
import sys
import logging
import os
from pathlib import Path

# Repo kök dizinini sys.path'e ekle
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

os.environ["OPENROUTER_API_KEY"] = os.getenv("OPENROUTER_API_KEY", "YOUR_API_KEY_HERE")
os.environ["LIVE_LLM_E2E"] = "1"

logging.basicConfig(level=logging.DEBUG, format='%(name)s - %(levelname)s - %(message)s')

from agent_core.task_executor import executor

# Bu dosya elle çalıştırılan canlı bir LLM script'idir (python scripts/e2e_test.py);
# pytest'in 'test' fonksiyonunu test sanıp toplamasını engelle.
__test__ = False

async def test():
    input_data = {
        'target_profile': {
            'username': 'cyber_strategist', 
            'bio': 'Teknoloji mimarı, sistem düşünürü ve açık kaynak savunucusu. Mükemmeliyetçi bir yapım var, karmaşık algoritmaları ve stratejik satranç hamlelerini koda dönüştürmeyi severim. Her şeyin kontrol altında olduğu, düzenli ve tıkır tıkır işleyen sistemler tasarlamak en büyük tutkum.', 
            'posts': [
                'Yapay zeka modellerinin veri setlerindeki önyargıları temizlemek, sıfırdan model eğitebilmek kadar kritik. Kontrolü hiçbir zaman kara kutulara bırakamayız.', 
                'Bu hafta sonu 15 kilometrelik doğa yürüyüşünde beynimi tamamen sıfırladım. Doğanın kusursuz matematiği ve sessizliği, şehirdeki kaosun en iyi panzehiri.',
                'Oyunu bilen kazanır: Bugün takım için yazdığım yeni mikroservis mimarisi, sunucu maliyetlerini %40 düşürdü. Zarafet, sadelikte gizlidir.',
                'Gece yarısı kahve eşliğinde kod yazmanın yerini hiçbir şey tutamaz. Sessizlik, sadece sen ve ekrandaki mantık zinciri.'
            ]
        },
        'user_profile': {
            'rituals': ['gece yarısı filtre kahve', 'sabah meditasyonu', 'pazar koşusu'], 
            'music': 'klasik müzik, dark ambient', 
            'envies': 'tamamen bağımsız ve izole bir yaşam',
            'private_rituals': ['pomodoro tekniği ile odaklanmak', 'kodları kağıda çizerek tasarlamak'],
            'late_night_playlist': ['Hans Zimmer', 'Blade Runner OST']
        },
        'visual_evidence': {
            'detected_objects': ['lüks mekanik klavye', 'çift monitör', 'kahve fincanı', 'orman manzarası', 'satranç tahtası']
        },
        'desired_action': 'detaylı analiz',
        'target_beliefs': ['sistemler kusursuz olmalıdır', 'kontrol her zaman elde tutulmalı'],
        'sacred_rules': ['asla varsayımda bulunma, veriye güven']
    }
    task_id = 'e2e_full_pipeline'
    
    # Run pipeline
    print("Executing pipeline with live LLM...")
    status = await executor.execute_task(input_data, task_id)
    
    import json
    print(json.dumps({
        'status': status.status,
        'halted_reason': getattr(status, 'halted_reason', None),
        'failed_runs': {name: run.model_dump() for name, run in getattr(status, 'agent_runs', {}).items() if run.status == 'halted' or run.status == 'failed'},
        'shadow_profile': getattr(status, 'shadow_profile', None),
        'osint_footprint': getattr(status, 'osint_footprint', None),
    }, indent=2, ensure_ascii=False, default=str))

if __name__ == "__main__":
    asyncio.run(test())
