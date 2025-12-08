#!/usr/bin/env python3
"""Test script to debug Score API with preset sentence"""

import requests
import json

# Get preset sentences first
print("=== Fetching preset sentences ===")
resp = requests.get("http://localhost:9000/api/speechpro/sentences")
sentences = resp.json()

print(f"Loaded {len(sentences)} preset sentences")
for i, s in enumerate(sentences[:3]):
    print(f"  [{i}] {s.get('sentenceKr', '')}")

# Find the problematic sentence
target_sentence = "우리 아들은 키가 큰 편이에요"
target_preset = None

for sentence in sentences:
    sent_kr = sentence.get('sentenceKr', '')
    if sent_kr == target_sentence:
        target_preset = sentence
        break

if target_preset:
    print(f"\n✓ Found preset sentence: {target_preset['sentenceKr']}")
    print(f"  ID: {target_preset.get('id', 'N/A')}")
    print(f"  syll_ltrs length: {len(target_preset.get('syll_ltrs', ''))}")
    print(f"  syll_phns length: {len(target_preset.get('syll_phns', ''))}")
    print(f"  fst length: {len(target_preset.get('fst', ''))}")
else:
    print(f"\n✗ ERROR: Could not find sentence: {target_sentence}")
    print("\nAvailable sentences:")
    for i, sentence in enumerate(sentences):
        print(f"  [{i}] {sentence.get('sentenceKr', '')}")
    exit(1)

# Create dummy audio (16k mono WAV, 1 second)
print("\n=== Creating test audio ===")
import wave
import io
sample_rate = 16000
duration = 1
num_samples = sample_rate * duration
amplitude = 1000

wav_buffer = io.BytesIO()
with wave.open(wav_buffer, 'wb') as wav_file:
    wav_file.setnchannels(1)  # mono
    wav_file.setsampwidth(2)  # 16-bit
    wav_file.setframerate(sample_rate)
    
    import struct
    audio_data = b''.join(struct.pack('<h', amplitude) for _ in range(num_samples))
    wav_file.writeframes(audio_data)

wav_bytes = wav_buffer.getvalue()
print(f"Created {len(wav_bytes)} bytes of test audio")

# Test evaluation with preset
print("\n=== Testing evaluation with preset ===")
print(f"Submitting: '{target_sentence}'")

files = {
    'audio': ('test.wav', wav_bytes, 'audio/wav')
}

data = {
    'text': target_sentence,
    'syll_ltrs': target_preset.get('syll_ltrs', ''),
    'syll_phns': target_preset.get('syll_phns', ''),
    'fst': target_preset.get('fst', '')
}

try:
    resp = requests.post("http://localhost:9000/api/speechpro/evaluate", files=files, data=data, timeout=40)
    print(f"Response status: {resp.status_code}")
    result = resp.json()
    print(f"Response JSON:")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    if result.get('success'):
        print(f"\n✓ Success!")
        print(f"  Overall score: {result.get('overall_score')}")
        score_details = result.get('score', {})
        print(f"  Score details: {score_details}")
    else:
        print(f"\n✗ Failed")
        print(f"  Error: {result.get('error')}")
        
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
