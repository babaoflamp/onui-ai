#!/usr/bin/env python3
"""
Generate images for folktales using Gemini API
"""

import os
import sys
import json
import asyncio
import base64
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.services.dalle_service import generate_image_gemini

# Load environment
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_IMAGE_MODEL = os.getenv("GEMINI_IMAGE_MODEL", "gemini-2.0-flash-exp")
UPLOADS_DIR = Path("uploads/images")
FOLKTALES_DATA = Path("data/folktales.json")

UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


async def generate_folktale_image(folktale_id: int, prompt: str) -> dict:
    """Generate image for a folktale"""
    print(f"\n📸 Generating image for folktale #{folktale_id}...")
    print(f"   Prompt: {prompt[:100]}...")
    
    try:
        result = await generate_image_gemini(prompt, save_locally=True)
        
        if result.get("success"):
            image_url = result.get("local_path") or result.get("image_url")
            print(f"   ✅ Image generated: {image_url}")
            return {
                "success": True,
                "image_url": image_url,
                "model": GEMINI_IMAGE_MODEL
            }
        else:
            print(f"   ❌ Error: {result.get('error')}")
            return {"success": False, "error": result.get("error")}
            
    except Exception as e:
        print(f"   ❌ Exception: {e}")
        return {"success": False, "error": str(e)}


async def main():
    """Main function to generate images for all folktales with prompts"""
    
    if not GEMINI_API_KEY:
        print("❌ Error: GEMINI_API_KEY not set in .env")
        sys.exit(1)
    
    # Load folktales data
    with open(FOLKTALES_DATA, 'r', encoding='utf-8') as f:
        folktales = json.load(f)
    
    print(f"📖 Loaded {len(folktales)} folktales")
    
    # Process each folktale with imagePrompt
    for folktale in folktales:
        folktale_id = folktale.get("id")
        image_prompt = folktale.get("imagePrompt")
        
        if not image_prompt:
            print(f"\n⏭️  Folktale #{folktale_id} '{folktale.get('title')}' has no imagePrompt, skipping...")
            continue
        
        # Check if image already exists
        if folktale.get("image_url"):
            print(f"\n⏭️  Folktale #{folktale_id} '{folktale.get('title')}' already has image_url, skipping...")
            continue
        
        # Generate image
        result = await generate_folktale_image(folktale_id, image_prompt)
        
        if result["success"]:
            folktale["image_url"] = result["image_url"]
            folktale["image_model"] = result.get("model")
    
    # Save updated folktales
    with open(FOLKTALES_DATA, 'w', encoding='utf-8') as f:
        json.dump(folktales, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ Updated {FOLKTALES_DATA}")


if __name__ == "__main__":
    asyncio.run(main())
