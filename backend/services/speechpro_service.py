"""
SpeechPro API 서비스

한국어 발음 평가를 위한 SpeechPro API 통합 서비스
GTP (Grapheme-to-Phoneme), Model, Score의 3단계 워크플로우를 지원합니다.
"""

import os
import uuid
import requests
import base64
from typing import Dict, Any, Optional, List
from dataclasses import dataclass


# SpeechPro API 설정
SPEECHPRO_URL = os.getenv('SPEECHPRO_TARGET', 'http://112.220.79.222:33005/speechpro')


# 공백 정규화 함수
def normalize_spaces(text: str) -> str:
    """
    다양한 공백 문자를 일반 공백으로 정규화
    
    SpeechPro API는 표준 공백만 허용하므로 특수 공백을 제거해야 합니다.
    - \\u00A0 (NBSP - Non-breaking space)
    - \\u2002 (En Space)
    - \\u2003 (Em Space)
    - \\u2009 (Thin Space)
    - \\t (Tab)
    """
    special_spaces = {
        '\u00A0': ' ',  # NBSP
        '\u2002': ' ',  # En Space
        '\u2003': ' ',  # Em Space
        '\u2009': ' ',  # Thin Space
        '\t': ' ',      # Tab
    }
    
    for special, normal in special_spaces.items():
        text = text.replace(special, normal)
    
    # 연속된 공백을 단일 공백으로 변환
    while '  ' in text:
        text = text.replace('  ', ' ')
    
    return text.strip()


@dataclass
class GTPResult:
    """GTP API 응답"""
    id: str
    text: str
    syll_ltrs: str  # 음절 글자 (언더스코어로 구분)
    syll_phns: str  # 음절 음소 (언더스코어로 구분)
    error_code: int
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'text': self.text,
            'syll_ltrs': self.syll_ltrs,
            'syll_phns': self.syll_phns,
            'error_code': self.error_code
        }


@dataclass
class ModelResult:
    """Model API 응답"""
    id: str
    text: str
    syll_ltrs: str
    syll_phns: str
    fst: str  # Finite State Transducer 모델
    error_code: int
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'text': self.text,
            'syll_ltrs': self.syll_ltrs,
            'syll_phns': self.syll_phns,
            'fst': self.fst,
            'error_code': self.error_code
        }


@dataclass
class ScoreResult:
    """Score API 응답"""
    score: float
    details: Dict[str, Any]
    error_code: int
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'score': self.score,
            'details': self.details,
            'error_code': self.error_code
        }


def call_speechpro_gtp(text: str, request_id: Optional[str] = None) -> GTPResult:
    """
    GTP (Grapheme-to-Phoneme) API 호출

    한국어 텍스트를 음소로 변환합니다.

    Args:
        text: 변환할 한국어 텍스트
        request_id: 요청 ID (선택, 없으면 자동 생성)

    Returns:
        GTPResult: GTP 처리 결과

    Raises:
        ValueError: 텍스트가 비어있을 경우
        requests.RequestException: API 호출 실패 시

    Examples:
        >>> result = call_speechpro_gtp("안녕하세요")
        >>> result.syll_ltrs
        '안_녕_하_세_요'
    """
    if not text or not text.strip():
        raise ValueError("text is required")

    # 공백 정규화
    text = normalize_spaces(text)

    # 요청 ID 생성
    if not request_id:
        request_id = f"gtp_{uuid.uuid4().hex[:8]}"

    # SpeechPro GTP API 호출
    url = f"{SPEECHPRO_URL.rstrip('/')}/gtp"

    payload = {
        "id": request_id,
        "text": text
    }

    try:
        response = requests.post(
            url,
            json=payload,
            headers={'Content-Type': 'application/json'},
            timeout=15
        )
        response.raise_for_status()
        data = response.json()
        
        return GTPResult(
            id=data.get('id', request_id),
            text=data.get('text', text),
            syll_ltrs=data.get('syll ltrs', ''),
            syll_phns=data.get('syll phns', ''),
            error_code=data.get('error code', 0)
        )
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"GTP API 호출 실패: {str(e)}")


