"""[DEPO DIŞI · ARŞİV] Canlı 360° bütüncül analiz koşusu.

Gerçek sağlayıcı anahtarı + ``LIVE_LLM_E2E=1`` ile ``PinealExecutor``'u koşar ve
bütüncül profili konsola döker; üretim yolu değildir, tanı amaçlı tutulur
(bkz. ``scripts/archive/README.md``).

Ağ erişimi ve canlı model gerektirir; CI'da koşmaz.
"""

import asyncio
import json
import os
import sys
from pathlib import Path

# Repo kök dizinini sys.path'e ekle
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

sys.stdout.reconfigure(encoding='utf-8')

from agent_core.task_executor import PinealExecutor
from agent_core.domain.memory_models import TaskSnapshot

async def main():
    print("=================================================================")
    print("360° BÜTÜNCÜL İNSAN TANIMA MOTORU - CANLI ÇÖZÜMLEME TESTİ")
    print("=================================================================")

    executor = PinealExecutor(
        log_callback=lambda lvl, msg: print(f"[{lvl}] {msg}")
    )

    # API Anahtarını doğrula (.pineal_vault.json veya env)
    vault_file = ".pineal_vault.json"
    if os.path.exists(vault_file):
        with open(vault_file, "r", encoding="utf-8") as f:
            v = json.load(f)
            api_key = v.get("api_key")
            if api_key:
                executor.llm_gateway.set_key(api_key)
                print(f"[KASA] API Anahtarı yüklendi: {api_key[:12]}...")
            tavily = v.get("tavily_key")
            serpapi = v.get("serpapi_key")
            exa = v.get("exa_key")
            if tavily or serpapi or exa:
                executor.search_engine.set_keys(tavily=tavily, serpapi=serpapi, exa=exa)
                print("[KASA] Arama Motoru Anahtarları yüklendi (Tavily/SerpAPI/Exa).")

    # Gerçek, Doğrulanabilir Profil (@refikanadol)
    payload = {
        "target_profile": {
            "username": "@refikanadol",
            "bio": "Refik Anadol. Media Artist, Director, Pioneer in AI Art & Data Aesthetics. Studio in Los Angeles. Dataland.",
            "posts": [
                "Artificial Realities: Coral at Serpentine Galleries London. Generative AI exploring nature and collective memories.",
                "Living Architecture: Casa Batlló at UNESCO World Heritage site Barcelona. Data sculptures blending physical and virtual spaces.",
                "Sense of Space: Exploring immersive media, architectural memory, and generative data sculptures."
            ]
        },
        "user_profile": {
            "bio": "Veri felsefesi ve dijital mimarlık araştırmacısı. Yapay zeka ile hafıza ilişkisi üzerine çalışıyorum.",
            "posts": [
                "Mekanların ve dijital verinin kolektif hafızadaki yeri.",
                "Algoritmik estetik ile insan algısının kesişimi."
            ],
            "private_rituals": ["gece veri görselleştirme eskizleri", "ambient elektronik dinleme", "felsefe okumaları"],
            "late_night_playlist": ["brian eno - ambient", "max richter", "nils frahm"],
            "secret_envies": ["veriyi yaşayan bir mimariye dönüştürebilmek", "sahici ve derin kavramsal diyalog kurmak"],
            "authenticity_score": 0.95
        },
        "sacred_rules": "Ucuz manipülasyon veya klişe iltifatlardan kaçın. Karşı tarafın sınırlarına ve kavramsal derinliğine saygılı, sahici ve entelektüel bir temas köprüsü kur."
    }

    print("\n[HEDEF PROFİL]: @refikanadol")
    print(f"Bio: {payload['target_profile']['bio']}")
    print(f"Gönderiler ({len(payload['target_profile']['posts'])} adet):")
    for p in payload['target_profile']['posts']:
        print(f" - {p}")

    print("\n--- PİPELİNE ÇALIŞTIRILIYOR ---")
    result: TaskSnapshot = await executor.execute_task(payload, task_id="live_test_360_001")

    print("\n--- ÇÖZÜMLEME SONUCU ---")
    print(f"Görev Durumu: {result.status}")
    print(f"Tamamlanan Ajanlar: {', '.join(result.completed_agents)}")
    
    if result.holistic_profile:
        hp = result.holistic_profile
        print("\n" + "="*50)
        print("🧠 360° BÜTÜNCÜL İNSAN PROFİLİ RAPORU")
        print("="*50)
        
        if hp.passions:
            print("\n✨ TUTKULAR VE NEŞE:")
            print(f"  • Ana Tutkular: {hp.passions.core_passions}")
            print(f"  • Enerji Veren Konular: {hp.passions.energizing_topics}")
            print(f"  • Akış Tetikleyicileri: {hp.passions.flow_triggers}")
            print(f"  • Duygu Durumu (Polarite): {hp.passions.sentiment_polarity}")
            print(f"  • Kanıt Alıntıları: {hp.passions.evidence_quotes}")

        if hp.frictions:
            print("\n🛡️ HASSASİYETLER VE SINIRLAR:")
            print(f"  • Hassasiyetler: {hp.frictions.sensitivities}")
            print(f"  • Yorulma/Stres Noktaları: {hp.frictions.stress_triggers}")
            print(f"  • İletişim Sınırları: {hp.frictions.boundary_signals}")
            print(f"  • Kanıt Alıntıları: {hp.frictions.evidence_quotes}")

        if hp.cognitive:
            print("\n💬 BİLİŞSEL VE İLETİŞİM ÜSLUBU:")
            print(f"  • İletişim Tonu: {hp.cognitive.communication_tone}")
            print(f"  • Karmaşıklık Düzeyi: {hp.cognitive.complexity_level}")
            print(f"  • Mizah Tarzı: {hp.cognitive.humor_style}")
            print(f"  • Sosyal Yaklaşım: {hp.cognitive.social_orientation}")

        if hp.bridge:
            print("\n🌿 SAHİCİ İLETİŞİM KÖPRÜSÜ (ÖNERİLEN İLK TEMAS):")
            print(f"  • Rezonans Skoru: %{hp.bridge.resonance_score * 100:.1f}")
            print(f"  • Ortak Heyecanlar: {hp.bridge.shared_passions}")
            print(f"  • Tamamlayıcı Perspektifler: {hp.bridge.complementary_perspectives}")
            print(f"  • Önerilen Başlangıç Konusu: {hp.bridge.authentic_opening_topic}")
            print(f"  • Stratejik Gerekçe: {hp.bridge.conversation_starter_rationale}")
            print(f"\n  👉 ÖNERİLEN MESAJ METNİ:\n  \"{hp.bridge.suggested_opening_message}\"")
        print("="*50)
    else:
        print("[UYARI] Bütüncül profil oluşturulamadı.")

if __name__ == "__main__":
    asyncio.run(main())
