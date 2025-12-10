# SpeechPro API 호출 흐름

## 📊 전체 아키텍처

```
사용자 (브라우저)
    ↓
    ├─→ [1] 웹페이지: /speechpro-practice 접속
    │   └─→ 문장 데이터 로드 (fetch /api/speechpro/sentences)
    │
    ├─→ [2] 음성 녹음 (브라우저 네이티브 API)
    │   └─→ WAV 오디오 파일 생성
    │
    └─→ [3] 발음 평가 요청
        └─→ POST /api/speechpro/evaluate
            (text + audio 전송)
                ↓
            FastAPI 서버 (main.py)
                ↓
            speechpro_full_workflow() 호출
                ↓
                ├─→ [Step 1] GTP API 호출
                │   URL: http://112.220.79.222:33005/speechpro/gtp
                │   입력: {"id": "...", "text": "안녕하세요"}
                │   출력: {"syll_ltrs": "안_녕_하_세_요", "syll_phns": "..."}
                │
                ├─→ [Step 2] Model API 호출
                │   URL: http://112.220.79.222:33005/speechpro/model
                │   입력: {"text": "...", "syll_ltrs": "...", "syll_phns": "..."}
                │   출력: {"fst": "..."}
                │
                └─→ [Step 3] Score API 호출
                    URL: http://112.220.79.222:33005/speechpro/scorejson
                    입력: {"text": "...", "syll_ltrs": "...", "syll_phns": "...", "fst": "...", "wav usr": "..."}
                    출력: {"score": 85.5, "details": {...}}
                        ↓
                    결과 반환
                        ↓
              사용자 (결과 표시)
```

---

## 🔍 상세 API 호출 과정

### Step 1: GTP (Grapheme-to-Phoneme)

**함수:** `call_speechpro_gtp(text)`

**목적:** 한글 텍스트를 음소(Phoneme)로 변환

**요청:**
```
POST http://112.220.79.222:33005/speechpro/gtp
Content-Type: application/json

{
  "id": "gtp_edce8c0e",
  "text": "안녕하세요"
}
```

**응답:**
```json
{
  "id": "gtp_edce8c0e",
  "text": "안녕하세요",
  "syll ltrs": "안_녕_하_세_요",
  "syll phns": "aa nf_nn yv ng_h0 aa_s0 ee_yo",
  "error code": 0
}
```

**코드:**
```python
def call_speechpro_gtp(text: str, request_id: Optional[str] = None) -> GTPResult:
    # 1. 공백 정규화 (NBSP, Tab 등 제거)
    text = normalize_spaces(text)
    
    # 2. 요청 ID 생성
    if not request_id:
        request_id = f"gtp_{uuid.uuid4().hex[:8]}"
    
    # 3. API 호출
    url = f"{SPEECHPRO_URL}/gtp"
    payload = {"id": request_id, "text": text}
    
    response = requests.post(url, json=payload, timeout=30)
    data = response.json()
    
    # 4. 결과 반환
    return GTPResult(
        id=data.get('id'),
        text=data.get('text'),
        syll_ltrs=data.get('syll ltrs'),  # ← 다음 단계에서 사용
        syll_phns=data.get('syll phns'),  # ← 다음 단계에서 사용
        error_code=data.get('error code')
    )
```

---

### Step 2: Model (FST 모델 생성)

**함수:** `call_speechpro_model(text, syll_ltrs, syll_phns)`

**목적:** GTP 결과를 바탕으로 발음 평가를 위한 FST 모델 생성

**요청:**
```
POST http://112.220.79.222:33005/speechpro/model
Content-Type: application/json

{
  "id": "model_a1b2c3d4",
  "text": "안녕하세요",
  "syll ltrs": "안_녕_하_세_요",
  "syll phns": "aa nf_nn yv ng_h0 aa_s0 ee_yo"
}
```

**응답:**
```json
{
  "id": "model_a1b2c3d4",
  "text": "안녕하세요",
  "syll ltrs": "안_녕_하_세_요",
  "syll phns": "aa nf_nn yv ng_h0 aa_s0 ee_yo",
  "fst": "[복잡한 FST 모델 데이터]...",
  "error code": 0
}
```

