#!/usr/bin/env python3
"""
Diagnostic script to test SpeechPro Score API connectivity and data format.

Usage:
    python scripts/test_speechpro_score_api.py
"""

import requests
import base64
import csv
import struct
import sys
import json
from pathlib import Path

# Score API endpoint
SCORE_API_URL = "http://112.220.79.222:33005/speechpro/scorejson"

def create_test_wav(duration_ms=200, sample_rate=16000, channels=1):
    """Create a minimal valid WAV file with silence."""
    samples = int(sample_rate * duration_ms / 1000)
    sample_width = 2
    byte_rate = sample_rate * channels * sample_width
    block_align = channels * sample_width
    
    # WAV header
    wav_data = b'RIFF'
    wav_data += struct.pack('<I', 36 + samples * sample_width)
    wav_data += b'WAVE'
    wav_data += b'fmt '
    wav_data += struct.pack('<I', 16)  # Subchunk1Size
    wav_data += struct.pack('<HHIIHH', 1, channels, sample_rate, byte_rate, block_align, 16)
    wav_data += b'data'
    wav_data += struct.pack('<I', samples * sample_width)
    wav_data += b'\x00' * (samples * sample_width)
    
    return wav_data

def load_csv_row(csv_path, row_index=0):
    """Load a specific row from CSV."""
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            if i == row_index:
                return row
    return None

def test_api_connectivity():
    """Test basic API connectivity."""
    print("=" * 60)
    print("TEST 1: Basic API Connectivity")
    print("=" * 60)
    
    try:
        response = requests.head(SCORE_API_URL, timeout=5)
        print(f"✓ API endpoint reachable: {SCORE_API_URL}")
        print(f"  Status: {response.status_code}")
        return True
    except requests.Timeout:
        print(f"✗ API timeout - server not responding")
        return False
    except requests.ConnectionError as e:
        print(f"✗ Connection error: {e}")
        return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

def test_with_csv_data():
    """Test with real CSV data."""
    print("\n" + "=" * 60)
    print("TEST 2: Score API with CSV Metadata")
    print("=" * 60)
    
    csv_path = Path("data/sp_ko_questions.csv")
    if not csv_path.exists():
        print(f"✗ CSV file not found: {csv_path}")
        return False
    
    # Load first row from CSV
    row = load_csv_row(csv_path, 0)
    if not row:
        print("✗ Could not load CSV row")
        return False
    
    text = row['sentence']
    syll_ltrs = row['syll_ltrs']
    syll_phns = row['syll_phns']
    fst = row['fst']
    
    print(f"✓ Loaded CSV data:")
    print(f"  Text: {text[:50]}...")
    print(f"  syll_ltrs length: {len(syll_ltrs)}")
    print(f"  syll_phns length: {len(syll_phns)}")
    print(f"  fst length: {len(fst)}")
    
    # Create minimal WAV
    audio_bytes = create_test_wav(duration_ms=200)
    wav_base64 = base64.b64encode(audio_bytes).decode()
    
    print(f"  Audio (test): {len(audio_bytes)} bytes ({len(wav_base64)} chars base64)")
    
    # Test payload
    payload = {
        "id": "test_diagnostic_001",
        "text": text,
        "syll_ltrs": syll_ltrs,
        "syll_phns": syll_phns,
        "fst": fst,
        "wav_usr": wav_base64
    }
    
    print(f"\nSending test request to {SCORE_API_URL}...")
    try:
        response = requests.post(SCORE_API_URL, json=payload, timeout=30)
        print(f"Response status: {response.status_code}")
        
        if response.status_code == 200:
            try:
                data = response.json()
                print(f"✓ Success! Response: {json.dumps(data, indent=2, ensure_ascii=False)[:300]}")
                return True
            except:
                print(f"✓ Got 200 but response is not JSON: {response.text[:100]}")
                return True
        elif response.status_code == 400:
            print(f"✗ 400 Bad Request")
            print(f"  Response: {response.text[:200]}")
            print(f"\nDiagnostics:")
            print(f"  - Text is valid: {bool(text)}")
            print(f"  - syll_ltrs is valid: {bool(syll_ltrs)}")
            print(f"  - syll_phns is valid: {bool(syll_phns)}")
            print(f"  - fst is valid: {bool(fst)}")
            print(f"  - fst is base64: {fst.startswith('1v2')}")
            
            # Try to validate FST
            try:
                fst_binary = base64.b64decode(fst)
                print(f"  - fst decodes to {len(fst_binary)} bytes")
                print(f"  - fst binary starts with: {fst_binary[:20]}")
            except Exception as e:
                print(f"  - fst decode error: {e}")
            
            return False
        else:
            print(f"✗ Unexpected status: {response.status_code}")
            print(f"  Response: {response.text[:200]}")
            return False
            
    except requests.Timeout:
        print(f"✗ Request timeout (30s)")
        return False
    except requests.ConnectionError as e:
        print(f"✗ Connection error: {e}")
        return False
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_with_minimal_data():
    """Test with minimal payload."""
    print("\n" + "=" * 60)
    print("TEST 3: Score API with Minimal Data")
    print("=" * 60)
    
    payload = {
        "id": "test_minimal_001",
        "text": "안녕",  # Very short text
        "syll_ltrs": "안_녕",
        "syll_phns": "aa_nn yv_oh ng",
        "fst": "1v2yfgYAAAB2ZWN0b3I=",  # Truncated FST (just header)
        "wav_usr": base64.b64encode(create_test_wav(100)).decode()
    }
    
    print(f"Testing with minimal payload...")
    print(f"  Text: {payload['text']}")
    print(f"  Text length: {len(payload['text'])}")
    print(f"  FST length: {len(payload['fst'])} chars")
    
    try:
        response = requests.post(SCORE_API_URL, json=payload, timeout=30)
        print(f"Response status: {response.status_code}")
        
        if response.status_code == 200:
            print(f"✓ Success with minimal data")
            return True
        elif response.status_code == 400:
            print(f"✗ 400 Bad Request (expected for truncated FST)")
            print(f"  This indicates API is receiving request but rejecting payload")
            return False
        else:
            print(f"✗ Status: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

def main():
    """Run all diagnostic tests."""
    print("\n" + "=" * 60)
    print("SpeechPro Score API Diagnostic Tool")
    print("=" * 60)
    
    results = {
        "connectivity": test_api_connectivity(),
        "csv_data": test_with_csv_data(),
        "minimal_data": test_with_minimal_data(),
    }
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    for test_name, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{test_name}: {status}")
    
    all_pass = all(results.values())
    
    if all_pass:
        print("\n✓ All tests passed!")
        return 0
    else:
        print("\n✗ Some tests failed. Check diagnostics above.")
        if not results["connectivity"]:
            print("\nTroubleshoot: API endpoint is not reachable")
            print("  - Check if IP/port is correct: 112.220.79.222:33005")
            print("  - Check network connectivity")
            print("  - Check if Score API server is running")
        elif not results["csv_data"]:
            print("\nTroubleshoot: API rejects CSV data")
            print("  - Check if metadata format is correct")
            print("  - Check if FST data is valid base64")
            print("  - Try shorter sentences")
        
        return 1

if __name__ == "__main__":
    sys.exit(main())
