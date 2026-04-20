#!/usr/bin/env python3
import os
import sys
import json
import asyncio
from pathlib import Path
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))
load_dotenv()

from backend.services.dalle_service import generate_image_gemini

DATA_PATH = Path("data/voice-call.json")

async def main():
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        scenarios = json.load(f)
        
    prompt = (
        "A high-quality 2D anime/webtoon style illustration of a beautiful young Korean female idol. "
        "She has long, lustrous jet-black hair with a soft, slightly off-center part, face-framing layers, and subtle natural waves at the ends. "
        "She has large, sparkling anime-style dark brown eyes and a cheerful smile. "
        "She is wearing a crisp white shirt and a black apron as a restaurant waiter. "
        "The background is an elegant, dimly lit upscale restaurant interior, slightly blurred. "
        "Bright, colorful, cel-shaded, masterpiece, highly detailed, cute and charming idol vibe."
    )
    
    print(f"🎬 Generating restaurant waiter image using Gemini (2D anime style)...")
    
    # generate_image_gemini sets model internally. If we need to force it, we can set GEMINI_IMAGE_MODEL env var before calling.
    os.environ["GEMINI_IMAGE_MODEL"] = "gemini-2.5-flash-image"
    
    result = await generate_image_gemini(prompt, save_locally=True)
    
    if result.get("success"):
        image_path = result.get("local_path")
        print(f"   ✅ SUCCESS! Image saved to: {image_path}")
        
        # We want to name it onui-idol-waiter.png
        # generate_image_gemini saves it as gemini_timestamp.png, so we can rename it.
        import shutil
        
        old_path = "." + image_path  # /uploads/... -> ./uploads/...
        new_filename = "onui-idol-waiter.png"
        new_path = f"static/images/{new_filename}"
        
        shutil.copy(old_path, new_path)
        print(f"   ✅ Copied image to {new_path}")
        
        # Update JSON
        updated = False
        for scenario in scenarios:
            if scenario["id"] == "restaurant":
                scenario["avatar_url"] = f"/static/images/{new_filename}"
                updated = True
                break
        
        if updated:
            with open(DATA_PATH, "w", encoding="utf-8") as f:
                json.dump(scenarios, f, ensure_ascii=False, indent=2)
                f.write('\n')
            print("✅ Updated data/voice-call.json")
            
    else:
        print(f"   ❌ Failed to generate image: {result.get('error')}")

if __name__ == "__main__":
    asyncio.run(main())
