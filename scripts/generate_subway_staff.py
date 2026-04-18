#!/usr/bin/env python3
"""
Generate a specific Subway Station Staff (역무원) image for Onui Idol.
Correcting path and ensuring generation.
"""

import os
import sys
import json
import asyncio
import requests
import base64
from pathlib import Path
from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.services.dalle_service import generate_image_dall_e, generate_image_gemini

# Load environment variables
load_dotenv()

# Ensure absolute path for script execution
ROOT_DIR = Path(__file__).parent.parent
OUTPUT_PATH = ROOT_DIR / "static/images/onui-idol-subway-staff.png"
TUBE_DATA_PATH = ROOT_DIR / "data/onui-tube.json"

PROMPT = (
    "A high-quality 3D digital illustration of a cute and friendly young Korean female character named Onui. "
    "She has long black hair tied in a high ponytail and a bright smile. "
    "She is wearing a professional South Korean subway station staff uniform (navy blue jacket, light blue shirt, and a small badge). "
    "She is standing inside a modern, clean Seoul subway station. "
    "Pixar-style character design, soft volumetric lighting, vibrant colors, 4k, no text."
)

async def main():
    print(f"🚀 Generating Subway Staff image...")
    
    # Force a known working model for Gemini if DALL-E fails
    # Most environments have gemini-1.5-flash or gemini-pro-vision
    os.environ["GEMINI_IMAGE_MODEL"] = "gemini-1.5-flash" 

    # Attempt DALL-E 3
    print("   Attempting DALL-E 3...")
    result = await generate_image_dall_e(prompt=PROMPT, save_locally=False)
    
    if not result.get("success"):
        print(f"   ⚠️ DALL-E 3 failed: {result.get('error')}. Attempting Gemini...")
        result = await generate_image_gemini(PROMPT, save_locally=False)
        
    if result.get("success"):
        saved = False
        if result.get("image_base64"):
            img_data = base64.b64decode(result["image_base64"])
            with open(OUTPUT_PATH, "wb") as f:
                f.write(img_data)
            saved = True
            print(f"   ✅ Image saved from base64 to {OUTPUT_PATH}")
        elif result.get("image_url"):
            try:
                resp = requests.get(result["image_url"], timeout=30)
                if resp.status_code == 200:
                    with open(OUTPUT_PATH, "wb") as f:
                        f.write(resp.content)
                    saved = True
                    print(f"   ✅ Image saved from URL to {OUTPUT_PATH}")
            except Exception as e:
                print(f"   ❌ Download failed: {e}")

        if saved:
            # Update JSON with the correct relative path for the web server
            if TUBE_DATA_PATH.exists():
                with open(TUBE_DATA_PATH, "r", encoding="utf-8") as f:
                    videos = json.load(f)
                
                for v in videos:
                    if v["id"] == "subway_navigation":
                        v["poster_url"] = "/static/images/onui-idol-subway-staff.png"
                        break
                
                with open(TUBE_DATA_PATH, "w", encoding="utf-8") as f:
                    json.dump(videos, f, ensure_ascii=False, indent=2)
                print(f"   ✅ Updated {TUBE_DATA_PATH}")
        else:
            print("   ❌ Image data received but failed to save.")
    else:
        print(f"   ❌ Generation failed: {result.get('error')}")

if __name__ == "__main__":
    asyncio.run(main())
