# Google Cloud Speech-to-Text 설정 가이드

## 📋 필수 사항

### 1. Google Cloud 프로젝트 설정
```bash
# Google Cloud SDK 설치
curl https://sdk.cloud.google.com | bash

# Google Cloud 초기화
gcloud init

# 프로젝트 생성 또는 기존 프로젝트 선택
gcloud projects create [PROJECT_ID]
gcloud config set project [PROJECT_ID]
```

### 2. Speech-to-Text API 활성화
```bash
# API 활성화
gcloud services enable speech.googleapis.com
```

### 3. 서비스 계정 생성 및 인증
```bash
# 서비스 계정 생성
gcloud iam service-accounts create speech-stt \
  --display-name="Speech-to-Text Service Account"

# 프로젝트에 권한 부여
gcloud projects add-iam-policy-binding [PROJECT_ID] \
  --member="serviceAccount:speech-stt@[PROJECT_ID].iam.gserviceaccount.com" \
  --role="roles/speech.client"

# 서비스 계정 키 생성
gcloud iam service-accounts keys create ~/speech-key.json \
  --iam-account=speech-stt@[PROJECT_ID].iam.gserviceaccount.com
```

### 4. 환경 변수 설정

#### 방법 1: 로컬 개발 환경
```bash
# .env 파일에 추가
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/speech-key.json"

# 또는 직접 설정
export GOOGLE_APPLICATION_CREDENTIALS="$HOME/speech-key.json"
```

#### 방법 2: 프로덕션 배포 (systemd)
```bash
# /etc/systemd/system/onui-ai.service 수정
[Service]
Environment="GOOGLE_APPLICATION_CREDENTIALS=/opt/onui-ai/speech-key.json"
```

## 🔧 Python 코드에서의 사용

### 기본 사용법
```python
from google.cloud import speech

# 클라이언트 자동으로 GOOGLE_APPLICATION_CREDENTIALS에서 인증
client = speech.SpeechClient()

# 음성 파일 읽기
with open("audio.wav", "rb") as audio_file:
    content = audio_file.read()

# 인식 설정
audio = speech.RecognitionAudio(content=content)
config = speech.RecognitionConfig(
    encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
    sample_rate_hertz=16000,
    language_code="ko-KR",
)

# 인식 실행
response = client.recognize(config=config, audio=audio)

# 결과 처리
for result in response.results:
    print(f"Transcript: {result.alternatives[0].transcript}")
```

## 💰 가격 정보

- **Google Cloud Speech-to-Text**: 분당 $0.024 (한국어 기준)
- **Free Tier**: 매월 첫 60분 무료
- 자세한 가격: https://cloud.google.com/speech-to-text/pricing

## 🧪 테스트 방법

### 1. 서버 시작
```bash
# 개발 서버 시작
python -m uvicorn main:app --host 0.0.0.0 --port 9000 --reload
```

### 2. 테스트 페이지 접속
```
http://localhost:9000/stt-api-test
```

### 3. Google STT 엔진 선택 및 테스트
1. "🔍 Google" 버튼 클릭
2. 🎙️ 녹음 시작 또는 📁 파일 선택
3. ▶️ STT 실행 버튼 클릭

### 4. 명령줄에서 테스트
```bash
# 테스트 오디오 파일 업로드
curl -X POST \
  -F "file=@test_audio.wav" \
  -F "language=ko-KR" \
  http://localhost:9000/api/stt/google

# 응답 예시:
# {"text": "안녕하세요"}
```

## 🐛 문제 해결

### 1. "Google Cloud Speech-to-Text is not configured" 오류
**원인**: Google Speech 패키지 미설치 또는 클라이언트 초기화 실패

**해결책**:
```bash
pip install google-cloud-speech
echo $GOOGLE_APPLICATION_CREDENTIALS  # 환경 변수 확인
```

### 2. "Permission denied" 오류
**원인**: 서비스 계정 인증 파일 경로 잘못됨

**해결책**:
```bash
# 파일 경로 확인
ls -la /path/to/speech-key.json

# 권한 확인
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/speech-key.json"
gcloud auth application-default print-access-token
```

### 3. "Audio too short" 오류
**원인**: 음성 파일이 너무 짧음

**해결책**:
- 최소 1초 이상의 음성 필요
- WAV 형식 권장 (PCM 16-bit, 16kHz)

## 📝 지원 오디오 형식

| 형식 | 인코딩 | 샘플레이트 |
|------|--------|----------|
| FLAC | FLAC | 8000 - 48000 Hz |
| WAV | LINEAR16 | 8000 - 16000 Hz (권장) |
| OGG | OGG_OPUS | 8000 - 48000 Hz |
| MP3 | MP3 | 8000 - 48000 Hz |
| M4A | M4A | 16000 Hz |

## 🔐 보안 주의사항

1. **비밀 키 관리**:
   - `speech-key.json`을 절대 Git에 커밋하지 마세요
   - `.gitignore`에 추가: `speech-key.json`

2. **환경 변수 보호**:
   - 프로덕션에서는 환경 변수로 관리
   - Docker 시크릿 또는 Kubernetes Secrets 사용

3. **API 키 회전**:
   ```bash
   # 기존 키 삭제 및 새 키 생성
   gcloud iam service-accounts keys delete [KEY_ID] \
     --iam-account=speech-stt@[PROJECT_ID].iam.gserviceaccount.com
   ```

## 📚 참고 링크

- [Google Cloud Speech-to-Text 문서](https://cloud.google.com/speech-to-text/docs)
- [Python 클라이언트 라이브러리](https://googleapis.dev/python/speech/latest/)
- [gcloud 설정 가이드](https://cloud.google.com/docs/authentication/getting-started)
