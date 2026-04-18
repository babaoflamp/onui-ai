#!/usr/bin/env python3
"""
Generate a NEW Subway Station Staff image using Gemini (Imagen 3).
"""

import os
import sys
import json
import asyncio
import base64
from pathlib import Path
from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import google.generativeai as genai
from backend.services.dalle_service import _extract_gemini_image_base64

# Load environment
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
OUTPUT_PATH = Path("static/images/onui-idol-subway-staff.png")
TUBE_DATA_PATH = Path("data/onui-tube.json")

# Detailed prompt for a NEW unique image
PROMPT = (
    "A 3D digital illustration of 'Onui', a cute and friendly young Korean female character. "
    "She has a bright smile and her long black hair is tied in a ponytail. "
    "She is wearing a professional South Korean subway station manager uniform: a tailored navy blue blazer, "
    "a light blue button-down shirt, and a small identification badge. "
    "She is standing at a modern Seoul subway station platform with a futuristic train in the background. "
    "Cinematic lighting, Pixar-style aesthetic, vibrant colors, high detail, 4k, no text."
)

async def generate_with_gemini():
    if not GEMINI_API_KEY:
        print("❌ GEMINI_API_KEY not found")
        return False

    genai.configure(api_key=GEMINI_API_KEY)
    
    # Try multiple possible model names for image generation
    models_to_try = [
        "imagen-3.0-generate-001",
        "gemini-1.5-flash", 
        "gemini-2.0-flash-exp"
    ]
    
    for model_name in models_to_try:
        try:
            print(f"🎬 Attempting to generate with Gemini model: {model_name}...")
            model = genai.GenerativeModel(model_name)
            
            # Using run_in_executor for sync call
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: model.generate_content(PROMPT)
            )
            
            image_base64, mime_type = _extract_gemini_image_base64(response)
            
            if image_base64:
                img_data = base64.b64decode(image_base64)
                with open(OUTPUT_PATH, "wb") as f:
                    f.write(img_data)
                print(f"✅ SUCCESS! Image generated and saved to {OUTPUT_PATH} using {model_name}")
                return True
            else:
                print(f"   ⚠️ Model {model_name} did not return image data.")
                
        except Exception as e:
            print(f"   ⚠️ Model {model_name} failed: {str(e)[:100]}")
            
    return False

async def main():
    success = await generate_with_gemini()
    
    if success:
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
            print(f"✅ Updated {TUBE_DATA_PATH} with the NEW image.")
    else:
        print("❌ All Gemini models failed to generate the image.")

if __name__ == "__main__":
    asyncio.run(main())
