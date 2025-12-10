#!/usr/bin/env python3
"""
SpeechPro API 테스트 스크립트

SpeechPro 서비스의 각 엔드포인트를 테스트합니다.
"""

import requests
import json
import base64
from pathlib import Path


BASE_URL = "http://localhost:9000"
SPEECHPRO_API = f"{BASE_URL}/api/speechpro"


def test_gtp():
    """GTP (Grapheme-to-Phoneme) 테스트"""
    print("\n=== GTP API 테스트 ===")
    
    url = f"{SPEECHPRO_API}/gtp"
    payload = {
        "text": "안녕하세요"
    }
    
    try:
        response = requests.post(url, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        print(f"✅ 성공")
        print(f"응답: {json.dumps(data, ensure_ascii=False, indent=2)}")
        return data
    
    except requests.exceptions.RequestException as e:
        print(f"❌ 실패: {e}")
        return None


def test_model(gtp_result):
    """Model API 테스트"""
    print("\n=== Model API 테스트 ===")
    
    if not gtp_result or gtp_result.get('error_code') != 0:
        print("❌ GTP 결과가 없습니다")
        return None
    
    url = f"{SPEECHPRO_API}/model"
    payload = {
        "text": gtp_result.get('text'),
        "syll_ltrs": gtp_result.get('syll_ltrs'),
        "syll_phns": gtp_result.get('syll_phns')
    }
    
    try:
        response = requests.post(url, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        print(f"✅ 성공")
        print(f"응답: {json.dumps(data, ensure_ascii=False, indent=2)}")
        return data
    
    except requests.exceptions.RequestException as e:
        print(f"❌ 실패: {e}")
        return None


def test_score(model_result, audio_path=None):
    """Score API 테스트"""
    print("\n=== Score API 테스트 ===")
    
    if not model_result or model_result.get('error_code') != 0:
        print("❌ Model 결과가 없습니다")
        return None
    
    # 테스트용 더미 오디오 생성 (사인파 WAV)
    if audio_path is None or not Path(audio_path).exists():
        print("⚠️  실제 오디오 파일이 없어 더미 파일로 테스트합니다")
        import wave
        import struct
        import math
        
        audio_path = "/tmp/test_audio.wav"
        sample_rate = 16000
        duration = 1  # 1초
        frequency = 440  # A4 음
        
        # 사인파 생성
        num_samples = sample_rate * duration
        amplitude = 32767
        
        frames = []
        for i in range(num_samples):
            sample = int(amplitude * math.sin(2 * math.pi * frequency * i / sample_rate))
            frames.append(struct.pack('<h', sample))
        
        with wave.open(audio_path, 'w') as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            wav.writeframes(b''.join(frames))
        
        print(f"더미 오디오 파일 생성: {audio_path}")
    
    url = f"{SPEECHPRO_API}/score"
    
    try:
        with open(audio_path, 'rb') as f:
            audio_content = f.read()
        
        files = {
            'audio': ('test_audio.wav', audio_content, 'audio/wav')
        }
        
        data = {
            'text': model_result.get('text'),
            'syll_ltrs': model_result.get('syll_ltrs'),
            'syll_phns': model_result.get('syll_phns'),
            'fst': model_result.get('fst')
        }
        
        response = requests.post(url, data=data, files=files, timeout=60)
        response.raise_for_status()
        result = response.json()
        
        print(f"✅ 성공")
        print(f"응답: {json.dumps(result, ensure_ascii=False, indent=2)}")
        return result
    
    except requests.exceptions.RequestException as e:
        print(f"❌ 실패: {e}")
        return None


def test_evaluate(audio_path=None):
    """통합 평가 API 테스트"""
    print("\n=== 통합 평가 API 테스트 ===")
    
    # 테스트용 더미 오디오 생성
    if audio_path is None or not Path(audio_path).exists():
        print("⚠️  실제 오디오 파일이 없어 더미 파일로 테스트합니다")
        import wave
        import struct
        import math
        
        audio_path = "/tmp/test_audio.wav"
        sample_rate = 16000
        duration = 1
        frequency = 440
        
        num_samples = sample_rate * duration
        amplitude = 32767
        
        frames = []
        for i in range(num_samples):
            sample = int(amplitude * math.sin(2 * math.pi * frequency * i / sample_rate))
            frames.append(struct.pack('<h', sample))
        
        with wave.open(audio_path, 'w') as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            wav.writeframes(b''.join(frames))
    
    url = f"{SPEECHPRO_API}/evaluate"
    
    try:
        with open(audio_path, 'rb') as f:
            audio_content = f.read()
        
        files = {
            'audio': ('test_audio.wav', audio_content, 'audio/wav')
        }
        
        data = {
            'text': '안녕하세요'
        }
        
        response = requests.post(url, data=data, files=files, timeout=60)
        response.raise_for_status()
        result = response.json()
        
        if result.get('success'):
            print(f"✅ 성공")
        else:
            print(f"⚠️  워크플로우 실패: {result.get('error')}")
        
        print(f"응답: {json.dumps(result, ensure_ascii=False, indent=2)}")
        return result
    
    except requests.exceptions.RequestException as e:
        print(f"❌ 실패: {e}")
        return None


def test_config():
    """설정 API 테스트"""
    print("\n=== 설정 API 테스트 ===")
    
    url = f"{SPEECHPRO_API}/config"
    
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        print(f"✅ 성공")
        print(f"응답: {json.dumps(data, ensure_ascii=False, indent=2)}")
        return data
    
    except requests.exceptions.RequestException as e:
        print(f"❌ 실패: {e}")
        return None


def main():
    """메인 테스트"""
    print("=" * 50)
    print("SpeechPro API 테스트 시작")
    print("=" * 50)
    
    # 1. 설정 확인
    config = test_config()
    
    if not config:
        print("\n⚠️  SpeechPro 서버에 연결할 수 없습니다")
        print("SpeechPro 서버가 http://112.220.79.222:33005/speechpro 에서 실행 중인지 확인하세요")
        return
    
    # 2. GTP 테스트
    gtp_result = test_gtp()
    if not gtp_result:
        print("\n❌ GTP 테스트 실패")
        return
    
    # 3. Model 테스트
    model_result = test_model(gtp_result)
    if not model_result:
        print("\n❌ Model 테스트 실패")
        return
    
    # 4. Score 테스트 (오디오 파일 필요)
    score_result = test_score(model_result)
    if not score_result:
        print("\n⚠️  Score 테스트 실패 (SpeechPro 서버 상태 확인 필요)")
    
    # 5. 통합 평가 테스트
    evaluate_result = test_evaluate()
    if not evaluate_result:
        print("\n⚠️  통합 평가 테스트 실패")
    
    print("\n" + "=" * 50)
    print("테스트 완료")
    print("=" * 50)


if __name__ == "__main__":
    main()
