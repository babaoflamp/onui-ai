import asyncio
from playwright.async_api import async_playwright
import os


async def capture_screenshots():
    routes = [
        "/",
        "/video-learning",
        "/onui-beats",
        "/voice-call",
        "/onui-messenger",
        "/content-generation",
        "/daily-expression",
        "/folktales",
        "/signup",
        "/login",
        "/mypage",
        "/learning-progress",
        "/dashboard",
        "/speechpro-practice",
        "/roleplay",
        "/sitemap",
        "/stt-api-test",
        "/api-test",
        "/change-password",
        "/admin/login",
        "/admin",
        "/admin/dashboard",
        "/admin/users",
        "/admin/api",
        "/admin/system",
        "/admin/logs",
        "/admin/settings",
    ]

    base_url = "http://localhost:9002"

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()

        # Set viewport size to a standard desktop resolution
        await page.set_viewport_size({"width": 1280, "height": 800})

        for route in routes:
            url = f"{base_url}{route}"
            filename = f"screenshots/{route.replace('/', '_') or 'index'}.png"
            print(f"Capturing {url} -> {filename}")
            try:
                await page.goto(url, wait_until="networkidle", timeout=10000)
                # Wait a bit for any dynamic content to load
                await asyncio.sleep(1)
                await page.screenshot(path=filename)
            except Exception as e:
                print(f"Failed to capture {url}: {e}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(capture_screenshots())