def call_speechpro_model(
    text: str,
    syll_ltrs: str,
    syll_phns: str,
    request_id: Optional[str] = None
) -> ModelResult:
    """
    Model API - FST 발음 모델 생성

    GTP 결과를 바탕으로 발음 모델(FST)을 생성합니다.

    Args:
        text: 한국어 텍스트
        syll_ltrs: GTP에서 받은 음절 글자
        syll_phns: GTP에서 받은 음절 음소
        request_id: 요청 ID

    Returns:
        ModelResult: 모델 생성 결과

    Raises:
        ValueError: 필수 파라미터가 비어있을 경우
        requests.RequestException: API 호출 실패 시

    Examples:
        >>> gtp_result = call_speechpro_gtp("안녕하세요")
        >>> model_result = call_speechpro_model(
        ...     text="안녕하세요",
        ...     syll_ltrs=gtp_result.syll_ltrs,
        ...     syll_phns=gtp_result.syll_phns
        ... )
    """
    if not all([text, syll_ltrs, syll_phns]):
        raise ValueError("text, syll_ltrs, syll_phns are required")

    if not request_id:
        request_id = f"model_{uuid.uuid4().hex[:8]}"

    url = f"{SPEECHPRO_URL.rstrip('/')}/model"

    payload = {
        "id": request_id,
        "text": text,
        "syll ltrs": syll_ltrs,
        "syll phns": syll_phns
    }

    try:
        response = requests.post(
            url,
            json=payload,
            headers={'Content-Type': 'application/json'},
            timeout=20
        )
        response.raise_for_status()
        data = response.json()
        
        return ModelResult(
            id=data.get('id', request_id),
            text=data.get('text', text),
            syll_ltrs=data.get('syll ltrs', syll_ltrs),
            syll_phns=data.get('syll phns', syll_phns),
            fst=data.get('fst', ''),
            error_code=data.get('error code', 0)
        )
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Model API 호출 실패: {str(e)}")


def call_speechpro_score(
    text: str,
    syll_ltrs: str,
    syll_phns: str,
    fst: str,
    audio_data: bytes,
    request_id: Optional[str] = None
) -> ScoreResult:
    """
    Score JSON API - 발음 평가

    사용자의 음성 데이터를 전송하여 발음 정확도를 평가합니다.

    Args:
        text: 원문 텍스트
        syll_ltrs: 음절 글자
        syll_phns: 음절 음소
        fst: FST 모델 데이터
        audio_data: WAV 오디오 바이너리 데이터
        request_id: 요청 ID

    Returns:
        ScoreResult: 발음 평가 결과

    Raises:
        ValueError: 필수 파라미터가 비어있을 경우
        requests.RequestException: API 호출 실패 시

    Examples:
        >>> with open("recording.wav", "rb") as f:
        ...     audio = f.read()
        >>> score_result = call_speechpro_score(
        ...     text="안녕하세요",
        ...     syll_ltrs=model_result.syll_ltrs,
        ...     syll_phns=model_result.syll_phns,
        ...     fst=model_result.fst,
        ...     audio_data=audio
        ... )
    """
    if not all([text, syll_ltrs, syll_phns, fst, audio_data]):
        raise ValueError("text, syll_ltrs, syll_phns, fst, audio_data are required")

    if not request_id:
        request_id = f"score_{uuid.uuid4().hex[:8]}"

    # 오디오 데이터를 Base64로 인코딩
    wav_usr = base64.b64encode(audio_data).decode('utf-8')
    print(f"[Score] Audio size: {len(audio_data)} bytes, Base64 size: {len(wav_usr)}, Text: {text}")

    url = f"{SPEECHPRO_URL.rstrip('/')}/scorejson"
    print(f"[Score] URL: {url}, Request ID: {request_id}")

    payload = {
        "id": request_id,
        "text": text,
        "syll ltrs": syll_ltrs,
        "syll phns": syll_phns,
        "fst": fst,
        "wav usr": wav_usr
    }

    try:
        print(f"[Score] Sending payload with FST length: {len(fst)}")
        response = requests.post(
            url,
            json=payload,
            headers={'Content-Type': 'application/json'},
            timeout=30  # 발음 평가 타임아웃 단축
        )
        print(f"[Score] Response status: {response.status_code}")
        response.raise_for_status()
        data = response.json()
        print(f"[Score] Response data: {data}")
        
        # 일부 SpeechPro 빌드에서는 scorejson 응답이 {"score": ..., "details": ...}
        # 대신 {"result": {"quality": {...}, "fluency": {...}}} 형태로 반환됨.
        # 점수가 없으면 quality.sentences의 평균 점수를 사용하고, 상세는 result 전체를 전달한다.
        raw_score = data.get('score')
        details = data.get('details') or data.get('result') or {}

        computed_score = raw_score
        if computed_score is None:
            quality = details.get('quality', {}) if isinstance(details, dict) else {}
            sentences = quality.get('sentences', []) if isinstance(quality, dict) else []
            # !SIL과 0점(무음) 문장은 제외하고 평균을 계산
            scored_sentences = [
                s.get('score')
                for s in sentences
                if isinstance(s, dict)
                and s.get('score') is not None
                and s.get('text') not in ('!SIL', '')
                and s.get('score') > 0
            ]
            if scored_sentences:
                computed_score = sum(scored_sentences) / len(scored_sentences)
            else:
                computed_score = 0.0

        return ScoreResult(
            score=float(computed_score or 0.0),
            details=details,
            error_code=data.get('error code', 0)
        )
    except requests.exceptions.RequestException as e:
        print(f"[Score] Error: {str(e)}")
        raise RuntimeError(f"Score API 호출 실패: {str(e)}")


