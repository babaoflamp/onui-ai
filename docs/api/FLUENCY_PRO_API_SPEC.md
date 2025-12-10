# Fluency Pro API 명세서

## 1. 개요

**Fluency Pro API**는 한국어 음성 유창성(Fluency) 평가를 제공하는 WebSocket 기반 실시간 음성 분석 API입니다.

### 주요 기능
- 실시간 음성 녹음 및 스트리밍
- 한국어 음절 정확도 평가
- 말하기 속도 분석
- 인식된 텍스트 반환 (오류 태그 포함)

---

## 2. 연결 정보

### 엔드포인트
| 환경 | 프로토콜 | 주소 |
|------|---------|------|
| HTTP | WS | `ws://112.220.79.218:33043/ws` |
| HTTPS | WSS | `wss://112.220.79.218:33043/ws` |

### 통신 방식
- **프로토콜**: WebSocket (RFC 6455)
- **데이터 형식**: JSON 메시지 + 바이너리 음성 데이터
- **인코딩**: UTF-8 (텍스트), 16-bit PCM (음성)
- **샘플레이트**: 8,000 Hz (리샘플링 필수)
- **채널**: Mono (1채널)

---

## 3. 메시지 형식

### 3.1 클라이언트 → 서버

#### JOIN 메시지 (연결 직후)
```json
{
  "language": "ko",
  "cmd": "join",
  "answer": "한국에서 대중교통을 이용할 때는 교통카드를 사용하면 더 편리해요."
}
```

| 필드 | 타입 | 설명 | 필수 |
|------|------|------|------|
| `language` | string | 언어 코드 (`ko`: 한국어) | ✓ |
| `cmd` | string | 명령어 (`join`) | ✓ |
| `answer` | string | 평가 대상 한국어 문장 | ✓ |

**전송 시점**: WebSocket 연결 성공 직후 (onopen 이벤트)

---

#### 음성 데이터 (실시간 스트림)
```
바이너리 Blob 데이터
- 형식: 16-bit PCM (Int16Array)
- 샘플레이트: 8,000 Hz
- 채널: Mono
- 버퍼 크기: 4,096 샘플 (~512ms)
```

**전송 시점**: 마이크 버튼 클릭 후 녹음 중지 시까지 연속 전송

**데이터 변환 프로세스**:
```javascript
// 1. 오디오 컨텍스트에서 데이터 수신
let inputData = audioContext.getChannelData(0);  // Float32Array

// 2. 필요시 8kHz로 리샘플링
let resampled = resampleBuffer(inputData, 
                               audioContext.sampleRate, 
                               8000);

// 3. Float32 → 16-bit PCM 변환
let int16Data = new Int16Array(resampled.length);
for (let i = 0; i < resampled.length; i++) {
    let s = Math.max(-1, Math.min(1, resampled[i]));
    int16Data[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
}

// 4. Blob으로 변환 후 전송
let blob = new Blob([int16Data.buffer], { type: "audio/raw" });
ws.send(blob);
```

---

#### QUIT 메시지 (녹음 종료)
```json
{
  "language": "ko",
  "cmd": "quit"
}
```

| 필드 | 타입 | 설명 | 필수 |
|------|------|------|------|
| `language` | string | 언어 코드 (`ko`) | ✓ |
| `cmd` | string | 명령어 (`quit`) | ✓ |

**전송 시점**: 녹음 중지 버튼 클릭 시

---

### 3.2 서버 → 클라이언트

