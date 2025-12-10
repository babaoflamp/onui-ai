"""
Gemini와 EXAONE 모델 비교 테스트
응답 속도, 응답 길이, 품질 등을 테스트합니다.
"""

import time
import json
import re
from pathlib import Path
from dotenv import load_dotenv
import os
import requests

# 환경변수 로드
load_dotenv()

# 테스트할 프롬프트들
TEST_PROMPTS = [
    {
        "name": "간단한 질문",
        "prompt": "안녕하세요? 오늘 날씨가 어떤가요?"
    },
    {
        "name": "한국어 설명",
        "prompt": "김치가 뭔지 간단히 설명해주세요."
    },
    {
        "name": "복잡한 질문",
        "prompt": "한국의 전통문화와 현대문화의 차이점을 설명해주세요."
    },
    {
        "name": "창의적 질문",
        "prompt": "미래의 한국어 학습 방법은 어떻게 될까요?"
    }
]

# Gemini 테스트
def test_gemini(prompt: str) -> dict:
    """Gemini REST API로 테스트"""
    try:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            return {"error": "GEMINI_API_KEY 환경변수가 설정되지 않았습니다", "success": False}
        
        url = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent?key={api_key}"
        payload = {
            "contents": [{
                "parts": [{
                    "text": prompt
                }]
            }]
        }
        
        start_time = time.time()
        response = requests.post(url, json=payload, timeout=60)
        end_time = time.time()
        
        response.raise_for_status()
        result = response.json()
        
        if "candidates" in result and len(result["candidates"]) > 0:
            text = result["candidates"][0]["content"]["parts"][0]["text"]
            return {
                "model": "Gemini 2.5 Flash",
                "prompt": prompt,
                "response": text,
                "response_length": len(text),
                "elapsed_time": round(end_time - start_time, 2),
                "success": True
            }
        else:
            return {
                "model": "Gemini 2.5 Flash",
                "error": "No response from Gemini",
                "success": False
            }
    except Exception as e:
        return {
            "model": "Gemini 2.5 Flash",
            "error": str(e),
            "success": False
        }

# EXAONE 테스트
def test_exaone(prompt: str) -> dict:
    """EXAONE Ollama 모델로 테스트"""
    try:
        ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
        
        url = f"{ollama_url}/api/generate"
        payload = {
            "model": "exaone3.5:2.4b",
            "prompt": prompt,
            "stream": False
        }
        
        start_time = time.time()
        response = requests.post(url, json=payload, timeout=120)
        end_time = time.time()
        
        response.raise_for_status()
        result = response.json()
        
        text = result.get("response", "")
        return {
            "model": "EXAONE 3.5 (2.4B)",
            "prompt": prompt,
            "response": text,
            "response_length": len(text),
            "elapsed_time": round(end_time - start_time, 2),
            "success": True
        }
    except Exception as e:
        return {
            "model": "EXAONE 3.5 (2.4B)",
            "error": str(e),
            "success": False
        }

