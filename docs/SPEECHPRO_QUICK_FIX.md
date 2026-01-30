# SpeechPro 400 Error Quick Fix Guide

## 🔴 Error Message
```
❌ 오류
평가 중 오류: Score API 호출 실패: 400 Client Error: Bad Request 
for url: http://112.220.79.222:33005/speechpro/scorejson 
💡 문장이 너무 길거나 복잡할 수 있습니다. 더 짧은 문장으로 나누어 시도해보세요.
```

## 🚀 Quick Fixes (순서대로 시도)

### 1️⃣ 더 짧은 문장 사용 (가장 효과적)
- **❌ 피해야 할 문장:** `서울은 차도 많고 사람도 많아서 조금 복잡하지만 경치가 아름다운 도시입니다.` (32글자)
- **✅ 추천 문장:** `서울은 아름다운 도시입니다.` (15글자)
- 또는: `버스를 타고 회사에 갑니다.` (14글자)

### 2️⃣ 명확하고 큰 목소리로 발음
- 마이크가 귀에서 20cm 거리에 있도록 배치
- 천천히 정확하게 발음
- 녹음 시간 최소 2초 이상 (최대 10초)
- 배경 소음이 없는 조용한 환경

### 3️⃣ 다른 문장으로 시도
드롭다운에서 다른 문장 선택:
- 서울은 차도 많고 사람도 많아요.
- 버스는 사람이 많아서 복잡합니다.
- 약을 사러 약국에 갔어요.
- 저는 버스를 자주 타는 편이에요.

### 4️⃣ 페이지 새로고침
```
Ctrl + F5 (Windows)
Cmd + Shift + R (Mac)
```

### 5️⃣ 브라우저 캐시 삭제
1. DevTools 열기 (F12)
2. Settings → Storage → Clear site data
3. 페이지 새로고침

## 🔍 문제 진단

### 브라우저 콘솔 확인 (F12)
다음 로그가 보이는지 확인:
```
✓ [Evaluate] Metadata attached: {
    syll_ltrs_len: 47,
    syll_phns_len: 149,
    fst_len: 28148,
    audio_blob_size: 32000  ← 이 값이 크면 좋음 (최소 5000)
}

✓ [Evaluate] Validation result: {
    all_valid: true
}
```

### 서버 로그 확인 (개발자용)
터미널에서 다음 메시지 확인:
```
✓ [Score] Audio data size adequate: 6444 bytes
✓ [Score] Valid WAV header detected
[Score] Response status: 400
```

## ⚠️ 여전히 안 되면

1. **다른 브라우저 시도** (Chrome, Firefox, Safari)
2. **다른 기기의 마이크 시도** (외장 마이크)
3. **개인정보 보호 모드 비활성화**
   - DevTools → Settings → Disable cache (checked)를 unchecked로 변경

## 📊 작동 여부 테스트

### 정상 작동 (성공 사례)
```
- 문장: "안녕하세요" (5글자)
- 녹음 시간: 3초
- 마이크: 조용한 환경, 충분한 음량
- 결과: ✓ 점수 표시
```

### 실패 사례
```
- 문장: 매우 긴 복잡한 문장 (30글자 이상)
- 녹음 시간: < 1초
- 마이크: 너무 멀거나 소음 많음
- 결과: ❌ 400 Bad Request
```

## 🛠️ 고급 진단

### 1. 검증 API 테스트
브라우저 콘솔에서:
```javascript
fetch('/api/speechpro/validate', {
  method: 'POST',
  body: new FormData(/* form element */)
}).then(r => r.json()).then(console.log)
```

### 2. 진단 스크립트 실행
```bash
python scripts/test_speechpro_score_api.py
```

### 3. 원격 API 직접 테스트
```bash
curl -v http://112.220.79.222:33005/speechpro/scorejson
```

## 📞 추가 지원이 필요하면

다음 정보를 함께 제공해주세요:

1. 📸 **브라우저 콘솔 스크린샷** (F12 → Console)
   ```
   [Evaluate] Metadata attached: {...}
   [Evaluate] Running validation endpoint...
   [Evaluate] Validation result: {...}
   ```

2. 📝 **사용한 문장**: `_______________`

3. 🔊 **녹음 시간**: `__초`

4. 💻 **브라우저**: Chrome / Firefox / Safari / Edge

5. 🖥️ **OS**: Windows / Mac / Linux / Mobile

6. 📋 **서버 로그**:
   ```
   [Score] Audio size: _____ bytes
   [Score] Response status: _____
   ```

7. 🌐 **네트워크 상태**: 정상 / 느림 / 불안정

## ✅ 체크리스트

작동하기 전에 확인:
- [ ] 마이크가 정상 작동하는가?
- [ ] 마이크 권한을 허용했는가?
- [ ] 조용한 환경에서 시도했는가?
- [ ] 음량이 충분히 큰가?
- [ ] 5-20글자 문장을 사용했는가?
- [ ] 최소 2초 이상 녹음했는가?
- [ ] 다른 문장으로 시도해봤는가?
- [ ] 페이지를 새로고침해봤는가?
- [ ] 다른 브라우저로 시도해봤는가?

## 📚 참고 자료

- 상세 가이드: [SPEECHPRO_400_ERROR_GUIDE.md](SPEECHPRO_400_ERROR_GUIDE.md)
- 기술 분석: [SPEECHPRO_400_INVESTIGATION.md](SPEECHPRO_400_INVESTIGATION.md)
- 진단 도구: [scripts/test_speechpro_score_api.py](../scripts/test_speechpro_score_api.py)

---

**Last Updated:** 2024-01-16  
**Status:** ✓ Diagnostic tools added, troubleshooting guide available