#### REPLY 메시지 (JOIN 응답)
```json
{
  "event": "reply"
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `event` | string | 이벤트 타입 (`reply`) |

**의미**: 서버가 JOIN 메시지를 받았으며, 음성 데이터 전송을 시작할 준비 완료

---

#### 평가 완료 메시지 (성공)
```json
{
  "success": true,
  "result": {
    "SpeechproFluency": {
      "total_reading_words": 32,
      "total_correct_words": 29,
      "total_duration": 5.175,
      "reading_words_per_unit": 6.184,
      "correct_words_per_unit": 5.604
    },
    "output": "한국에서 <0.09> 대중교통을 <0.12> 이용할 때는 R교통카드를 사용하면 더 편리해요"
  },
  "event": "new:text"
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `success` | boolean | 평가 성공 여부 |
| `result.SpeechproFluency` | object | 평가 결과 메트릭 |
| `result.SpeechproFluency.total_reading_words` | integer | 읽은 총 음절 수 |
| `result.SpeechproFluency.total_correct_words` | integer | 맞게 읽은 총 음절 수 |
| `result.SpeechproFluency.total_duration` | float | 전체 음성 길이 (초) |
| `result.SpeechproFluency.reading_words_per_unit` | float | 초당 읽은 음절 수 |
| `result.SpeechproFluency.correct_words_per_unit` | float | 초당 맞게 읽은 음절 수 |
| `result.output` | string | STT 결과 텍스트 (오류 태그 포함) |
| `event` | string | 이벤트 타입 (`new:text`) |

**output 필드 특수 태그**:
- `<0.09>`: 침묵 시간 (초 단위)
- `R단어`: 발음되지 않은 음절 (생략)
- `Y단어`: 잘못 발음된 음절 (오류)

예시:
```
"비가 올 것 같아 <0.09> 우산을 Rchang겼는데"
  ↑ 침묵      ↑ 생략된 음절
```

---

#### 평가 실패 메시지
```json
{
  "success": false,
  "event": "error"
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `success` | boolean | 평가 실패 |
| `event` | string | 이벤트 타입 (`error`) |

**발생 원인**:
- 음성이 너무 작음
- 배경 잡음이 많음
- 음성이 확인되지 않음
- 서버 처리 오류

---

#### 연결 종료 메시지
```json
{
  "event": "close"
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `event` | string | 이벤트 타입 (`close`) |

**의미**: 서버가 평가를 완료했으며 연결을 종료

---

## 4. 동작 흐름 (Call Flow)

```
┌─────────────┐                              ┌──────────────────┐
│   클라이언트  │                              │  Fluency Pro     │
└──────┬──────┘                              └────────┬─────────┘
       │                                             │
       │ 1. WebSocket 연결                          │
       ├────────────────────────────────────────────>│
       │                                             │
       │ 2. JOIN 메시지 전송                         │
       ├───────────────────────────────────────────>│
       │   {language: "ko", cmd: "join", answer: "..."} │
       │                                             │
       │                 REPLY 이벤트                 │
       │<────────────────────────────────────────────┤
       │                                             │
       │ 3. 음성 데이터 스트림 전송 (실시간)          │
       ├───────────────────────────────────────────>│
       │   Blob (16-bit PCM, 8kHz)                  │
       │   Blob (16-bit PCM, 8kHz)                  │
       │   Blob (16-bit PCM, 8kHz)                  │
       │   ...                                       │
       │                                             │
       │ 4. QUIT 메시지 전송                         │
       ├───────────────────────────────────────────>│
       │   {language: "ko", cmd: "quit"}            │
       │                                             │
       │          [서버에서 음성 분석 진행]          │
       │                                             │
       │                평가 결과 메시지              │
       │<────────────────────────────────────────────┤
       │ {success: true, result: {...}, event: ...} │
       │                                             │
       │                CLOSE 이벤트                 │
       │<────────────────────────────────────────────┤
       │                                             │
       │ 5. 연결 종료                               │
       ├────────────────────────────────────────────>│
       │                                             │
```

---

## 5. 실제 구현 예제

### JavaScript 클라이언트 구현

```javascript
// 1. WebSocket 연결
const wsUri = (location.protocol == "http:") 
    ? "ws://112.220.79.218:33043/ws"
    : "wss://112.220.79.218:33043/ws";

const ws = new WebSocket(wsUri);
ws.binaryType = "arraybuffer";

// 2. 연결 성공 이벤트
ws.onopen = function(evt) {
    console.log("[연결됨]");
    
    // JOIN 메시지 전송
    const joinMsg = JSON.stringify({
        language: "ko",
        cmd: "join",
        answer: "한국에서 대중교통을 이용할 때는 교통카드를 사용하면 더 편리해요."
    });
    ws.send(joinMsg);
};

// 3. 메시지 수신 이벤트
ws.onmessage = function(evt) {
    const data = JSON.parse(evt.data);
    
    if (data.event === "reply") {
        console.log("[준비됨] 음성 데이터 전송 시작");
        startSendingAudio();
        
    } else if (data.success === true) {
        console.log("[평가 완료]");
        console.log("읽은 음절:", data.result.SpeechproFluency.total_reading_words);
        console.log("맞은 음절:", data.result.SpeechproFluency.total_correct_words);
        console.log("인식 결과:", data.result.output);
        
    } else if (data.success === false) {
        console.error("[평가 실패]");
        alert("녹음을 다시 진행해 주세요.");
    }
};

// 4. 오류 이벤트
ws.onerror = function(evt) {
    console.error("[오류]", evt);
};

// 5. 연결 종료 이벤트
ws.onclose = function(evt) {
    if (evt.code === 1006) {
        alert("연결이 비정상적으로 종료되었습니다.\n마이크를 확인해주세요.");
    }
};

// 6. 음성 데이터 전송 함수
function startSendingAudio() {
    let audioContext = new AudioContext();
    let source = audioContext.createMediaStreamSource(mediaStream);
    let processor = audioContext.createScriptProcessor(4096, 1, 1);
    
    source.connect(processor);
    processor.connect(audioContext.destination);
    
    processor.onaudioprocess = function(e) {
        let inputData = e.inputBuffer.getChannelData(0);
        
        // 리샘플링 (필요시)
        let processed = (audioContext.sampleRate === 8000) 
            ? inputData 
            : resampleBuffer(inputData, audioContext.sampleRate, 8000);
        
        // Float32 → 16-bit PCM 변환
        let int16Data = new Int16Array(processed.length);
        for (let i = 0; i < processed.length; i++) {
            let s = Math.max(-1, Math.min(1, processed[i]));
            int16Data[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
        }
        
        // 전송
        ws.send(int16Data.buffer);
    };
}

// 7. 녹음 중지 함수
function stopRecording() {
    // QUIT 메시지 전송
    const quitMsg = JSON.stringify({
        language: "ko",
        cmd: "quit"
    });
    ws.send(quitMsg);
}
```

---

## 6. 오류 처리

### WebSocket 종료 코드

| 코드 | 설명 | 처리 방법 |
|------|------|---------|
| 1000 | 정상 종료 | - |
| 1006 | 비정상 종료 | 마이크 연결 확인, 재시도 |
| 1002 | 프로토콜 오류 | 메시지 형식 확인 |
| 1003 | 지원하지 않는 데이터 | 데이터 형식 확인 |

### 일반적인 오류 상황

| 상황 | 원인 | 해결책 |
|------|------|-------|
| `success: false` | 음성 품질 낮음 | 조용한 장소에서 다시 녹음 |
| `getUserMedia 거부` | 마이크 권한 없음 | 브라우저 권한 설정 확인 |
| `"NotFoundError"` | 마이크 없음 | 시스템 마이크 연결 확인 |
| `연결 시간초과` | 서버 응답 없음 | 서버 상태 확인, 방화벽 확인 |

---

## 7. 성능 가이드

### 권장 사항

| 항목 | 권장값 | 설명 |
|------|-------|------|
| 샘플레이트 | 8,000 Hz | 한국어 음성 인식에 최적화 |
| 버퍼 크기 | 4,096 샘플 | 약 512ms 지연, 네트워크 효율성 균형 |
| 음성 길이 | 3~30초 | 너무 짧거나 길면 정확도 저하 |
| 배경 잡음 | <50dB | 조용한 환경 권장 |
| 네트워크 대역폭 | 128 kbps 이상 | 안정적인 실시간 전송 필요 |

### 전송 데이터량 계산
```
초당 데이터량 = 샘플레이트 × 채널 × 샘플 크기
            = 8,000 Hz × 1 채널 × 2 byte
            = 16,000 bytes/sec
            ≈ 128 kbps
```

---

## 8. 보안 고려사항

### 권장 사항
1. **HTTPS 환경에서 WSS 사용** (암호화 통신)
2. **서버 주소 환경변수화** (하드코딩 방지)
3. **타임아웃 설정** (네트워크 오류 방지)
4. **입력 검증** (answer 필드 길이 제한)
5. **로깅 시 민감정보 제외** (음성 데이터 기록 금지)

### 데이터 프라이버시
- 음성 데이터는 암호화되어 전송해야 함 (WSS 사용)
- 서버에서 음성 데이터는 즉시 처리 후 삭제 권장
- 평가 결과만 클라이언트에 반환

---

## 9. 버전 정보

| 항목 | 정보 |
|------|------|
| API 버전 | 1.0 |
| 지원 언어 | 한국어 (ko) |
| 프로토콜 | WebSocket (RFC 6455) |
| 서버 주소 | 112.220.79.218:33043 |
| 작성 날짜 | 2025-12-09 |

---

## 10. 참고 자료

### 관련 파일
- `src/main/resources/static/js/fluency/fluency-websocket.js` - WebSocket 구현
- `src/main/resources/static/js/fluency/fluency.js` - UI 및 결과 처리
- `src/main/resources/templates/fluency/demo.html` - 프론트엔드 페이지

### 외부 라이브러리
- RecordRTC (음성 녹음)
- Web Audio API (음성 처리)
- jQuery (DOM 조작)

### 관련 표준
- [RFC 6455 - WebSocket Protocol](https://tools.ietf.org/html/rfc6455)
- [Web Audio API](https://www.w3.org/TR/webaudio/)
- [getUserMedia API](https://w3c.github.io/mediacapture-main/)
