#!/usr/bin/env python3
import os
import sys
import json
import asyncio
import shutil
from pathlib import Path
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))
load_dotenv()

from backend.services.dalle_service import generate_image_gemini

DATA_PATH = Path("data/voice-call.json")

PERSONA_PROMPTS = {
    "hotel": ("hotel concierge wearing a sharp, elegant suit", "A luxurious, grand hotel lobby with warm golden lighting, slightly blurred."),
    "taxi": ("taxi driver wearing a comfortable casual vest and a driving cap", "The interior of a modern taxi cab with city street lights visible outside the window, slightly blurred."),
    "shopping": ("fashion store clerk wearing trendy, stylish modern casual clothes", "A bright, high-end fashion boutique interior, slightly blurred."),
    "bank": ("bank teller wearing a neat, professional business suit", "A clean, modern bank interior with a service counter, slightly blurred."),
    "dutyfree": ("duty-free shop staff wearing a luxurious, elegant uniform", "A sparkling, luxurious duty-free shopping mall interior, slightly blurred.")
}

async def main():
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        scenarios = json.load(f)
        
    os.environ["GEMINI_IMAGE_MODEL"] = "gemini-2.5-flash-image"
    
    updated = False
    for sid, (persona_desc, bg_desc) in PERSONA_PROMPTS.items():
        prompt = (
            "A high-quality 2D anime/webtoon style illustration of a beautiful young Korean female idol. "
            "She has long, lustrous jet-black hair with a soft, slightly off-center part, face-framing layers, and subtle natural waves at the ends. "
            "She has large, sparkling anime-style dark brown eyes and a cheerful smile. "
            f"She is wearing a {persona_desc}. "
            f"The background is {bg_desc} "
            "Bright, colorful, cel-shaded, masterpiece, highly detailed, cute and charming idol vibe."
        )
        
        print(f"🎬 Generating {sid} image using Gemini (2D anime style)...")
        
        result = await generate_image_gemini(prompt, save_locally=True)
        
        if result.get("success"):
            image_path = result.get("local_path")
            print(f"   ✅ SUCCESS! Image saved to: {image_path}")
            
            old_path = "." + image_path  # /uploads/... -> ./uploads/...
            
            # Map sid to filenames
            filename_map = {
                "hotel": "onui-idol-concierge.png",
                "taxi": "onui-idol-driver.png",
                "shopping": "onui-idol-shopstaff.png",
                "bank": "onui-idol-banker.png",
                "dutyfree": "onui-idol-dutyfree.png"
            }
            new_filename = filename_map.get(sid, f"onui-idol-{sid}.png")
            new_path = f"static/images/{new_filename}"
            
            shutil.copy(old_path, new_path)
            print(f"   ✅ Copied image to {new_path}")
            
            for scenario in scenarios:
                if scenario["id"] == sid:
                    scenario["avatar_url"] = f"/static/images/{new_filename}"
                    updated = True
                    break
        else:
            print(f"   ❌ Failed to generate image for {sid}: {result.get('error')}")

    if updated:
        with open(DATA_PATH, "w", encoding="utf-8") as f:
            json.dump(scenarios, f, ensure_ascii=False, indent=2)
            f.write('\n')
        print("✅ Updated data/voice-call.json")

if __name__ == "__main__":
    asyncio.run(main())
