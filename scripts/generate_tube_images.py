#!/usr/bin/env python3
"""
Generate and Save high-quality thumbnail images for OnuiTube videos.
Using Gemini Image Generation with correct model name.
"""

import os
import sys
import json
import asyncio
import requests
import shutil
import base64
from pathlib import Path
from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Ensure correct model name is used for Gemini Image Generation
os.environ["GEMINI_IMAGE_MODEL"] = "gemini-2.0-flash-exp"

from backend.services.dalle_service import generate_image_gemini

# Load environment variables (will not override GEMINI_IMAGE_MODEL set above if already in environ)
load_dotenv()

TUBE_DATA_PATH = Path("data/onui-tube.json")
OUTPUT_DIR = Path("static/images/tube")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Detailed character and style description for consistency
CHARACTER_DESC = "A cute, friendly young Korean female character named 'Onui' with a bright smile, long black hair in a high ponytail, wearing stylish casual modern clothing."
STYLE_DESC = "3D digital illustration, vibrant colors, soft volumetric lighting, Pixar-style character design, educational and friendly atmosphere, soft pastel background."

async def generate_thumbnail(video_id, title, description):
    """Generate and save thumbnail using Gemini"""
    print(f"\n🎬 Processing: {title} ({video_id})")
    
    # Construct descriptive English prompt
    prompt = f"{STYLE_DESC} {CHARACTER_DESC} in a scene: '{description}'. Background is {title}. 4k, clean, educational, no text."
    
    print(f"   Prompt: {prompt[:80]}...")
    
    # Try Gemini directly
    print(f"   Generating with Gemini Image ({os.environ['GEMINI_IMAGE_MODEL']})...")
    result = await generate_image_gemini(prompt, save_locally=False)
        
    if result.get("success"):
        dest_path = OUTPUT_DIR / f"{video_id}.png"
        
        # Handle base64 from Gemini
        if result.get("image_base64"):
            img_data = base64.b64decode(result["image_base64"])
            with open(dest_path, "wb") as f:
                f.write(img_data)
            print(f"   ✅ Image saved (from base64): {dest_path}")
            return f"/static/images/tube/{video_id}.png"
            
        # Handle URL from Gemini if provided
        image_url = result.get("image_url")
        if image_url:
            try:
                resp = requests.get(image_url, timeout=30, stream=True)
                if resp.status_code == 200:
                    with open(dest_path, 'wb') as f:
                        shutil.copyfileobj(resp.raw, f)
                    print(f"   ✅ Image saved (downloaded): {dest_path}")
                    return f"/static/images/tube/{video_id}.png"
            except Exception as e:
                print(f"      ❌ Download failed: {e}")
                
    print(f"   ❌ Generation failed: {result.get('error')}")
    return None

async def main():
    if not TUBE_DATA_PATH.exists():
        print("❌ tube data not found")
        return

    with open(TUBE_DATA_PATH, "r", encoding="utf-8") as f:
        videos = json.load(f)

    print(f"🚀 Generating thumbnails for {len(videos)} videos using Gemini {os.environ['GEMINI_IMAGE_MODEL']}...")

    for video in videos:
        new_url = await generate_thumbnail(video["id"], video["title"], video["description"])
        if new_url:
            video["poster_url"] = new_url
            # Save progress
            with open(TUBE_DATA_PATH, "w", encoding="utf-8") as f:
                json.dump(videos, f, ensure_ascii=False, indent=2)
        
        await asyncio.sleep(1)

    print("\n✨ Done!")

if __name__ == "__main__":
    asyncio.run(main())
