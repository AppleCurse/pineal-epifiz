"""[DEPO DIŞI · ARŞİV] Görsel indirme gecikme ölçümü.

Yürütücünün ``_download_images`` yolunu gecikmeli uçlarla (httpbin delay)
koşup toplam süreyi ölçer. Yalnız performans tanısı içindir; ağ erişimi
gerektirir, CI'da koşmaz.
"""

import asyncio
import time
import sys
from pathlib import Path

# Repo kök dizinini sys.path'e ekle
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from agent_core.task_executor import PinealExecutor

async def run_benchmark():
    executor = PinealExecutor()
    # Use a delay endpoint to simulate network latency (e.g. 1 second delay per request)
    urls = [
        "https://httpbin.org/delay/1",
        "https://httpbin.org/delay/1"
    ]
    
    print("Starting download benchmark...")
    start_time = time.time()
    paths = await executor._download_images(urls)
    end_time = time.time()
    
    elapsed = end_time - start_time
    print(f"Downloaded {len(paths)} images in {elapsed:.2f} seconds.")
    if elapsed < 1.5:
        print("✅ SUCCESS: Parallel execution is working! Time is ~1.2s instead of 2.0s+")
    else:
        print("❌ FAILED: Execution took too long, might still be serial.")

if __name__ == "__main__":
    asyncio.run(run_benchmark())
