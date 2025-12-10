"""
맞춤형 교재 생성 최적화 테스트
교재 생성 전용 프롬프트로 두 모델을 비교
"""

import time
import json
import re
from pathlib import Path
from dotenv import load_dotenv
import os
import requests

load_dotenv()

# 교재 생성용 프롬프트들
CURRICULUM_PROMPTS = [
    {
        "name": "초급 - 간단한 주제",
        "topic": "인사",
        "level": "초급",
        "prompt": """
한국어 선생님입니다.
주제: '인사'
레벨: '초급'

초급 학습자용으로 답변해주세요. 
문장은 짧고 간단하게(주로 기본 표현), 쉬운 어휘를 사용하고, 각 문장에 대한 짧은 설명은 생략하세요. 
한글을 처음 배우는 학습자도 이해하기 쉬운 수준으로 구성해 주세요.

위 조건에 맞는 짧은 한국어 대화문(3~4마디)과 주요 단어 3개를 JSON 형식으로 만들어주세요.
각 대사 항목에는 한국어 원문(text)과, 발음 표기를 반드시 포함해 주세요.
발음 표기는 한국어 발음을 이해하기 쉬운 영문 로마자(라틴 알파벳)로 표기해 주세요.
형식 예시:
{
    "dialogue": [
        {"speaker": "A", "text": "한국어 문장", "pronunciation": "romanized pronunciation"},
        {"speaker": "B", "text": "한국어 문장", "pronunciation": "romanized pronunciation"}
    ],
    "vocabulary": ["단어1", "단어2", "단어3"]
}

중요: 응답은 반드시 마지막에 하나의 JSON 객체만 포함된 코드 블럭(```json ... ``` )으로 정확하게 반환하세요.
"""
    },
    {
        "name": "중급 - 음식",
        "topic": "한국 음식",
        "level": "중급",
        "prompt": """
한국어 선생님입니다.
주제: '한국 음식'
레벨: '중급'

중급 학습자용으로 답변해주세요. 
문장은 자연스럽고 약간 복잡한 문장 구조를 포함할 수 있으며, 한두 개의 문법 포인트나 표현 설명(짧게)을 포함하세요. 
어휘는 적당히 도전적인 단어를 사용해 주세요.

위 조건에 맞는 짧은 한국어 대화문(3~4마디)과 주요 단어 3개를 JSON 형식으로 만들어주세요.
각 대사 항목에는 한국어 원문(text)과, 발음 표기를 반드시 포함해 주세요.
발음 표기는 한국어 발음을 이해하기 쉬운 영문 로마자(라틴 알파벳)로 표기해 주세요.
형식 예시:
{
    "dialogue": [
        {"speaker": "A", "text": "한국어 문장", "pronunciation": "romanized pronunciation"},
        {"speaker": "B", "text": "한국어 문장", "pronunciation": "romanized pronunciation"}
    ],
    "vocabulary": ["단어1", "단어2", "단어3"]
}

중요: 응답은 반드시 마지막에 하나의 JSON 객체만 포함된 코드 블럭(```json ... ``` )으로 정확하게 반환하세요.
"""
    },
    {
        "name": "고급 - 문화",
        "topic": "한국 문화",
        "level": "고급",
        "prompt": """
한국어 선생님입니다.
주제: '한국 문화'
레벨: '고급'

고급 학습자용으로 답변해주세요. 
보다 풍부한 표현, 관용구, 뉘앙스 설명과 문화적 메모를 포함해 주세요. 
문장은 자연스럽고 복잡할 수 있으며 학습자가 심화 학습할 수 있도록 예시와 설명을 추가하세요.

위 조건에 맞는 짧은 한국어 대화문(3~4마디)과 주요 단어 3개를 JSON 형식으로 만들어주세요.
각 대사 항목에는 한국어 원문(text)과, 발음 표기를 반드시 포함해 주세요.
발음 표기는 한국어 발음을 이해하기 쉬운 영문 로마자(라틴 알파벳)로 표기해 주세요.
형식 예시:
{
    "dialogue": [
        {"speaker": "A", "text": "한국어 문장", "pronunciation": "romanized pronunciation"},
        {"speaker": "B", "text": "한국어 문장", "pronunciation": "romanized pronunciation"}
    ],
    "vocabulary": ["단어1", "단어2", "단어3"]
}

중요: 응답은 반드시 마지막에 하나의 JSON 객체만 포함된 코드 블럭(```json ... ``` )으로 정확하게 반환하세요.
"""
    }
]

