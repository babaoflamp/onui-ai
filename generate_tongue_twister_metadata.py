#!/usr/bin/env python3
"""
Generate SpeechPro metadata for tongue-twister sentence
"""
import requests
import json

BASE_URL = "http://localhost:9000"
SENTENCE = "내가 그린 기린 그림은 잘 그린 기린 그림이고 네가 그린 기린 그림은 못 그린 기린 그림이다."

def generate_metadata():
    """Call SpeechPro API to generate metadata"""
    print(f"Generating metadata for: {SENTENCE[:50]}...")
    
    # Call the generate-metadata endpoint
    response = requests.post(
        f"{BASE_URL}/api/speechpro/generate-metadata",
        data={"text": SENTENCE}
    )
    
    if response.status_code == 200:
        data = response.json()
        if data.get("success"):
            print("✓ Metadata generated successfully")
            print(f"  syll_ltrs length: {len(data.get('syll_ltrs', ''))}")
            print(f"  syll_phns length: {len(data.get('syll_phns', ''))}")
            print(f"  fst length: {len(data.get('fst', ''))}")
            
            # Save to file
            metadata = {
                "text": SENTENCE,
                "syll_ltrs": data.get("syll_ltrs", ""),
                "syll_phns": data.get("syll_phns", ""),
                "fst": data.get("fst", "")
            }
            
            output_file = "data/tongue-twister-metadata.json"
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)
            
            print(f"\n✓ Metadata saved to: {output_file}")
            return metadata
        else:
            print(f"✗ API returned success=false: {data}")
            return None
    else:
        print(f"✗ API call failed with status {response.status_code}")
        print(f"  Response: {response.text}")
        return None

if __name__ == "__main__":
    metadata = generate_metadata()
    if metadata:
        print("\n" + "="*60)
        print("Preview:")
        print("="*60)
        print(f"text: {metadata['text'][:50]}...")
        print(f"syll_ltrs: {metadata['syll_ltrs'][:100]}...")
        print(f"syll_phns: {metadata['syll_phns'][:100]}...")
        print(f"fst: {metadata['fst'][:100]}...")