def speechpro_full_workflow(
    text: str,
    audio_data: bytes,
    request_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    SpeechPro 전체 워크플로우 실행

    1. GTP: 텍스트 → 음소 변환
    2. Model: 발음 모델 생성
    3. Score: 음성 발음 평가

    Args:
        text: 평가할 한국어 텍스트
        audio_data: WAV 오디오 바이너리 데이터
        request_id: 요청 ID (선택)

    Returns:
        Dict[str, Any]: {
            'gtp': GTPResult,
            'model': ModelResult,
            'score': ScoreResult,
            'overall_score': float
        }

    Raises:
        ValueError: 필수 파라미터가 비어있을 경우
        RuntimeError: API 호출 실패 시

    Examples:
        >>> with open("recording.wav", "rb") as f:
        ...     audio = f.read()
        >>> result = speechpro_full_workflow("안녕하세요", audio)
        >>> print(f"점수: {result['overall_score']}")
    """
    if not text or not text.strip():
        raise ValueError("text is required")
    
    if not audio_data or len(audio_data) == 0:
        raise ValueError("audio_data is required")

    # 공백 정규화
    text = normalize_spaces(text)

    if not request_id:
        request_id = f"workflow_{uuid.uuid4().hex[:8]}"

    try:
        # Step 1: GTP (텍스트 → 음소)
        gtp_result = call_speechpro_gtp(text, request_id)
        
        if gtp_result.error_code != 0:
            raise RuntimeError(f"GTP 오류: error_code={gtp_result.error_code}")

        # Step 2: Model (발음 모델 생성)
        model_result = call_speechpro_model(
            text=text,
            syll_ltrs=gtp_result.syll_ltrs,
            syll_phns=gtp_result.syll_phns,
            request_id=request_id
        )
        
        if model_result.error_code != 0:
            raise RuntimeError(f"Model 오류: error_code={model_result.error_code}")

        # Step 3: Score (발음 평가)
        score_result = call_speechpro_score(
            text=text,
            syll_ltrs=model_result.syll_ltrs,
            syll_phns=model_result.syll_phns,
            fst=model_result.fst,
            audio_data=audio_data,
            request_id=request_id
        )
        
        if score_result.error_code != 0:
            raise RuntimeError(f"Score 오류: error_code={score_result.error_code}")

        return {
            'gtp': gtp_result.to_dict(),
            'model': model_result.to_dict(),
            'score': score_result.to_dict(),
            'overall_score': score_result.score,
            'success': True
        }

    except Exception as e:
        return {
            'error': str(e),
            'success': False,
            'overall_score': 0.0
        }


def get_speechpro_url() -> str:
    """현재 SpeechPro API URL 반환"""
    return SPEECHPRO_URL


def set_speechpro_url(url: str) -> None:
    """SpeechPro API URL 설정"""
    global SPEECHPRO_URL
    SPEECHPRO_URL = url