**코드:**
```python
def call_speechpro_model(text: str, syll_ltrs: str, syll_phns: str, 
                        request_id: Optional[str] = None) -> ModelResult:
    # 1. 파라미터 검증
    if not all([text, syll_ltrs, syll_phns]):
        raise ValueError("필수 파라미터 부족")
    
    # 2. 요청 ID 생성
    if not request_id:
        request_id = f"model_{uuid.uuid4().hex[:8]}"
    
    # 3. API 호출
    url = f"{SPEECHPRO_URL}/model"
    payload = {
        "id": request_id,
        "text": text,
        "syll ltrs": syll_ltrs,  # ← GTP에서 받은 값
        "syll phns": syll_phns   # ← GTP에서 받은 값
    }
    
    response = requests.post(url, json=payload, timeout=30)
    data = response.json()
    
    # 4. 결과 반환
    return ModelResult(
        id=data.get('id'),
        text=data.get('text'),
        syll_ltrs=data.get('syll ltrs'),
        syll_phns=data.get('syll phns'),
        fst=data.get('fst'),  # ← 다음 단계에서 사용
        error_code=data.get('error code')
    )
```

---

### Step 3: Score (발음 평가)

**함수:** `call_speechpro_score(text, syll_ltrs, syll_phns, fst, audio_data)`

**목적:** 사용자 음성을 평가하여 발음 점수 계산

**요청:**
```
POST http://112.220.79.222:33005/speechpro/scorejson
Content-Type: application/json

{
  "id": "score_x1y2z3w4",
  "text": "안녕하세요",
  "syll ltrs": "안_녕_하_세_요",
  "syll phns": "aa nf_nn yv ng_h0 aa_s0 ee_yo",
  "fst": "[FST 모델 데이터]...",
  "wav usr": "[Base64 인코딩된 WAV 오디오]..."
}
```

**응답:**
```json
{
  "score": 85.5,
  "details": {
    "syllables": [...],
    "phonemes": [...]
  },
  "error code": 0
}
```

**코드:**
```python
def call_speechpro_score(text: str, syll_ltrs: str, syll_phns: str, 
                        fst: str, audio_data: bytes, 
                        request_id: Optional[str] = None) -> ScoreResult:
    # 1. 파라미터 검증
    if not all([text, syll_ltrs, syll_phns, fst, audio_data]):
        raise ValueError("필수 파라미터 부족")
    
    # 2. 요청 ID 생성
    if not request_id:
        request_id = f"score_{uuid.uuid4().hex[:8]}"
    
    # 3. 오디오 데이터 Base64 인코딩
    wav_usr = base64.b64encode(audio_data).decode('utf-8')
    
    # 4. API 호출
    url = f"{SPEECHPRO_URL}/scorejson"
    payload = {
        "id": request_id,
        "text": text,
        "syll ltrs": syll_ltrs,           # ← Model에서 받은 값
        "syll phns": syll_phns,           # ← Model에서 받은 값
        "fst": fst,                       # ← Model에서 받은 값
        "wav usr": wav_usr                # ← Base64 인코딩된 오디오
    }
    
    response = requests.post(url, json=payload, timeout=60)
    data = response.json()
    
    # 5. 결과 반환
    return ScoreResult(
        score=data.get('score', 0.0),
        details=data.get('details', {}),
        error_code=data.get('error code', 0)
    )
```

---

### 전체 워크플로우: `speechpro_full_workflow()`

**함수:** `speechpro_full_workflow(text, audio_data)`

**목적:** 3단계를 모두 실행하여 발음 평가 완료

**코드:**
```python
def speechpro_full_workflow(text: str, audio_data: bytes, 
                           request_id: Optional[str] = None) -> Dict[str, Any]:
    # Step 1: GTP 실행
    gtp_result = call_speechpro_gtp(text, request_id)
    if gtp_result.error_code != 0:
        raise RuntimeError(f"GTP 오류: {gtp_result.error_code}")
    
    # Step 2: Model 실행 (GTP 결과 사용)
    model_result = call_speechpro_model(
        text=text,
        syll_ltrs=gtp_result.syll_ltrs,    # ← GTP 출력
        syll_phns=gtp_result.syll_phns,    # ← GTP 출력
        request_id=request_id
    )
    if model_result.error_code != 0:
        raise RuntimeError(f"Model 오류: {model_result.error_code}")
    
    # Step 3: Score 실행 (Model 결과 사용)
    score_result = call_speechpro_score(
        text=text,
        syll_ltrs=model_result.syll_ltrs,  # ← Model 출력
        syll_phns=model_result.syll_phns,  # ← Model 출력
        fst=model_result.fst,              # ← Model 출력
        audio_data=audio_data,
        request_id=request_id
    )
    if score_result.error_code != 0:
        raise RuntimeError(f"Score 오류: {score_result.error_code}")
    
    # 최종 결과 반환
    return {
        'gtp': gtp_result.to_dict(),
        'model': model_result.to_dict(),
        'score': score_result.to_dict(),
        'overall_score': score_result.score,
        'success': True
    }
```

