"""[DEPO DIŞI · ARŞİV] Sabit (fixture) girdilerle uçtan uca koşu.

Gerçek ağ yerine yerel fixture'lar ve (varsa) ``.pineal_vault.json`` kullanır;
``snapshot_handler`` ile anlık görüntüleri toplar. Canlı anahtar gerektirmez,
ancak canlı LLM kapısı (``LIVE_LLM_E2E``) yine açılmalıdır.
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from datetime import datetime

# Repo kök dizinini sys.path'e ekle
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from agent_core.task_executor import PinealExecutor
from agent_core.aspasia.aspasia_chief import AspasiaChief
from agent_core.domain.memory_models import TaskSnapshot

os.environ['LIVE_LLM_E2E'] = '1'

vault_data = {}
if os.path.exists('.pineal_vault.json'):
    try:
        with open('.pineal_vault.json', 'r', encoding='utf-8') as f:
            vault_data = json.load(f)
    except Exception as e:
        print(f'Vault load warning: {e}')

snapshots_log = []

def snapshot_handler(s: TaskSnapshot):
    snapshots_log.append({
        'task_id': s.task_id,
        'status': s.status,
        'current_agent': s.current_agent,
        'planned': list(s.planned_agents),
        'completed': list(s.completed_agents),
        'halted_reason': s.halted_reason,
        'runs_count': len(s.agent_runs),
        'runs_summary': {k: {'status': v.status, 'confidence': v.confidence} for k, v in s.agent_runs.items()}
    })

async def run_fixture_test():
    print('=== [PINEAL-HERETIC] ADIM 5: E2E FIXTURE & SNAPSHOT TESTI ===')
    
    logs = []
    def log_cb(lvl, msg):
        logs.append(f'[{lvl}] {msg}')
        print(f'  LOG [{lvl}]: {msg}')

    executor = PinealExecutor(
        log_callback=log_cb,
        snapshot_callback=snapshot_handler
    )

    api_key = vault_data.get('api_key') or os.getenv('OPENROUTER_API_KEY')
    if api_key:
        executor.llm_gateway.set_key(api_key)
    
    tavily = vault_data.get('tavily_key')
    serpapi = vault_data.get('serpapi_key')
    exa = vault_data.get('exa_key')
    if tavily or serpapi or exa:
        executor.search_engine.set_keys(tavily=tavily, serpapi=serpapi, exa=exa)

    fixture_input = {
        'target_url': 'https://instagram.com/fixture_user',
        'target_profile': {
            'bio': 'Kurucu & Stratejist. Soguk gercekler, kesintisiz disiplin. Yalnizlik bir zayiflik degil, filtredir.',
            'posts': [
                'Zirvedeyken kimseye guvenemezsin. Herkes zayifligini arar.',
                'Gece 04:00. Sehir uyurken strateji kurmak tek luksum.',
                'Duygusal kararlar iflas getirir. Sadece sayilar ve mantik.'
            ],
            'images': []
        },
        'user_profile': {
            'bio': 'Sessiz analist. Insan davranislarini cozumler.',
            'posts': ['Maskelerin ardindaki gercegi gormek zordur ama imkansiz degil.']
        },
        'sacred_rules': '1. Ucuz numaralar yasak. 2. Asla dogrudan ovgu yapma. 3. Bosluk birak.'
    }

    task_id = f"test_e2e_{datetime.now().strftime('%H%M%S')}"
    print(f"\n[1] Gorev Baslatiliyor: {task_id}")
    
    try:
        final_status = await executor.execute_task(fixture_input, task_id=task_id)
        print(f'\n[2] Gorev Tamamlandi. Durum: {final_status.status}')
        print(f'  - Planlanan Ajanlar: {final_status.planned_agents}')
        print(f'  - Tamamlanan Ajanlar: {final_status.completed_agents}')
        print(f'  - Rezonans Skoru: {final_status.resonance_score}')
        print(f'  - Durdurma Nedeni: {final_status.halted_reason}')
        print(f'  - Uretilen Snapshot Sayisi: {len(snapshots_log)}')
        
        print('\n[3] AgentRun Kayitlari (Detayli Telemetri):')
        for name, run in final_status.agent_runs.items():
            print(f'  * [{name}] Durum: {run.status} | Guven: {run.confidence} | Baslangic: {run.started_at} | Bitis: {run.completed_at}')
            if run.error_message:
                print(f'    HATA/UYARI: {run.error_message}')
        
        print('\n[4] Aspasia Gozlemci Telemetri Cevirisi:')
        aspasia = AspasiaChief(llm_gateway=executor.llm_gateway)
        room_mock = {
            'executor': executor,
            'active_tasks': {task_id: final_status},
            'vault': {'or_key': bool(api_key)}
        }
        aspasia_summary = aspasia.build_telemetry_summary(room_mock)
        print('--- Aspasia Okudugu Yapilandirilmis Durum ---')
        print(aspasia_summary)
        print('---------------------------------------------')
        
        assert len(snapshots_log) > 0, 'HATA: Hic snapshot uretilmedi!'
        assert len(final_status.agent_runs) > 0, 'HATA: AgentRun nesneleri bos!'
        assert final_status.status in ['completed', 'halted_frequency', 'halted_evidence'], f'Beklenmeyen durum: {final_status.status}'
        print('\n>>> [SONUC] ADIM 5 FIXTURE TESTI BASARIYLA GECTI. <<<')
        return True

    except Exception as e:
        import traceback
        print(f'\n[HATA] Test sirasinda istisna olustu: {type(e).__name__}: {e}')
        traceback.print_exc()
        return False

if __name__ == '__main__':
    success = asyncio.run(run_fixture_test())
    sys.exit(0 if success else 1)
