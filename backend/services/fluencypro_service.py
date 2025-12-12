"""
FluencyPro API 서비스
WebSocket 기반 실시간 한국어 유창성 평가 서비스
"""

import asyncio
import json
import base64
import struct
import os
from typing import Dict, Optional, Tuple
import websockets
from io import BytesIO
import wave
import logging

logger = logging.getLogger(__name__)

# FluencyPro WebSocket 엔드포인트
FLUENCYPRO_WS_URL = os.getenv("FLUENCYPRO_WS_URL", "ws://112.220.79.218:33043/ws")


def convert_audio_to_pcm(audio_data: bytes, target_sample_rate: int = 8000) -> bytes:
    """
    오디오 데이터를 16-bit PCM (8kHz, Mono)로 변환

    Args:
        audio_data: 입력 오디오 데이터 (WebM, WAV 등)
        target_sample_rate: 목표 샘플레이트 (기본 8000Hz)

    Returns:
        변환된 PCM 데이터 (16-bit, Mono)
    """
    try:
        import pydub
        from pydub import AudioSegment

        # AudioSegment로 변환
        audio = AudioSegment.from_file(BytesIO(audio_data))

        # 8kHz Mono로 변환
        audio = audio.set_frame_rate(target_sample_rate)
        audio = audio.set_channels(1)
        audio = audio.set_sample_width(2)  # 16-bit

        # Raw PCM 데이터 추출
        return audio.raw_data

    except Exception as e:
        logger.error(f"Audio conversion error: {e}")
        # pydub 없으면 ffmpeg 사용 시도
        try:
            import subprocess
            import tempfile

            # 임시 파일 생성
            with tempfile.NamedTemporaryFile(suffix='.webm', delete=False) as input_file:
                input_file.write(audio_data)
                input_path = input_file.name

            output_path = input_path + '.pcm'

            # ffmpeg로 변환
            cmd = [
                'ffmpeg', '-i', input_path,
                '-f', 's16le',  # 16-bit PCM
                '-acodec', 'pcm_s16le',
                '-ar', str(target_sample_rate),  # 8kHz
                '-ac', '1',  # Mono
                '-y',  # Overwrite
                output_path
            ]

            subprocess.run(cmd, capture_output=True, check=True)

            # PCM 데이터 읽기
            with open(output_path, 'rb') as f:
                pcm_data = f.read()

            # 임시 파일 삭제
            os.unlink(input_path)
            os.unlink(output_path)

            return pcm_data

        except Exception as e2:
            logger.error(f"FFmpeg conversion error: {e2}")
            raise ValueError(f"Audio conversion failed: {e}, {e2}")


