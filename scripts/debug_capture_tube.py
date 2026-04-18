import asyncio
from playwright.async_api import async_playwright
import os

async def capture_tube():
    url = "http://localhost:9002/video-learning"
    filename = "static/images/debug_tube_capture.png"
    
    # Ensure directory exists
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    
    async with async_playwright() as p:
        print(f"🚀 Launching browser to capture {url}...")
        browser = await p.chromium.launch()
        # Use a mobile-like viewport to see the "Shorts" layout better
        page = await browser.new_page(viewport={"width": 1080, "height": 1920})
        
        try:
            await page.goto(url, wait_until="networkidle", timeout=15000)
            # Wait for thumbnails to render
            await asyncio.sleep(3)
            await page.screenshot(path=filename, full_page=True)
            print(f"✅ Captured! Saved to {filename}")
        except Exception as e:
            print(f"❌ Failed: {e}")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(capture_tube())