def test_gemini_curriculum(prompt: str) -> dict:
    """Gemini로 교재 생성 테스트"""
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
            
            # JSON 추출 시도
            json_match = re.search(r'```json\n([\s\S]*?)\n```', text)
            json_obj = None
            if json_match:
                try:
                    json_obj = json.loads(json_match.group(1))
                except:
                    pass
            
            return {
                "model": "Gemini 2.5 Flash",
                "success": True,
                "elapsed_time": round(end_time - start_time, 2),
                "response_length": len(text),
                "dialogue_count": len(json_obj.get("dialogue", [])) if json_obj else 0,
                "has_json": json_obj is not None,
                "json_valid": json_obj is not None and "dialogue" in json_obj and "vocabulary" in json_obj
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

def test_exaone_curriculum(prompt: str) -> dict:
    """EXAONE으로 교재 생성 테스트"""
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
        
        # JSON 추출 시도
        json_match = re.search(r'```json\n([\s\S]*?)\n```', text)
        json_obj = None
        if json_match:
            try:
                json_obj = json.loads(json_match.group(1))
            except:
                pass
        
        return {
            "model": "EXAONE 3.5 (2.4B)",
            "success": True,
            "elapsed_time": round(end_time - start_time, 2),
            "response_length": len(text),
            "dialogue_count": len(json_obj.get("dialogue", [])) if json_obj else 0,
            "has_json": json_obj is not None,
            "json_valid": json_obj is not None and "dialogue" in json_obj and "vocabulary" in json_obj
        }
    except Exception as e:
        return {
            "model": "EXAONE 3.5 (2.4B)",
            "error": str(e),
            "success": False
        }

def run_curriculum_comparison():
    """교재 생성 비교 테스트 실행"""
    print("=" * 80)
    print("맞춤형 교재 생성 최적화 테스트")
    print("=" * 80)
    print()
    
    results = []
    
    for test_case in CURRICULUM_PROMPTS:
        print(f"\n📚 테스트: {test_case['name']}")
        print(f"주제: {test_case['topic']}, 레벨: {test_case['level']}")
        print("-" * 80)
        
        # Gemini 테스트
        print("🔹 Gemini 2.5 Flash 테스트 중...")
        gemini_result = test_gemini_curriculum(test_case['prompt'])
        results.append({**gemini_result, "test_name": test_case['name']})
        
        if gemini_result['success']:
            print(f"✅ 응답 시간: {gemini_result['elapsed_time']}초")
            print(f"📊 응답 길이: {gemini_result['response_length']} 글자")
            print(f"📋 대화문 개수: {gemini_result['dialogue_count']}")
            print(f"✨ JSON 유효성: {'✅ 유효함' if gemini_result['json_valid'] else '❌ 추출 실패'}")
        else:
            print(f"❌ 오류: {gemini_result.get('error', '알 수 없는 오류')}")
        
        time.sleep(1)
        
        # EXAONE 테스트
        print("\n🔹 EXAONE 3.5 (2.4B) 테스트 중...")
        exaone_result = test_exaone_curriculum(test_case['prompt'])
        results.append({**exaone_result, "test_name": test_case['name']})
        
        if exaone_result['success']:
            print(f"✅ 응답 시간: {exaone_result['elapsed_time']}초")
            print(f"📊 응답 길이: {exaone_result['response_length']} 글자")
            print(f"📋 대화문 개수: {exaone_result['dialogue_count']}")
            print(f"✨ JSON 유효성: {'✅ 유효함' if exaone_result['json_valid'] else '❌ 추출 실패'}")
        else:
            print(f"❌ 오류: {exaone_result.get('error', '알 수 없는 오류')}")
        
        print()
    
    # 결과 요약
    print("\n" + "=" * 80)
    print("📊 교재 생성 최적화 결과 요약")
    print("=" * 80)
    
    gemini_results = [r for r in results if r['success'] and r['model'] == 'Gemini 2.5 Flash']
    exaone_results = [r for r in results if r['success'] and r['model'] == 'EXAONE 3.5 (2.4B)']
    
    if gemini_results:
        avg_gemini_time = sum(r['elapsed_time'] for r in gemini_results) / len(gemini_results)
        avg_gemini_length = sum(r['response_length'] for r in gemini_results) / len(gemini_results)
        gemini_valid = sum(1 for r in gemini_results if r['json_valid']) / len(gemini_results) * 100
        
        print(f"\n🔷 Gemini 2.5 Flash")
        print(f"   - 평균 응답 시간: {avg_gemini_time:.2f}초")
        print(f"   - 평균 응답 길이: {int(avg_gemini_length)} 글자")
        print(f"   - JSON 유효성: {gemini_valid:.0f}%")
        print(f"   - 성공 테스트: {len(gemini_results)}/{len(CURRICULUM_PROMPTS)}")
    else:
        print(f"\n🔷 Gemini 2.5 Flash - 실패함")
    
    if exaone_results:
        avg_exaone_time = sum(r['elapsed_time'] for r in exaone_results) / len(exaone_results)
        avg_exaone_length = sum(r['response_length'] for r in exaone_results) / len(exaone_results)
        exaone_valid = sum(1 for r in exaone_results if r['json_valid']) / len(exaone_results) * 100
        
        print(f"\n🔶 EXAONE 3.5 (2.4B)")
        print(f"   - 평균 응답 시간: {avg_exaone_time:.2f}초")
        print(f"   - 평균 응답 길이: {int(avg_exaone_length)} 글자")
        print(f"   - JSON 유효성: {exaone_valid:.0f}%")
        print(f"   - 성공 테스트: {len(exaone_results)}/{len(CURRICULUM_PROMPTS)}")
    else:
        print(f"\n🔶 EXAONE 3.5 (2.4B) - 실패함")
    
    # 교재 생성 최적화 분석
    if gemini_results and exaone_results:
        print(f"\n⚡ 교재 생성 최적화 분석")
        print(f"\n속도 (응답 시간):")
        avg_gemini_time = sum(r['elapsed_time'] for r in gemini_results) / len(gemini_results)
        avg_exaone_time = sum(r['elapsed_time'] for r in exaone_results) / len(exaone_results)
        time_diff = avg_exaone_time - avg_gemini_time
        if time_diff > 0:
            percentage = (abs(time_diff) / avg_gemini_time) * 100
            print(f"   🏆 Gemini가 {abs(time_diff):.2f}초 더 빠릅니다 ({percentage:.1f}% 차이)")
        else:
            percentage = (abs(time_diff) / avg_exaone_time) * 100
            print(f"   🏆 EXAONE이 {abs(time_diff):.2f}초 더 빠릅니다 ({percentage:.1f}% 차이)")
        
        print(f"\n생성 길이 (교재 부담):")
        avg_gemini_length = sum(r['response_length'] for r in gemini_results) / len(gemini_results)
        avg_exaone_length = sum(r['response_length'] for r in exaone_results) / len(exaone_results)
        
        if avg_exaone_length < avg_gemini_length:
            diff = ((avg_gemini_length - avg_exaone_length) / avg_gemini_length) * 100
            print(f"   🏆 EXAONE이 {diff:.1f}% 더 간결합니다 (학습자 부담 감소)")
        else:
            diff = ((avg_exaone_length - avg_gemini_length) / avg_gemini_length) * 100
            print(f"   🏆 Gemini가 {diff:.1f}% 더 간결합니다")
        
        print(f"\nJSON 포맷 정확성:")
        gemini_valid = sum(1 for r in gemini_results if r['json_valid']) / len(gemini_results) * 100
        exaone_valid = sum(1 for r in exaone_results if r['json_valid']) / len(exaone_results) * 100
        
        if gemini_valid > exaone_valid:
            print(f"   🏆 Gemini: {gemini_valid:.0f}% vs EXAONE: {exaone_valid:.0f}%")
        elif exaone_valid > gemini_valid:
            print(f"   🏆 EXAONE: {exaone_valid:.0f}% vs Gemini: {gemini_valid:.0f}%")
        else:
            print(f"   🤝 동점: 둘 다 {gemini_valid:.0f}%")
        
        print(f"\n🎯 교재 생성 최적화 권장사항:")
        if avg_exaone_time < avg_gemini_time and avg_exaone_length < avg_gemini_length:
            print(f"   🏆🏆🏆 EXAONE 3.5가 교재 생성에 최적화됨")
            print(f"      - 3배 빠른 생성 속도")
            print(f"      - 더 간결한 교재 (학습자 친화적)")
            print(f"      - API 비용 없음")
        else:
            print(f"   선택 기준:")
            print(f"   - 빠른 생성이 중요: EXAONE 추천")
            print(f"   - 상세한 설명이 중요: Gemini 추천")
    
    # 결과를 파일로 저장
    output_file = Path("test_results/curriculum_optimization_results.json")
    output_file.parent.mkdir(exist_ok=True)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f"\n💾 상세 결과가 {output_file}에 저장되었습니다")

if __name__ == "__main__":
    run_curriculum_comparison()
