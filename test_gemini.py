#!/usr/bin/env python3
"""
Quick test script for Google Gemini API integration
Uses REST API directly for compatibility with Python 3.8
"""
import os
import requests
from dotenv import load_dotenv

def test_gemini():
    """Test Gemini API connection and response via REST API"""
    load_dotenv()
    
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("❌ GEMINI_API_KEY not found in .env")
        return
    
    print(f"✓ API Key found: {api_key[:10]}...")
    
    try:
        # Use Gemini REST API directly - gemini-2.5-flash model
        url = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent?key={api_key}"
        
        test_prompt = """You are a Korean pronunciation coach. Analyze this pronunciation attempt:

Target Sentence: 안녕하세요
User's Score: 75/100
Fluency: 70%
Sentence Score: 75

Word Analysis:
- 안녕하세요: 75 points
  - Syllables: 안(80), 녕(75), 하(70), 세(72), 요(78)

Provide brief, encouraging feedback in Korean (2-3 sentences) focusing on:
1. What they did well
2. One specific improvement suggestion
"""
        
        payload = {
            "contents": [{
                "parts": [{
                    "text": test_prompt
                }]
            }]
        }
        
        print("\n📡 Testing Gemini API with pronunciation feedback prompt...\n")
        
        response = requests.post(url, json=payload, timeout=30)
        response.raise_for_status()
        
        result = response.json()
        
        if "candidates" in result and len(result["candidates"]) > 0:
            text = result["candidates"][0]["content"]["parts"][0]["text"]
            print("✅ Gemini Response:")
            print("-" * 60)
            print(text)
            print("-" * 60)
            print("\n✅ Test successful! Gemini API is working.")
        else:
            print("❌ Unexpected response format:")
            print(result)
        
    except requests.exceptions.HTTPError as e:
        print(f"\n❌ HTTP Error: {e}")
        if e.response:
            print(f"Status Code: {e.response.status_code}")
            print(f"Response Text: {e.response.text}")
            try:
                error_json = e.response.json()
                print(f"Error JSON: {error_json}")
            except:
                pass
    except Exception as e:
        print(f"\n❌ Error calling Gemini API: {str(e)}")
        print(f"Error type: {type(e).__name__}")

if __name__ == "__main__":
    test_gemini()