def run_comparison():
    """비교 테스트 실행"""
    print("=" * 80)
    print("Gemini 2.5 Flash vs EXAONE 3.5 (2.4B) 비교 테스트")
    print("=" * 80)
    print()
    
    results = []
    
    for test_case in TEST_PROMPTS:
        print(f"\n📝 테스트: {test_case['name']}")
        print(f"프롬프트: {test_case['prompt']}")
        print("-" * 80)
        
        # Gemini 테스트
        print("🔹 Gemini 2.5 Flash 테스트 중...")
        gemini_result = test_gemini(test_case['prompt'])
        results.append(gemini_result)
        
        if gemini_result['success']:
            print(f"✅ 응답 시간: {gemini_result['elapsed_time']}초")
            print(f"📊 응답 길이: {gemini_result['response_length']} 글자")
            print(f"💬 응답: {gemini_result['response'][:150]}...")
        else:
            print(f"❌ 오류: {gemini_result.get('error', '알 수 없는 오류')}")
        
        time.sleep(1)  # API 제한 회피
        
        # EXAONE 테스트
        print("\n🔹 EXAONE 3.5 (2.4B) 테스트 중...")
        exaone_result = test_exaone(test_case['prompt'])
        results.append(exaone_result)
        
        if exaone_result['success']:
            print(f"✅ 응답 시간: {exaone_result['elapsed_time']}초")
            print(f"📊 응답 길이: {exaone_result['response_length']} 글자")
            print(f"💬 응답: {exaone_result['response'][:150]}...")
        else:
            print(f"❌ 오류: {exaone_result.get('error', '알 수 없는 오류')}")
        
        print()
    
    # 결과 요약
    print("\n" + "=" * 80)
    print("📊 결과 요약")
    print("=" * 80)
    
    gemini_results = [r for r in results if r['success'] and r['model'] == 'Gemini 2.5 Flash']
    exaone_results = [r for r in results if r['success'] and r['model'] == 'EXAONE 3.5 (2.4B)']
    
    if gemini_results:
        avg_gemini_time = sum(r['elapsed_time'] for r in gemini_results) / len(gemini_results)
        avg_gemini_length = sum(r['response_length'] for r in gemini_results) / len(gemini_results)
        print(f"\n🔷 Gemini 2.5 Flash")
        print(f"   - 평균 응답 시간: {avg_gemini_time:.2f}초")
        print(f"   - 평균 응답 길이: {int(avg_gemini_length)} 글자")
        print(f"   - 성공 테스트: {len(gemini_results)}/{len(TEST_PROMPTS)}")
    else:
        print(f"\n🔷 Gemini 2.5 Flash - 실패함")
    
    if exaone_results:
        avg_exaone_time = sum(r['elapsed_time'] for r in exaone_results) / len(exaone_results)
        avg_exaone_length = sum(r['response_length'] for r in exaone_results) / len(exaone_results)
        print(f"\n🔶 EXAONE 3.5 (2.4B)")
        print(f"   - 평균 응답 시간: {avg_exaone_time:.2f}초")
        print(f"   - 평균 응답 길이: {int(avg_exaone_length)} 글자")
        print(f"   - 성공 테스트: {len(exaone_results)}/{len(TEST_PROMPTS)}")
    else:
        print(f"\n🔶 EXAONE 3.5 (2.4B) - 실패함")
    
    # 비교 분석
    if gemini_results and exaone_results:
        avg_gemini_time = sum(r['elapsed_time'] for r in gemini_results) / len(gemini_results)
        avg_exaone_time = sum(r['elapsed_time'] for r in exaone_results) / len(exaone_results)
        avg_gemini_length = sum(r['response_length'] for r in gemini_results) / len(gemini_results)
        avg_exaone_length = sum(r['response_length'] for r in exaone_results) / len(exaone_results)
        
        print(f"\n⚡ 응답 속도 비교")
        time_diff = avg_exaone_time - avg_gemini_time
        if time_diff > 0:
            percentage = (abs(time_diff) / avg_gemini_time) * 100
            print(f"   Gemini가 {abs(time_diff):.2f}초 더 빠릅니다 ({percentage:.1f}% 차이)")
        else:
            percentage = (abs(time_diff) / avg_exaone_time) * 100
            print(f"   EXAONE이 {abs(time_diff):.2f}초 더 빠릅니다 ({percentage:.1f}% 차이)")
        
        print(f"\n📝 응답 길이 비교")
        length_diff = avg_exaone_length - avg_gemini_length
        if length_diff > 0:
            percentage = (abs(length_diff) / avg_gemini_length) * 100
            print(f"   EXAONE이 {int(length_diff)} 글자 더 깁니다 ({percentage:.1f}% 차이)")
        else:
            percentage = (abs(length_diff) / avg_exaone_length) * 100
            print(f"   Gemini가 {int(abs(length_diff))} 글자 더 깁니다 ({percentage:.1f}% 차이)")
        
        print(f"\n💡 모델 특성 분석")
        print(f"   - Gemini: 빠른 응답이 필요한 경우 적합, API 사용량 제한이 있음")
        print(f"   - EXAONE: 로컬 실행으로 응답 시간은 느리지만 더 상세한 답변 제공")
    
    # 결과를 파일로 저장
    output_file = Path("test_results/model_comparison_results.json")
    output_file.parent.mkdir(exist_ok=True)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f"\n💾 상세 결과가 {output_file}에 저장되었습니다")

if __name__ == "__main__":
    run_comparison()