async def call_fluencypro_analyze(text: str, audio_data: bytes) -> Dict:
    """
    FluencyPro API를 통한 유창성 분석

    Args:
        text: 평가 대상 한국어 문장
        audio_data: 음성 데이터 (bytes)

    Returns:
        Dict: 유창성 평가 결과
        {
            "success": bool,
            "total_reading_words": int,
            "total_correct_words": int,
            "total_duration": float,
            "reading_words_per_unit": float,
            "correct_words_per_unit": float,
            "output": str,  # STT 결과 (오류 태그 포함)
            "error": str  # 오류 메시지 (실패 시)
        }
    """

    try:
        # 1. 오디오를 8kHz PCM으로 변환
        logger.info(f"Converting audio to PCM (8kHz, Mono, 16-bit)...")
        pcm_data = convert_audio_to_pcm(audio_data, target_sample_rate=8000)

        # 2. WebSocket 연결
        logger.info(f"Connecting to FluencyPro: {FLUENCYPRO_WS_URL}")
        async with websockets.connect(FLUENCYPRO_WS_URL, ping_timeout=30) as websocket:

            # 3. JOIN 메시지 전송
            join_message = json.dumps({
                "language": "ko",
                "cmd": "join",
                "answer": text
            })

            logger.info(f"Sending JOIN message...")
            await websocket.send(join_message)

            # 4. REPLY 대기
            reply_data = await websocket.recv()
            reply = json.loads(reply_data)

            if reply.get("event") != "reply":
                raise ValueError(f"Unexpected event: {reply.get('event')}")

            logger.info(f"Received REPLY event, sending audio data...")

            # 5. PCM 데이터 전송 (청크 단위)
            chunk_size = 4096 * 2  # 4096 샘플 * 2 bytes (16-bit)
            total_chunks = (len(pcm_data) + chunk_size - 1) // chunk_size

            for i in range(0, len(pcm_data), chunk_size):
                chunk = pcm_data[i:i + chunk_size]
                await websocket.send(chunk)
                logger.debug(f"Sent chunk {i//chunk_size + 1}/{total_chunks}")

            # 6. QUIT 메시지 전송
            quit_message = json.dumps({
                "language": "ko",
                "cmd": "quit"
            })

            logger.info(f"Sending QUIT message...")
            await websocket.send(quit_message)

            # 7. 결과 대기
            logger.info(f"Waiting for analysis result...")
            result_data = await websocket.recv()
            result = json.loads(result_data)

            # 8. 결과 파싱
            if result.get("success"):
                fluency_data = result.get("result", {}).get("SpeechproFluency", {})

                return {
                    "success": True,
                    "total_reading_words": fluency_data.get("total_reading_words", 0),
                    "total_correct_words": fluency_data.get("total_correct_words", 0),
                    "total_duration": fluency_data.get("total_duration", 0.0),
                    "reading_words_per_unit": fluency_data.get("reading_words_per_unit", 0.0),
                    "correct_words_per_unit": fluency_data.get("correct_words_per_unit", 0.0),
                    "output": result.get("result", {}).get("output", ""),
                    "accuracy_rate": round(
                        (fluency_data.get("total_correct_words", 0) /
                         max(fluency_data.get("total_reading_words", 1), 1)) * 100,
                        2
                    )
                }
            else:
                logger.error(f"FluencyPro analysis failed: {result}")
                return {
                    "success": False,
                    "error": "음성 분석에 실패했습니다. 다시 시도해 주세요."
                }

    except asyncio.TimeoutError:
        logger.error("FluencyPro connection timeout")
        return {
            "success": False,
            "error": "서버 연결 시간이 초과되었습니다."
        }

    except websockets.exceptions.WebSocketException as e:
        logger.error(f"WebSocket error: {e}")
        return {
            "success": False,
            "error": f"WebSocket 연결 오류: {str(e)}"
        }

    except Exception as e:
        logger.error(f"FluencyPro analysis error: {e}", exc_info=True)
        return {
            "success": False,
            "error": f"분석 중 오류 발생: {str(e)}"
        }


def parse_fluency_output(output: str) -> Dict:
    """
    FluencyPro output 문자열 파싱

    Args:
        output: FluencyPro 결과 텍스트
                예: "한국에서 <0.09> 대중교통을 R교통카드를 Y사용하면"

    Returns:
        Dict: 파싱된 정보
        {
            "recognized_text": str,  # 태그 제거된 텍스트
            "pauses": List[float],   # 침묵 시간 목록
            "omitted_words": List[str],  # 생략된 단어 (R 태그)
            "error_words": List[str]     # 오류 단어 (Y 태그)
        }
    """
    import re

    # 침묵 태그 추출 <0.09>
    pauses = [float(m.group(1)) for m in re.finditer(r'<(\d+\.\d+)>', output)]

    # 생략된 단어 추출 (R태그)
    omitted = [m.group(1) for m in re.finditer(r'R(\S+)', output)]

    # 오류 단어 추출 (Y태그)
    errors = [m.group(1) for m in re.finditer(r'Y(\S+)', output)]

    # 태그 제거한 텍스트
    clean_text = re.sub(r'<\d+\.\d+>', '', output)
    clean_text = re.sub(r'[RY]', '', clean_text)
    clean_text = ' '.join(clean_text.split())  # 공백 정리

    return {
        "recognized_text": clean_text,
        "pauses": pauses,
        "omitted_words": omitted,
        "error_words": errors,
        "total_pauses": len(pauses),
        "total_omissions": len(omitted),
        "total_errors": len(errors)
    }
