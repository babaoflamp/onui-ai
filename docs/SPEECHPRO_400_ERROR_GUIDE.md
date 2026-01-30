# SpeechPro Score API 400 Bad Request トラブルシューティングガイド

## 문제 상황

SpeechPro 발음 평가 시 "400 Bad Request" 오류가 발생하고 있습니다.

```
평가 중 오류: Score API 호출 실패: 400 Client Error: Bad Request 
for url: http://112.220.79.222:33005/speechpro/scorejson 
💡 문장이 너무 길거나 복잡할 수 있습니다. 더 짧은 문장으로 나누어 시도해보세요.
```

## 진단 방법

### 1단계: 브라우저 콘솔 확인

1. 브라우저에서 **F12** 또는 **개발자 도구** 열기
2. **Console** 탭으로 이동
3. 다시 평가 시도
4. 다음과 같은 로그 확인:

```
[Evaluate] Metadata attached: {
  syll_ltrs_len: 47,
  syll_phns_len: 149,
  fst_len: 28148,
  text_len: ...,
  audio_blob_size: ...,
  audio_blob_type: "audio/webm;codecs=opus"
}
[Evaluate] Validation result: {
  validation: {
    text: {valid: true, ...},
    audio: {valid: true, ...},
    ...
  }
}
```

**확인 사항:**
- ✓ 모든 메타데이터가 로드되었는가?
- ✓ `audio_blob_size`가 충분히 큰가? (최소 1000 bytes 이상)
- ✓ 음성 파일이 제대로 녹음되었는가?

### 2단계: 서버 로그 확인

서버 터미널에서 다음 로그 확인:

```
[Score] Audio size: 6444 bytes, Base64 size: 8592, Text: 서울은...
[Score] Sending payload with:
  - Text: 서울은...
  - syll_ltrs length: 63
  - syll_phns length: 209
  - fst length: 28148
  - wav_usr length: 8592
[Score] Response status: 400
[Score] Client error (status=400): 400 Bad Request
```

**확인 사항:**
- Audio size는 최소 1000 bytes 이상이어야 함
- 모든 메타데이터가 비어있지 않아야 함

### 3단계: 진단 스크립트 실행

```bash
python scripts/test_speechpro_score_api.py
```

**출력 예:**

```
============================================================
SpeechPro Score API Diagnostic Tool
============================================================
✓ API endpoint reachable
✗ 400 Bad Request with CSV data

Diagnostics:
  - Text is valid: True
  - syll_ltrs is valid: True
  - syll_phns is valid: True
  - fst is valid: True
```

## 해결 방법

### 가능성 1: 음성 녹음이 너무 짧거나 조용함

**증상:** `audio_blob_size < 5000`

**해결책:**
1. 더 천천히, 명확하게 발음하기
2. 마이크 위치 조정 (더 가깝게)
3. 배경 소음 줄이기

### 가능성 2: 더 짧은 문장 사용

Score API가 긴 문장을 처리하지 못할 수 있습니다.

**Before (실패):**
```
서울은 차도 많고 사람도 많아서 조금 복잡하지만 경치가 아름다운 도시입니다.
```

**After (성공):**
```
서울은 아름다운 도시입니다.
```

### 가능성 3: Score API 서버 상태 확인

원격 Score API 서버(`112.220.79.222:33005`)가 정상 작동 중인지 확인:

```bash
# 연결 테스트
curl -v http://112.220.79.222:33005/speechpro/scorejson

# 또는
curl -X POST http://112.220.79.222:33005/speechpro/scorejson \
  -H "Content-Type: application/json" \
  -d '{"id":"test","text":"테스트"}'
```

**예상 결과:**
- `200 OK` 또는 `400 Bad Request` (정상)
- `500+ Server Error` (서버 문제)
- Connection refused (서버 다운)

### 가능성 4: 메타데이터 자동 로드 확인

문장 선택 후 메타데이터가 자동으로 로드되어야 합니다.

**확인:**
1. 콘솔에서 `[Evaluate] Metadata attached` 메시지 확인
2. 없으면 메타데이터가 로드되지 않은 것

**수동 로드 (CSV에서 자동):**
```javascript
// 콘솔에서 실행
console.log("Selected:", appState.selectedSentence);
```

## 고급 진단

### 검증 API 직접 호출

```bash
# POST 요청으로 검증 API 호출
curl -X POST http://localhost:9000/api/speechpro/validate \
  -F "text=서울은 아름다운 도시입니다" \
  -F "audio=@recording.wav" \
  -F "syll_ltrs=..." \
  -F "syll_phns=..." \
  -F "fst=..."
```

응답에서:
```json
{
  "validation": {
    "text": {"valid": true, "length": 13},
    "audio": {"valid": true, "size": 32000},
    ...
  },
  "all_valid": true
}
```

### 로컬 Score API 테스트 (동기화 필요)

```python
# Python에서 테스트
import sys; sys.path.insert(0, '.')
from backend.services.speechpro_service import call_speechpro_score

result = call_speechpro_score(
    text="테스트",
    syll_ltrs="...",
    syll_phns="...",
    fst="...",
    audio_data=open("test.wav", "rb").read()
)
print(result)
```

## 임시 해결책

Score API가 지속적으로 400을 반환하는 경우:

1. **더 짧은 문장 사용** (5-10 글자)
2. **명확하고 천천히 발음**
3. **배경 소음 제거**
4. **다른 문장으로 시도** (CSV의 다른 행)

## 최종 체크리스트

- [ ] 브라우저 콘솔에서 `[Evaluate] Metadata attached` 보임
- [ ] `audio_blob_size > 5000` 확인
- [ ] `syll_ltrs`, `syll_phns`, `fst` 모두 비어있지 않음
- [ ] 5글자 이상 20글자 미만의 문장 사용
- [ ] 마이크가 정상 작동하고 충분히 큰 목소리로 발음
- [ ] 서버 로그에서 오류 메시지 확인

## 문의

위 단계를 모두 따랐는데도 문제가 계속되면:

1. **브라우저 콘솔** 전체 로그 (F12 → Console 탭)
2. **서버 터미널** 오류 메시지
3. 사용한 **문장**
4. **진단 스크립트** 출력 결과

를 함께 제공하면 더 구체적인 도움을 드릴 수 있습니다.
