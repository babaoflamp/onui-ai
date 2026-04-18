#!/usr/bin/env python3
"""
Generate a NEW Subway Station Staff image using the NEW Gemini SDK (google-genai).
"""

import os
import sys
import json
import base64
from pathlib import Path
from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Use the new SDK
try:
    from google import genai
    from google.genai import types
except ImportError:
    print("❌ google-genai SDK not installed. Please run: pip install google-genai")
    sys.exit(1)

# Load environment
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
OUTPUT_PATH = Path("static/images/onui-idol-subway-staff.png")
TUBE_DATA_PATH = Path("data/onui-tube.json")

# Detailed prompt
PROMPT = (
    "A professional 3D digital illustration of a cute young Korean female character 'Onui'. "
    "She has a warm smile, wearing a South Korean subway station staff uniform (navy blue blazer, badge). "
    "She is at a subway station platform. Pixar-style, cinematic lighting, 4k."
)

def main():
    if not GEMINI_API_KEY:
        print("❌ GEMINI_API_KEY not found")
        return

    client = genai.Client(api_key=GEMINI_API_KEY, http_options={'api_version': 'v1alpha'})
    
    # Common imagen model names in new SDK
    model_name = "imagen-3.0-generate-001"
    
    print(f"🎬 Generating with NEW SDK and model: {model_name}...")
    
    try:
        response = client.models.generate_content(
            model=model_name,
            contents=PROMPT,
            config=types.GenerateContentConfig(
                # Some versions require specific configs for images
                # but often it's just a regular prompt for Imagen models
            )
        )
        
        # New SDK response parsing
        image_data = None
        for candidate in response.candidates:
            for part in candidate.content.parts:
                if part.inline_data:
                    image_data = part.inline_data.data
                    break
        
        if image_data:
            # Save the image
            with open(OUTPUT_PATH, "wb") as f:
                f.write(image_data)
            print(f"✅ SUCCESS! Image saved to {OUTPUT_PATH}")
            
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
                print(f"✅ Updated {TUBE_DATA_PATH}")
        else:
            print("❌ No image data found in response.")
            print(f"Response: {response}")
            
    except Exception as e:
        print(f"❌ Error with new SDK: {e}")

if __name__ == "__main__":
    main()
