"""Playwright duman testi — tarayıcı katmanı gerçekten açılıyor mu?

Chromium'u başlatır, ``https://example.com`` sayfasını yükler ve başlığı okur;
başarı/başarısızlık tek satır olarak basılır ve hata durumunda çıkış kodu 1'dir
(CI'da kullanılabilir). Analiz yapmaz — yalnız altyapı canlılığını ölçer.
"""

import asyncio
from playwright.async_api import async_playwright

async def main():
    print("Starting Playwright smoke test...")
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto("https://example.com")
            title = await page.title()
            print(f"Browser launched successfully! Page title: {title}")
            await browser.close()
            print("Smoke test PASSED \u2705")
    except Exception as e:
        print(f"Smoke test FAILED \u274c: {e}")
        exit(1)

if __name__ == "__main__":
    asyncio.run(main())
