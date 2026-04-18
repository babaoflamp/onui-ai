#!/usr/bin/env python3
"""
Final attempt to generate a TRULY NEW image using DALL-E 3.
"""

import os
import sys
import json
import asyncio
import requests
from pathlib import Path
from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load environment
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OUTPUT_PATH = Path("static/images/onui-idol-subway-staff.png")
TUBE_DATA_PATH = Path("data/onui-tube.json")

# Detailed prompt
PROMPT = (
    "A 3D digital illustration of a cute young Korean female character 'Onui' with a ponytail. "
    "She is dressed as a South Korean subway station staff member with a navy blue uniform. "
    "Background is a modern Seoul subway platform. Pixar style, vibrant colors, 4k."
)

async def main():
    if not OPENAI_API_KEY:
        print("❌ OPENAI_API_KEY not found")
        return

    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY)
    
    print("🎬 Generating with DALL-E 3...")
    try:
        response = client.images.generate(
            model="dall-e-3",
            prompt=PROMPT,
            size="1024x1024",
            quality="standard",
            n=1,
        )
        
        image_url = response.data[0].url
        print(f"✅ SUCCESS! Image URL: {image_url}")
        
        # Download
        resp = requests.get(image_url, timeout=30)
        if resp.status_code == 200:
            with open(OUTPUT_PATH, "wb") as f:
                f.write(resp.content)
            print(f"✅ Image saved to {OUTPUT_PATH}")
            
            # Update JSON
            if TUBE_DATA_PATH.exists():
                with open(TUBE_DATA_PATH, "r", encoding="utf-8") as f:
                    videos = json.load(f)
                for v in videos:
                    if v["id"] == "subway_navigation":
                        v["poster_url"] = "/static/images/onui-idol-subway-staff.png"
                        break
                with open(TUBE_DATA_PATH, "w", encoding="utf-8") as f:
                    json.dump(videos, f, ensure_ascii=False, indent=2)
                print("✅ Updated onui-tube.json")
        else:
            print(f"❌ Failed to download: {resp.status_code}")
            
    except Exception as e:
        print(f"❌ DALL-E 3 Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
