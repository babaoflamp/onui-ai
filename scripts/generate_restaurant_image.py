#!/usr/bin/env python3
import os
import sys
import json
import asyncio
import requests
from pathlib import Path
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DATA_PATH = Path("data/voice-call.json")

async def main():
    if not OPENAI_API_KEY:
        print("❌ OPENAI_API_KEY not found in .env")
        return

    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY)
    
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        scenarios = json.load(f)
        
    prompt = (
        "A 3D Pixar-style cute digital illustration portrait of a young Korean female character. "
        "She has long, lustrous jet-black hair with soft, slightly off-center part, face-framing layers, and subtle natural waves at the ends. "
        "She has large, almond-shaped dark brown eyes with a gentle, friendly sparkle. "
        "She has a soft oval face, fair to light skin tone, rosy pink blush, and a wide, genuine, cheerful smile revealing neat white teeth. "
        "She is wearing a crisp white shirt and a black apron as a restaurant waiter. "
        "The background is an elegant, dimly lit upscale restaurant interior, slightly blurred. "
        "The lighting should be soft, bright, and welcoming, matching her cheerful and gentle aura. "
        "Highly detailed, 4k resolution, waist-up portrait."
    )
    
    output_filename = "onui-idol-waiter.webp" # Try to save it as webp but DALL-E returns png. Let's just name it .png and update the json, or save as png and convert to webp if needed. We'll just save it as onui-idol-waiter-v2.png to be safe and update JSON.
    output_filename = "onui-idol-waiter.png"
    output_path = Path("static/images") / output_filename
    
    print(f"🎬 Generating restaurant waiter image...")
    try:
        response = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1024x1024",
            quality="standard",
            n=1,
        )
        
        image_url = response.data[0].url
        print(f"   ✅ SUCCESS! Image URL: {image_url}")
        
        # Download and save
        resp = requests.get(image_url, timeout=30)
        if resp.status_code == 200:
            with open(output_path, "wb") as f:
                f.write(resp.content)
            print(f"   ✅ Image saved to {output_path}")
            
            # Update JSON
            updated = False
            for scenario in scenarios:
                if scenario["id"] == "restaurant":
                    scenario["avatar_url"] = f"/static/images/{output_filename}"
                    updated = True
                    break
            
            if updated:
                with open(DATA_PATH, "w", encoding="utf-8") as f:
                    json.dump(scenarios, f, ensure_ascii=False, indent=2)
                    f.write('\n')
                print("✅ Updated data/voice-call.json")
        else:
            print(f"   ❌ Failed to download: {resp.status_code}")
            
    except Exception as e:
        print(f"   ❌ DALL-E 3 Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
