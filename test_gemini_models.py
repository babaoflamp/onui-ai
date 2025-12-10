#!/usr/bin/env python3
"""
Test script to list available Gemini models
"""
import os
import requests
from dotenv import load_dotenv

def list_models():
    """List available Gemini models"""
    load_dotenv()
    
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("❌ GEMINI_API_KEY not found in .env")
        return
    
    print(f"✓ API Key found: {api_key[:10]}...\n")
    
    try:
        # List models endpoint
        url = f"https://generativelanguage.googleapis.com/v1/models?key={api_key}"
        
        print("📡 Fetching available models...\n")
        
        response = requests.get(url, timeout=30)
        
        print(f"Status Code: {response.status_code}")
        print(f"Response:\n{response.text[:1000]}")
        
        if response.status_code == 200:
            result = response.json()
            if "models" in result:
                print("\n✅ Available models:")
                for model in result["models"]:
                    print(f"  - {model.get('name', 'Unknown')}")
        else:
            print(f"\n❌ Error: {response.status_code}")
            print(response.text)
        
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        print(f"Error type: {type(e).__name__}")

if __name__ == "__main__":
    list_models()
