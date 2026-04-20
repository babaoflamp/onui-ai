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
DATA_PATH = Path("data/voice-call.json")

PERSONA_PROMPTS = {
    "starbucks": ("barista in a green apron", "A cozy, warmly lit modern cafe interior, slightly blurred in the background."),
    "airport": ("airport check-in staff wearing a neat navy blue uniform and a neck scarf", "A bright, busy modern airport terminal, slightly blurred in the background."),
    "hospital": ("doctor wearing a white medical coat and a stethoscope", "A clean, bright hospital corridor or clinic room, slightly blurred in the background."),
    "restaurant": ("waiter wearing a crisp white shirt and a black apron", "An elegant, dimly lit upscale restaurant interior, slightly blurred in the background."),
    "hotel": ("hotel concierge wearing a sharp, elegant suit", "A luxurious, grand hotel lobby with warm golden lighting, slightly blurred in the background."),
    "taxi": ("taxi driver wearing a comfortable casual vest and a driving cap", "The interior of a modern taxi cab with city street lights visible outside the window, slightly blurred in the background."),
    "police": ("police officer wearing a South Korean police uniform", "A neat, bright police station interior, slightly blurred in the background."),
    "school": ("teacher wearing smart casual clothes, holding a book", "A sunny, modern classroom with a blackboard, slightly blurred in the background."),
    "shopping": ("fashion store clerk wearing trendy, stylish modern casual clothes", "A bright, high-end fashion boutique interior, slightly blurred in the background."),
    "bank": ("bank teller wearing a neat, professional business suit", "A clean, modern bank interior with a service counter, slightly blurred in the background."),
    "dutyfree": ("duty-free shop staff wearing a luxurious, elegant uniform", "A sparkling, luxurious duty-free shopping mall interior, slightly blurred in the background.")
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
        persona_data = PERSONA_PROMPTS.get(sid)
        if not persona_data:
            print(f"Skipping {sid}...")
            continue
            
        persona_desc, bg_desc = persona_data
            
        # Unified tone and style prompt with environmental background
        prompt = (
            f"A 3D Pixar-style cute digital illustration portrait of a young Korean character 'Onui' as a {persona_desc}. "
            f"Background: {bg_desc} "
            "The overall tone MUST HAVE a unified, premium dark-cinematic lighting with soft rim lights, matching a dark-mode UI. "
            "Highly detailed, expressive character design, 4k resolution, waist-up portrait."
        )
        
        # Determine output filename based on existing URL or generate a new one
        existing_url = scenario.get("avatar_url", "")
        if existing_url.startswith("/static/images/"):
            output_filename = existing_url.split("/")[-1].replace(".webp", ".png")
        else:
            output_filename = f"voice_call_{sid}.png"
            
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
                
                scenario["avatar_url"] = f"/static/images/{output_filename}"
                updated = True
            else:
                print(f"   ❌ Failed to download: {resp.status_code}")
                
        except Exception as e:
            print(f"   ❌ DALL-E 3 Error: {e}")

    if updated:
        with open(DATA_PATH, "w", encoding="utf-8") as f:
            json.dump(scenarios, f, ensure_ascii=False, indent=2)
            f.write('\n')
        print("✅ Updated data/voice-call.json")

if __name__ == "__main__":
    asyncio.run(main())
