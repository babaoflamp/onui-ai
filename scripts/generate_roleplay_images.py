#!/usr/bin/env python3
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
DATA_PATH = Path("data/roleplay-scenarios.json")

PERSONA_PROMPTS = {
    "sejong": "King Sejong the Great of Joseon, wearing a traditional red royal dragon robe (Gonryongpo) and ikseongwan (king's hat).",
    "yisunsin": "Admiral Yi Sun-sin, wearing traditional Joseon naval commander armor (Gapot) and holding a sword.",
    "sinsaimdang": "Shin Saimdang, a noble Joseon artist and mother, wearing a beautiful elegant hanbok.",
    "yugwansun": "Yu Gwan-sun, a young Korean independence activist, wearing a traditional white and black hanbok school uniform.",
    "jangyeongsil": "Jang Yeong-sil, a Joseon scientist, wearing a blue official's robe, holding a small astronomical instrument.",
    "hojun": "Heo Jun, a Joseon royal physician, wearing a green official's medical robe, holding an ancient medical book.",
    "kimgu": "Kim Gu, a Korean independence leader, wearing a 1930s vintage suit and round glasses.",
    "gwanggaeto": "Gwanggaeto the Great of Goguryeo, wearing ancient majestic armor and a crown, looking heroic."
}

async def main():
    if not OPENAI_API_KEY:
        print("❌ OPENAI_API_KEY not found in .env")
        return

    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY)
    
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        scenarios = json.load(f)
        
    updated = False
    
    for scenario in scenarios:
        sid = scenario["id"]
        persona_desc = PERSONA_PROMPTS.get(sid)
        if not persona_desc:
            print(f"Skipping {sid}...")
            continue
            
        # Unified background and style prompt
        prompt = (
            f"A 3D Pixar-style cute digital illustration portrait of {persona_desc} "
            "The background MUST BE a completely solid, plain dark charcoal grey (#1A1A1A) with no other elements, no gradients, no distractions, creating a unified premium dark theme. "
            "Vibrant rim lighting, highly detailed, expressive character design, 4k resolution, waist-up portrait."
        )
        
        output_filename = f"{sid}.png"
        output_path = Path("static/images") / output_filename
        
        print(f"🎬 Generating image for {sid}...")
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
                
                scenario["image"] = f"/static/images/{output_filename}"
                updated = True
            else:
                print(f"   ❌ Failed to download: {resp.status_code}")
                
        except Exception as e:
            print(f"   ❌ DALL-E 3 Error: {e}")

    if updated:
        with open(DATA_PATH, "w", encoding="utf-8") as f:
            json.dump(scenarios, f, ensure_ascii=False, indent=2)
            f.write('\n')
        print("✅ Updated data/roleplay-scenarios.json")

if __name__ == "__main__":
    asyncio.run(main())
