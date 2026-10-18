"""CLI kazıyıcı girişi — kasa kapısı KOMUT SATIRINDA da uygulanır.

``python -m agent_core.scraper.run_scraper <kullanıcı_adı>`` tek bir hedefin
profilini çeker ve JSON basar. API sınırının dışında kaldığı için ikinci
savunma buradadır: kasa kilitliyken tarayıcı HİÇ AÇILMAZ
(``vault_gate.require_open(strict=True)``), ret ``VAULT_LOCKED`` kodu ve
sıfırdan farklı çıkış koduyla bildirilir.

Kanıt yetersizse (``InsufficientEvidenceError``) hata JSON'u basılır; çıktı
asla "boş profil" gibi sahte bir başarıya dönüşmez.
"""

import sys
import os
import json
import asyncio

# Ensure agent_core is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from agent_core.scraper.instagram_ghost import InstagramGhostScraper, InsufficientEvidenceError
from agent_core.scraper.vault_gate import require_open
from playwright.async_api import async_playwright

async def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "No username provided"}))
        sys.exit(1)

    # [E-GÖZ2-3 · YAPRAK KAPI] Kasa kilitliyken tarayıcı HİÇ AÇILMAZ.
    # Bu CLI API sınırının dışındadır; ikinci savunma buradadır (Tüzük Md.4).
    try:
        require_open(purpose="scraper", strict=True)
    except Exception as exc:  # VaultLockedError dâhil — dürüst ret, iz bırakır
        print(json.dumps({"error": str(exc), "code": "VAULT_LOCKED"}))
        sys.exit(2)
        
    username = sys.argv[1] 
    
    # URL'den temizleme (örn https://www.instagram.com/hedef/ -> hedef)
    username = username.strip('/').split('/')[-1]
    
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            
            scraper = InstagramGhostScraper()
            try:
                profile = await scraper.scrape_async(username, playwright_page=page)
                print(profile.model_dump_json())
            except InsufficientEvidenceError as e:
                print(json.dumps({"error": str(e)}))
            finally:
                await browser.close()
                
    except Exception as e:
        print(json.dumps({"error": f"Beklenmeyen hata: {str(e)}"}))

if __name__ == "__main__":
    asyncio.run(main())
