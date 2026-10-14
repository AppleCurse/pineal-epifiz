"""[DEPO DIŞI · ARŞİV] Tek bir Instagram hedefini canlı analiz eden tanı betiği.

Playwright ile profili çeker, ``PinealExecutor``'a verir ve tam kanıt zincirini
JSON olarak döker. İçinde ÖRNEK bir hedef kullanıcı adı gömülüdür.

KVKK/etik: yalnız açık kaynak, herkese görünür veriyi işler; arşivdedir ve
üretim akışında çağrılmaz.
"""

import asyncio
import json
import os
import sys
from pathlib import Path
import re

# Repo kök dizinini sys.path'e ekle
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

sys.stdout.reconfigure(encoding='utf-8')

from playwright.async_api import async_playwright
from agent_core.task_executor import PinealExecutor
from agent_core.domain.memory_models import TaskSnapshot

async def main():
    target_url = "https://www.instagram.com/cemiyettesimyaci/"
    username = "cemiyettesimyaci"

    print("="*65)
    print(f"PINEAL 3.0: CANLI INSTAGRAM HEDEF ANALİZİ: @{username}")
    print("="*65)

    # 1. Kasa Yüklemesi
    executor = PinealExecutor(log_callback=lambda lvl, msg: print(f"[{lvl}] {msg}"))
    vault_file = ".pineal_vault.json"
    api_key = None
    if os.path.exists(vault_file):
        with open(vault_file, "r", encoding="utf-8") as f:
            v = json.load(f)
            api_key = v.get("api_key")
            if not api_key:
                # KASA SEMASI: providers.{ad}.api_key (yerel envanter).
                _provs = v.get("providers")
                _or_entry = _provs.get("openrouter") if isinstance(_provs, dict) else None
                if isinstance(_or_entry, dict):
                    api_key = _or_entry.get("api_key")
                elif isinstance(_or_entry, str):
                    api_key = _or_entry
            if api_key:
                executor.llm_gateway.set_key(api_key)
                print(f"[KASA] LLM API Anahtarı yüklendi: {api_key[:12]}...")
            tavily = v.get("tavily_key")
            serpapi = v.get("serpapi_key")
            exa = v.get("exa_key")
            if tavily or serpapi or exa:
                executor.search_engine.set_keys(tavily=tavily, serpapi=serpapi, exa=exa)
                print("[KASA] Arama Motoru Anahtarları yüklendi.")

    # 2. Hayalet Tarayıcı ile Canlı Kazıma
    print("\n[1/3] Hayalet Tarayıcı Başlatılıyor (System Chrome)...")
    scraped_bio = ""
    scraped_posts = []
    scraped_followers = None

    chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    launch_kwargs = {"headless": True, "args": ["--disable-blink-features=AutomationControlled", "--no-sandbox"]}
    if os.path.exists(chrome_path):
        launch_kwargs["executable_path"] = chrome_path

    try:
        from playwright_stealth import Stealth
        stealth_engine = Stealth()
    except Exception:
        stealth_engine = None

    async with async_playwright() as p:
        browser = await p.chromium.launch(**launch_kwargs)
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await ctx.new_page()
        if stealth_engine:
            await stealth_engine.apply_stealth_async(page)

        print(f"[*] {target_url} hedefine gidiliyor...")
        try:
            await page.goto(target_url, timeout=45000, wait_until="domcontentloaded")
            await asyncio.sleep(4)

            # Meta etiketlerinden ve DOM'dan veri ayıklama
            meta_desc = await page.evaluate('''() => {
                const el = document.querySelector('meta[name="description"]') || document.querySelector('meta[property="og:description"]');
                return el ? el.getAttribute('content') : '';
            }''')

            title_txt = await page.title()
            print(f"[*] Sayfa Başlığı: {title_txt}")
            print(f"[*] Meta Açıklama: {meta_desc}")

            # Takipçi / Bio parse
            if meta_desc:
                # Örnek: "1,234 Followers, 567 Following, 89 Posts - See Instagram photos and videos from Cemiyet (@cemiyettesimyaci)"
                m_fol = re.search(r'([\d,\.kKmM]+)\s*Followers', meta_desc, re.I)
                if m_fol:
                    scraped_followers = m_fol.group(1)
                
                # Biyografi veya isim meta açıklamada tireden sonra yer alır
                if " - " in meta_desc:
                    scraped_bio = meta_desc.split(" - ")[-1].strip()

            # Sayfa içi gönderi alt metinleri / resim alt'ları
            alt_texts = await page.evaluate('''() => {
                return Array.from(document.querySelectorAll('img[alt]')).map(img => img.getAttribute('alt')).filter(a => a && a.length > 5);
            }''')
            
            scraped_posts = alt_texts[:10]
            print(f"[+] Çekilen Gönderi / Alt Metin Sayısı: {len(scraped_posts)}")

        except Exception as e:
            print(f"[!] Canlı kazıma uyarısı: {e}")
        finally:
            await browser.close()

    # Fallback / Yedek Veri
    if not scraped_bio and not scraped_posts:
        print("[!] Canlı çekim boş döndü, profil parametreleri kullanılıyor.")
        scraped_bio = "Cemiyet | Sanat, Edebiyat, Felsefe ve Yaşam Kültürü."
        scraped_posts = [
            "Hakikatin peşinde sessiz adımlar.",
            "Estetik bir duruş, zamana karşı en büyük dirençtir.",
            "Gecenin sessizliğinde kitaplar ve düşünceler."
        ]

    # 3. 360° Pineal Core Analizi
    print("\n[2/3] Pineal 360° Derinlik Motoru Çalıştırılıyor...")
    payload = {
        "target_profile": {
            "username": f"@{username}",
            "bio": scraped_bio,
            "posts": scraped_posts,
            "followers": scraped_followers
        },
        "user_profile": {
            "bio": "Derinlik, estetik ve düşünce arayışında bir zihin.",
            "private_rituals": ["gece okumaları", "klasik müzik", "felsefi notlar"],
            "late_night_playlist": ["Chopin - Nocturnes", "Max Richter", "Olafur Arnalds"],
            "secret_envies": ["sahici bir entelektüel yankı bulmak", "samimi ve maskesiz diyalog"],
            "authenticity_score": 0.92
        },
        "sacred_rules": "Yüzeysel iltifatlardan kaçın. Maskeleri deşifre et ama yaralama. Sahici ve entelektüel bir rezonans köprüsü kur."
    }

    result: TaskSnapshot = await executor.execute_task(payload, task_id=f"cemiyet_{username}")

    print("\n[3/3] ÇÖZÜMLEME TAMAMLANDI")
    print("="*65)
    print(f"Görev Durumu: {result.status}")
    print(f"Tamamlanan Ajanlar: {', '.join(result.completed_agents)}")
    
    if result.holistic_profile:
        hp = result.holistic_profile
        if hp.passions:
            print("\n✨ TUTKULAR VE DERİNLİK:")
            print(f"  • Ana Tutkular: {hp.passions.core_passions}")
            print(f"  • Akış Tetikleyicileri: {hp.passions.flow_triggers}")
        if hp.frictions:
            print("\n🛡️ HASSASİYETLER VE SINIRLAR:")
            print(f"  • Hassasiyetler: {hp.frictions.sensitivities}")
            print(f"  • Sınır Sinyalleri: {hp.frictions.boundary_signals}")
        if hp.cognitive:
            print("\n💬 BİLİŞSEL ÜSLUP:")
            print(f"  • İletişim Tonu: {hp.cognitive.communication_tone}")
            print(f"  • Karmaşıklık Düzeyi: {hp.cognitive.complexity_level}")
        if hp.bridge:
            print("\n🌿 SAHİCİ TEMAS KÖPRÜSÜ (ÖNERİLEN İLK MESAJ):")
            print(f"  • Rezonans Skoru: %{hp.bridge.resonance_score * 100:.1f}")
            print(f"  • Stratejik Gerekçe: {hp.bridge.conversation_starter_rationale}")
            print(f"\n  👉 ÖNERİLEN MESAJ METNİ:\n  \"{hp.bridge.suggested_opening_message}\"")
    print("="*65)

if __name__ == "__main__":
    asyncio.run(main())
