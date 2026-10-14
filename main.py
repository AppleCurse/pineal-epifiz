"""Geliştirici demosu — yürütücüyü doğrudan çağıran en küçük koşu.

Örnek bir kullanıcı/hedef payload'ı ile ``PinealExecutor``'u çalıştırır, görev
durumunu, kanıt zinciri uzunluğunu ve üretilen mesajı basar. Amaç: API'yi
ayağa kaldırmadan boru hattını uçtan uca gözlemek.

Üretim girişi DEĞİLDİR (üretim yolu ``uvicorn backend.api:app``); sahte
girdiler burada yalnız gösterim amaçlıdır.
"""

import asyncio
from agent_core.task_executor import PinealExecutor
# Register pattern_interrupt dynamically
from agent_core.agents.pattern_interrupt import PatternInterrupt

async def main():
    executor = PinealExecutor()
    executor.agents['pattern_interrupt'] = PatternInterrupt()
    
    # Görev: Hedef profili analiz et ve mesaj üret
    task_input = {
        'user_profile': {
            'private_rituals': ['çay', 'kitap', 'neset_ertas'],
            'late_night_playlist': ['neşet ertaş - gönül dağı'],
            'secret_envies': ['derin bağlantılar', 'anlaşılmak'],
            'authenticity_score': 0.85
        },
        'target_profile': {
            'images': ['./target_photo_1.jpg', './target_photo_2.jpg'],
            'bio': "Hayatımı yaşıyorum 💫 Sadece pozitif enerji ✨",
            'posts': [
                "Cuma akşamı evdeyim yorgunum 😴",
                "Pazartesi motivasyonu! 💪",
                "Kimse anlamıyor beni..."
            ],
            'post_times': ['23:30', '08:00', '02:15']
        }
    }
    
    try:
        result = await executor.execute_task(task_input, task_id="op_001")
        print(f"Görev durumu: {result.status}")
        print(f"Kanıt zinciri: {len(result.evidence_chain)} adım")
        
        # Son adım: Mesaj
        # 360° zincirinde son ajan resonance_synthesizer'dir (AuthenticBridge şeması);
        # mesaj önce oradan, yoksa pattern_interrupt kanıtından çıkar.
        final_message = ""
        hp = getattr(result, "holistic_profile", None)
        if hp is not None and getattr(hp, "bridge", None) is not None:
            final_message = (hp.bridge.suggested_opening_message or "").strip()
        if not final_message:
            for item in result.evidence_chain:
                if item.get("agent") == "pattern_interrupt":
                    final_message = (item.get("result", {}).get("message") or "").strip()
                    break
        if final_message:
            print(f"\nÜretilen mesaj:\n{final_message}")
        else:
            print("\nÜretilen mesaj: (üretilmedi — görev tamamlanmadan durdu)")
            
    except Exception as e:
        print(f"Sistem hatası: {e}")
        # Hata gizlenmez, loglanır, yukarı iletilir

if __name__ == "__main__":
    asyncio.run(main())