---

## 🌐 FastAPI 엔드포인트

### 사용자 요청 처리

**엔드포인트:** `POST /api/speechpro/evaluate`

**코드:**
```python
@app.post("/api/speechpro/evaluate")
async def speechpro_evaluate(
    text: str = Form(...),
    audio: UploadFile = File(...)
):
    """통합 발음 평가 API"""
    try:
        # 1. 오디오 파일 읽기
        audio_content = await audio.read()
        
        # 2. 입력 검증
        text = text.strip()
        if not text or not audio_content:
            return JSONResponse(
                status_code=400,
                content={"error": "text and audio are required"}
            )
        
        # 3. SpeechPro 워크플로우 실행
        result = speechpro_full_workflow(text, audio_content)
        
        # 4. 결과 반환
        return JSONResponse(content=result)
    
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    except RuntimeError as e:
        return JSONResponse(status_code=503, content={"error": str(e)})
```

---

## 💻 프론트엔드 호출 방식

### JavaScript에서 평가 요청

**파일:** `templates/speechpro-practice.html`

**코드:**
```javascript
async function evaluatePronunciation() {
    const text = document.getElementById("evaluation-text").value.trim();
    const audioElement = document.getElementById("audio-playback");

    if (!text || !audioElement.src) {
        showError("문장과 음성을 입력하세요");
        return;
    }

    showLoading();

    try {
        // 1. 오디오 데이터 가져오기
        const audioBlob = await fetch(audioElement.src).then(r => r.blob());

        // 2. FormData 생성
        const formData = new FormData();
        formData.append("text", text);
        formData.append("audio", audioBlob, "recording.wav");

        // 3. API 호출
        const response = await fetch("/api/speechpro/evaluate", {
            method: "POST",
            body: formData
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error);
        }

        // 4. 결과 처리
        const result = await response.json();
        if (result.success) {
            displayResults(result);
        } else {
            showError(result.error);
        }
    } catch (error) {
        showError(`평가 중 오류: ${error.message}`);
    } finally {
        hideLoading();
    }
}
```

---

## 📊 데이터 흐름 요약

```
음성 오디오
    ↓
    └─→ Base64 인코딩
        ↓
        └─→ Score API 요청에 포함 ("wav usr")

평가 텍스트 (예: "안녕하세요")
    ↓
    ├─→ [정규화] 공백 제거/표준화
    │
    ├─→ GTP API
    │   입력: "안녕하세요"
    │   출력: syll_ltrs, syll_phns
    │
    ├─→ Model API
    │   입력: text + syll_ltrs + syll_phns (← GTP 출력)
    │   출력: fst
    │
    └─→ Score API
        입력: text + syll_ltrs + syll_phns + fst + audio
             (← 모두 이전 단계 출력)
        출력: score (0-100), details
```

---

## ⚠️ 에러 처리

모든 함수와 엔드포인트는 다음을 처리합니다:

1. **ValueError** (400) - 입력 파라미터 오류
2. **RuntimeError** (503) - SpeechPro 서버 연결 실패
3. **Exception** (500) - 일반적인 서버 오류

---

## 🔗 관련 파일

- `backend/services/speechpro_service.py` - API 호출 로직
- `main.py` - FastAPI 엔드포인트
- `templates/speechpro-practice.html` - 프론트엔드 UI
- `data/speechpro-sentences.json` - 평가 문장 데이터

---

**정리:** SpeechPro 3단계 API(GTP → Model → Score)를 순차적으로 호출하여 최종 발음 점수를 얻습니다.
