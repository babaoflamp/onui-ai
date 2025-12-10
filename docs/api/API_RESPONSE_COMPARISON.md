# SpeechPro vs FluencyPro API 응답 비교

## 1. SpeechPro API 응답 구조

### POST /api/speechpro/evaluate
**목적**: 발음 정확도 평가

**응답 항목**:
```
{
  "gtp": {
    "id": string,
    "text": string,
    "syll_ltrs": string (음절 문자),
    "syll_phns": string (음절 발음),
    "error_code": number
  },
  "model": {
    "id": string,
    "text": string,
    "syll_ltrs": string,
    "syll_phns": string,
    "fst": string (발음 모델),
    "error_code": number
  },
  "score": {
    "id": string,
    "text": string,
    "accuracy": number (0-100),
    "f0": number (기본주파수),
    "energy": number (에너지),
    "speech_rate": number,
    "phoneme_score": object,
    "error_code": number
  },
  "overall_score": number (0-100, 최종 발음 점수),
  "success": boolean,
  "source": string ("precomputed" or "full_workflow"),
  "ai_feedback": string (선택사항, AI 피드백)
}
```

**핵심 평가 항목**:
- **accuracy**: 발음 정확도 (%)
- **overall_score**: 최종 발음 점수
- **phoneme_score**: 개별 음소별 점수
- **ai_feedback**: AI 기반 피드백

---

## 2. FluencyPro API 응답 구조

### POST /api/fluencypro/analyze
**목적**: 유창성 평가

**응답 항목**:
```
{
  "text": string (분석 텍스트),
  "audio_length_ms": number (오디오 길이, 밀리초),
  "speech_rate": number (음절/초, 발화 속도),
  "correct_syllables_rate": number (% 정확한 음절 비율),
  "articulation_rate": number (조음 속도),
  "pause_count": number (쉼표 개수),
  "pause_duration_ms": number (쉼표 총 시간),
  "fluency_score": number (0-100, 유창성 점수),
  "confidence": number (0-1, 신뢰도),
  "recommendations": array[string] (개선 권장사항),
  "timestamp": string (ISO 8601 형식)
}
```

### GET /api/fluencypro/metrics/{user_id}
**목적**: 사용자 유창성 통계 조회

**응답 항목**:
```
{
  "user_id": string,
  "total_practices": number (총 연습 횟수),
  "average_fluency_score": number (평균 유창성 점수),
  "best_fluency_score": number (최고 유강성 점수),
  "worst_fluency_score": number (최저 유강성 점수),
  "fluency_grade": string ("A+", "A", "B", "C", "D"),
  "practice_frequency": string ("매일", "주 3-4회", "불규칙"),
  "improvement_trend": string ("상승", "하강", "데이터 부족"),
  "speech_rate_average": number (평균 발화 속도),
  "articulation_rate_average": number (평균 조음 속도),
  "accuracy_score": number (정확도 점수),
  "last_practice": string (마지막 연습 시간)
}
```

**핵심 평가 항목**:
- **fluency_score**: 유창성 점수
- **speech_rate**: 발화 속도
- **articulation_rate**: 조음 속도
- **pause_count/pause_duration**: 쉼표 분석

---

## 3. 항목별 비교 분석

### 공통 항목
| 항목 | SpeechPro | FluencyPro | 설명 |
|------|-----------|-----------|------|
| text | ✓ | ✓ | 평가 대상 텍스트 |
| speech_rate | ✓ (score) | ✓ | 발화 속도 |
| error_code | ✓ | ✗ | 에러 코드 |
| timestamp | ✗ | ✓ | 분석 시간 |

### SpeechPro 고유 항목
| 항목 | 설명 |
|------|------|
| **gtp** | 텍스트→음소 변환 결과 |
| **model** | FST 발음 모델 정보 |
| **accuracy** | 발음 정확도 |
| **phoneme_score** | 개별 음소 점수 |
| **f0** | 기본 주파수 |
| **energy** | 에너지 수준 |
| **ai_feedback** | AI 기반 피드백 |
| **source** | 데이터 소스 표시 |

### FluencyPro 고유 항목
| 항목 | 설명 |
|------|------|
| **audio_length_ms** | 오디오 길이 |
| **correct_syllables_rate** | 정확한 음절 비율 |
| **articulation_rate** | 조음 속도 |
| **pause_count** | 쉼표 개수 |
| **pause_duration_ms** | 쉼표 총 시간 |
| **fluency_score** | 유창성 점수 |
| **confidence** | 신뢰도 |
| **recommendations** | 개선 권장사항 |

---

## 4. 평가 초점 비교

### SpeechPro (발음 평가)
- **초점**: 개별 음소의 정확성
- **평가 대상**: 정확한 발음 (Accuracy)
- **세부 분석**: 
  - 개별 음소별 점수
  - 음향 특성 (F0, Energy)
  - 음성 시스템 정보 (phoneme error rate 등)
- **피드백 방식**: AI 기반 상세 피드백

### FluencyPro (유강성 평가)
- **초점**: 연속된 발화의 자연스러움
- **평가 대상**: 발화 흐름 (Fluency)
- **세부 분석**:
  - 발화 속도
  - 쉼표 패턴
  - 조음 속도
  - 정확한 음절 비율
- **피드백 방식**: 구조화된 권장사항 리스트

---

## 5. 사용 시나리오

### SpeechPro 사용 시기
- ✓ "이 발음이 맞는가?" → 발음 정확도 검증
- ✓ "어떤 음소가 틀렸는가?" → 개별 음소 분석
- ✓ "어떻게 개선하면 되는가?" → AI 상세 피드백
- ✓ 초급자 발음 교정

### FluencyPro 사용 시기
- ✓ "자연스럽게 말하는가?" → 유강성 평가
- ✓ "발화 속도가 적절한가?" → 속도 분석
- ✓ "쉼표를 잘 사용하는가?" → 호흡 패턴 분석
- ✓ 중급자 이상 자연스러운 표현 학습

---

## 6. 통합 사용 제안

**최적의 발음 학습 플로우**:

1. **Phase 1**: SpeechPro로 정확도 검증
   - 목표: 정확한 발음 습득
   - 피드백: AI 기반 세부 지도

2. **Phase 2**: FluencyPro로 유강성 평가
   - 목표: 자연스러운 발화
   - 피드백: 속도, 호흡, 조음 개선

3. **결과**: 정확하면서도 자연스러운 발음 완성

